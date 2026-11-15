"""POWER ingestion: 162 POC regions, 36 core variables, daily 2006+.

The job is intentionally resumable at the location level: every location is
upserted independently. Re-running the command is safe.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from psycopg.types.json import Jsonb

from core.nasa_events.catalog import load_core_selection
from core.nasa_events.sources.power import PowerClient

from core import db
from core.refresh import refresh_coverage, refresh_analytics
from core.world import world_base
from processor.ingest_gibs import GRID_VERSION, seed_catalog as seed_gibs_catalog
from core.models import IngestRun, Location, Observation, Variable

POWER_SOURCE = "NASA POWER"
METHOD_VERSION = "power-point-v1"
BATCH = 2_500


def _power_codes() -> list[str]:
    return [
        row["codigo"]
        for row in load_core_selection()
        if row["disposicion"] == "nucleo" and row["fuente"] == POWER_SOURCE
    ]


def seed_catalog() -> None:
    if not db.is_configured():
        raise SystemExit("DATABASE_URL is not configured")
    seed_gibs_catalog()
    metadata = {row["codigo"]: row for row in load_core_selection()}
    with db.session_scope() as session:
        for code in _power_codes():
            if session.get(Variable, code) is not None:
                continue
            row = metadata[code]
            session.add(
                Variable(
                    code=code,
                    name=row["nombre"],
                    unit=row.get("unidad") or "",
                    source=POWER_SOURCE,
                    native_resolution="daily",
                    description=row.get("motivo") or "",
                )
            )


def _region_elevations() -> dict[int, float]:
    """Mean world-base elevation per POC region, used for POWER PSC."""
    _, records, grid = world_base(80)
    sums: dict[int, float] = {}
    counts: dict[int, int] = {}
    for record in records:
        if record.elevation is None:
            continue
        region = grid.region_for_cell(record.code)
        sums[region] = sums.get(region, 0.0) + record.elevation
        counts[region] = counts.get(region, 0) + 1
    return {region: sums[region] / counts[region] for region in sums}


def _rows(
    observations,
    location_id: int,
) -> list[dict]:
    rows: list[dict] = []
    for obs in observations:
        if obs.time is None or not isinstance(obs.time, date):
            continue
        rows.append(
            {
                "location_id": location_id,
                "source": POWER_SOURCE,
                "variable_code": obs.code,
                "source_layer": None,
                "platform": None,
                "observed_on": obs.time,
                "temporal_resolution": "daily",
                "value": obs.value,
                "unit": obs.unit,
                "quality": obs.quality if obs.quality in {"ok", "fill", "missing"} else "missing",
                "valid_fraction": None,
                "class_counts": None,
                "dominant_class": None,
                "metrics": None,
                "unknown_color_fraction": None,
                "footprint": {"kind": "point", "lat": obs.lat, "lon": obs.lon},
                "resolution_deg": None,
                "palette_version": None,
                "method_version": METHOD_VERSION,
                "time_standard": obs.time_standard,
                "source_url": None,
            }
        )
    return rows


OBS_COLUMNS = (
    "location_id",
    "source",
    "variable_code",
    "source_layer",
    "platform",
    "observed_on",
    "temporal_resolution",
    "value",
    "unit",
    "quality",
    "valid_fraction",
    "class_counts",
    "dominant_class",
    "metrics",
    "unknown_color_fraction",
    "footprint",
    "resolution_deg",
    "palette_version",
    "method_version",
    "time_standard",
    "source_url",
)
JSON_COLUMNS = {"class_counts", "metrics", "footprint"}


def _upsert(session, rows: list[dict]) -> int:
    """COPY into a temp table, then upsert once.

    A 2006+ point produces ~274k rows. SQLAlchemy row-by-row inserts are far
    too slow at that volume; COPY keeps the historical backfill practical.
    """
    if not rows:
        return 0
    raw = session.connection().connection
    with raw.cursor() as cur:
        cur.execute(
            "CREATE TEMP TABLE observations_stage "
            "(LIKE observations INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        columns = ", ".join(OBS_COLUMNS)
        with cur.copy(f"COPY observations_stage ({columns}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(
                    tuple(
                        Jsonb(row[column]) if column in JSON_COLUMNS and row.get(column) is not None else row.get(column)
                        for column in OBS_COLUMNS
                    )
                )
        cur.execute(
            f"""
            INSERT INTO observations ({columns})
            SELECT {columns} FROM observations_stage
            ON CONFLICT (location_id, source, variable_code, observed_on, temporal_resolution)
            DO UPDATE SET
                value = excluded.value,
                unit = excluded.unit,
                quality = excluded.quality,
                metrics = excluded.metrics,
                unknown_color_fraction = excluded.unknown_color_fraction,
                palette_version = excluded.palette_version,
                method_version = excluded.method_version,
                time_standard = excluded.time_standard,
                ingested_at = now()
            """
        )
    return len(rows)


def run(*, since: date, until: date, workers: int = 1, limit: int | None = None) -> None:
    if not db.is_configured():
        raise SystemExit("DATABASE_URL is not configured")
    codes = _power_codes()
    seed_catalog()
    elevations = _region_elevations()
    with db.session_scope() as session:
        statement = (
            select(Location.id, Location.region_code, Location.lat, Location.lon)
            .where(Location.kind == "hex_region")
            .order_by(Location.region_code)
        )
        if limit:
            statement = statement.limit(limit)
        locations = session.execute(statement).all()
        run_row = IngestRun(job="power", source=POWER_SOURCE, status="running")
        session.add(run_row)
        session.flush()
        run_id = run_row.id

    total = 0
    try:
        for number, (location_id, region_code, lat, lon) in enumerate(locations, start=1):
            client = PowerClient(use_cache=True, timeout=180)
            observations = client.point(
                codes,
                lat,
                lon,
                since.strftime("%Y%m%d"),
                until.strftime("%Y%m%d"),
                community="RE",
                site_elevation=elevations.get(region_code, 0.0),
            )
            rows = _rows(observations, location_id)
            with db.session_scope() as session:
                written = _upsert(session, rows)
            total += written
            print(
                f"[{number}/{len(locations)}] region={region_code} "
                f"rows={written} total={total}",
                flush=True,
            )
    except Exception as exc:
        with db.session_scope() as session:
            run_row = session.get(IngestRun, run_id)
            if run_row:
                run_row.status = "failed"
                run_row.finished_at = datetime.now(timezone.utc)
                run_row.error = f"{type(exc).__name__}: {exc}"
        raise
    else:
        with db.session_scope() as session:
            run_row = session.get(IngestRun, run_id)
            if run_row:
                run_row.status = "success"
                run_row.finished_at = datetime.now(timezone.utc)
                run_row.rows_read = total
                run_row.rows_written = total
    try:
        refresh_coverage()
    except Exception as exc:  # noqa: BLE001 - coverage is derivative
        print(f"WARN: no se pudo refrescar coverage: {exc}", flush=True)
    try:
        refresh_analytics()
    except Exception as exc:  # noqa: BLE001 - analytics is derivative
        print(f"WARN: no se pudo refrescar analytics: {exc}", flush=True)
    print(f"ok: {total} observaciones POWER", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="20060101")
    parser.add_argument("--until", default=date.today().strftime("%Y%m%d"))
    parser.add_argument("--days", type=int, default=0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    until = datetime.strptime(args.until.replace("-", ""), "%Y%m%d").date()
    since = until - timedelta(days=args.days) if args.days else datetime.strptime(args.since.replace("-", ""), "%Y%m%d").date()
    if args.dry_run:
        print(f"dry-run: {len(_power_codes())} variables, {since}..{until}")
        return 0
    run(since=since, until=until, workers=args.workers, limit=args.limit or None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
