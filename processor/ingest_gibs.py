"""GIBS ingestion CLI: global WMS -> 162 regional observations -> PostgreSQL.

Examples:
    python -m processor.ingest_gibs seed
    python -m processor.ingest_gibs run --days 90 --workers 2
    python -m processor.ingest_gibs run --since 20060101 --until 20261001 --layers LST_DAY,NDVI
"""
from __future__ import annotations

import argparse
import gc
import re
import sys
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from core.nasa_events.gibs_extract import LAYERS, LayerSpec, extract_layer, load_palettes
from core.nasa_events.gibs_regions import build_region_map
from core.nasa_events.hexgrid import EARTH_AREA_KM2, region_centres, to_lat_lon
from core.nasa_events.sources.gibs import GibsClient

from core import db
from core.refresh import refresh_coverage, refresh_analytics
from core.models import (
    GibsAvailability,
    IngestRun,
    Location,
    Observation,
    Palette,
    SourceLayer,
    Variable,
)

# Legacy grid identifier stored in PostgreSQL; keep it stable.
GRID_VERSION = "milanko-hex-162-2048x1024-v1"
METHOD_VERSION = "gibs-global-2048-v1"
PALETTE_VERSION = load_palettes()["version"]
SOURCE = "NASA GIBS"
WIDTH = 2048
HEIGHT = 1024


def _parse_date(value: str) -> date:
    return datetime.strptime(value.replace("-", ""), "%Y%m%d").date()


def _dates(
    spec: LayerSpec, since: date, until: date, step_days: int = 1
) -> list[date]:
    out: list[date] = []
    step = max(1, step_days)
    if spec.time_format == "month":
        cursor = date(since.year, since.month, 1)
        while cursor <= until:
            out.append(cursor)
            if cursor.month == 12:
                cursor = date(cursor.year + 1, 1, 1)
            else:
                cursor = date(cursor.year, cursor.month + 1, 1)
    else:
        cursor = since
        while cursor <= until:
            out.append(cursor)
            cursor += timedelta(days=step)
    return out


def seed_catalog() -> None:
    if not db.is_configured():
        raise SystemExit("DATABASE_URL is not configured")
    palettes = load_palettes()
    centres = region_centres()
    with db.session_scope() as session:
        for code, spec in LAYERS.items():
            variable = session.get(Variable, code)
            if variable is None:
                session.add(
                    Variable(
                        code=code,
                        name=spec.layer,
                        unit=spec.unit,
                        source=SOURCE,
                        native_resolution="daily" if spec.time_format == "day" else "monthly",
                        description=f"GIBS {spec.layer}",
                    )
                )
        # Flush variables before source_layers: the FK ordering must be explicit.
        session.flush()

        for code, spec in LAYERS.items():
            layer = session.scalar(
                select(SourceLayer).where(
                    SourceLayer.source == SOURCE, SourceLayer.layer == spec.layer
                )
            )
            if layer is None:
                session.add(
                    SourceLayer(
                        source=SOURCE,
                        layer=spec.layer,
                        variable_code=code,
                        platform=spec.layer.split("_")[0],
                        native_resolution="daily" if spec.time_format == "day" else "monthly",
                        palette_id=f"{code}:{PALETTE_VERSION}",
                        extraction_method=METHOD_VERSION,
                    )
                )
            palette = session.scalar(
                select(Palette).where(
                    Palette.layer == spec.layer, Palette.version == PALETTE_VERSION
                )
            )
            if palette is None:
                session.add(
                    Palette(
                        layer=spec.layer,
                        version=PALETTE_VERSION,
                        mapping=palettes["layers"][code]["entries"],
                        source_url=palettes["layers"][code]["url"],
                    )
                )

        for region_code, centre in enumerate(centres):
            slug = f"region-{region_code:03d}"
            location = session.scalar(select(Location).where(Location.slug == slug))
            if location is not None:
                continue
            lat, lon = to_lat_lon(centre)
            session.add(
                Location(
                    slug=slug,
                    name=f"Milanko region {region_code:03d}",
                    kind="hex_region",
                    grid_version=GRID_VERSION,
                    region_code=region_code,
                    lat=round(lat, 6),
                    lon=round(lon, 6),
                    area_km2=EARTH_AREA_KM2 / len(centres),
                )
            )


def _fetch_and_extract(
    spec: LayerSpec, observed_on: date, region_id: Any, weight: Any, workers: int = 1
) -> tuple[LayerSpec, date, list[dict[str, Any]], dict[str, Any] | None]:
    """Fetch one layer/date. Missing dates are data, not fatal errors."""
    client = GibsClient(use_cache=False, timeout=180)
    try:
        rows = extract_layer(
            client,
            spec,
            observed_on.isoformat(),
            region_id,
            weight,
            width=WIDTH,
            height=HEIGHT,
        )
        return spec, observed_on, rows, None
    except Exception as exc:  # noqa: BLE001 - historical dates fail in many ways
        message = f"{type(exc).__name__}: {exc}"
        http_status = None
        match = re.search(r"HTTP (\d{3})", str(exc))
        if match:
            http_status = int(match.group(1))
        return (
            spec,
            observed_on,
            [],
            {"http_status": http_status, "error": message[:500]},
        )


def _upsert_batch(
    session,
    fetched: list[tuple[LayerSpec, date, list[dict[str, Any]], dict[str, Any] | None]],
    location_ids: dict[int, int],
) -> tuple[int, int, int]:
    rows_written = 0
    errors = 0
    availability_rows: list[dict[str, Any]] = []
    for spec, observed_on, regions, failure in fetched:
        valid_rows = [row for row in regions if row.get("value") is not None]
        valid_fraction = sum(row["valid_fraction"] for row in regions) / max(1, len(regions))
        unknown_fraction = max(
            (row.get("unknown_color_fraction", 0) for row in regions), default=0
        )
        if failure:
            errors += 1
            availability_rows.append(
                {
                    "layer": spec.layer,
                    "observed_on": observed_on,
                    "status": "error",
                    "http_status": failure.get("http_status"),
                    "valid_fraction": None,
                    "unknown_fraction": None,
                    "error": failure.get("error"),
                    "fetched_at": func.now(),
                }
            )
            continue
        availability_rows.append(
            {
                "layer": spec.layer,
                "observed_on": observed_on,
                "status": "ok" if valid_rows else "no_data",
                "http_status": 200,
                "valid_fraction": round(valid_fraction, 6),
                "unknown_fraction": round(unknown_fraction, 6),
                "error": None,
                "fetched_at": func.now(),
            }
        )
        if not valid_rows:
            continue
        values = [
            {
                "location_id": location_ids[row["region_code"]],
                "source": SOURCE,
                "variable_code": spec.variable,
                "source_layer": spec.layer,
                "platform": spec.layer.split("_")[0],
                "observed_on": observed_on,
                "temporal_resolution": "daily" if spec.time_format == "day" else "monthly",
                "value": row["value"],
                "unit": spec.unit,
                "quality": row["quality"],
                "valid_fraction": row["valid_fraction"],
                "class_counts": None,
                "dominant_class": None,
                "metrics": row.get("metrics"),
                "unknown_color_fraction": row.get("unknown_color_fraction"),
                "footprint": {"bbox": [-180, -90, 180, 90], "width": WIDTH, "height": HEIGHT},
                "resolution_deg": 180.0 / HEIGHT,
                "palette_version": PALETTE_VERSION,
                "method_version": METHOD_VERSION,
                "time_standard": "UTC",
                "source_url": None,
            }
            for row in valid_rows
        ]
        stmt = insert(Observation).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                "location_id",
                "source",
                "variable_code",
                "observed_on",
                "temporal_resolution",
            ],
            set_={
                "value": stmt.excluded.value,
                "quality": stmt.excluded.quality,
                "valid_fraction": stmt.excluded.valid_fraction,
                "metrics": stmt.excluded.metrics,
                "unknown_color_fraction": stmt.excluded.unknown_color_fraction,
                "palette_version": stmt.excluded.palette_version,
                "method_version": stmt.excluded.method_version,
                "ingested_at": func.now(),
            },
        )
        session.execute(stmt)
        rows_written += len(values)

    for row in availability_rows:
        stmt = insert(GibsAvailability).values(**row)
        stmt = stmt.on_conflict_do_update(
            index_elements=["layer", "observed_on"],
            set_={
                "status": stmt.excluded.status,
                "http_status": stmt.excluded.http_status,
                "valid_fraction": stmt.excluded.valid_fraction,
                "unknown_fraction": stmt.excluded.unknown_fraction,
                "error": stmt.excluded.error,
                "fetched_at": func.now(),
            },
        )
        session.execute(stmt)
    return sum(len(rows) for _, _, rows, _ in fetched), rows_written, errors


def run(
    *,
    since: date,
    until: date,
    layer_names: list[str],
    workers: int,
    dry_run: bool,
    skip_known: bool = False,
    step_days: int = 1,
) -> None:
    if not db.is_configured():
        raise SystemExit("DATABASE_URL is not configured")
    region_id, weight = build_region_map(WIDTH, HEIGHT)
    tasks: list[tuple[LayerSpec, date]] = []
    for name in layer_names:
        spec = LAYERS[name]
        for observed_on in _dates(spec, since, until, step_days):
            tasks.append((spec, observed_on))

    if skip_known:
        layer_values = [LAYERS[name].layer for name in layer_names]
        with db.session_scope() as session:
            known = {
                (row[0], row[1])
                for row in session.execute(
                    select(GibsAvailability.layer, GibsAvailability.observed_on).where(
                        GibsAvailability.layer.in_(layer_values),
                        GibsAvailability.observed_on >= since,
                        GibsAvailability.observed_on <= until,
                        GibsAvailability.status.in_(["ok", "no_data"]),
                    )
                ).all()
            }
        before = len(tasks)
        tasks = [task for task in tasks if (task[0].layer, task[1]) not in known]
        print(f"reanudando: {before - len(tasks)} tareas ya registradas", flush=True)

    print(f"tareas: {len(tasks)} capas={len(layer_names)} workers={workers}", flush=True)
    if dry_run:
        print("dry-run: no se escribirá en PostgreSQL")
        return

    with db.session_scope() as session:
        location_ids = {
            code: location_id
            for code, location_id in session.execute(
                select(Location.region_code, Location.id).where(
                    Location.grid_version == GRID_VERSION
                )
            )
        }
        run_row = IngestRun(job="gibs", source=SOURCE, status="running")
        session.add(run_row)
        session.flush()
        run_id = run_row.id

    total_read = 0
    total_written = 0
    total_errors = 0
    pending: list[tuple[LayerSpec, date, list[dict[str, Any]], dict[str, Any] | None]] = []
    try:
        worker_count = max(1, workers)
        task_iter = iter(tasks)
        in_flight: dict = {}

        def submit_next() -> bool:
            try:
                spec, observed_on = next(task_iter)
            except StopIteration:
                return False
            future = pool.submit(
                _fetch_and_extract, spec, observed_on, region_id, weight
            )
            in_flight[future] = (spec, observed_on)
            return True

        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            # Keep only a small window of futures alive. Submitting all tasks at
            # once retains every per-region result (162 dicts each) and caused
            # the historical job to be OOM-killed.
            for _ in range(worker_count * 2):
                if not submit_next():
                    break
            while in_flight:
                done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
                for future in done:
                    in_flight.pop(future, None)
                    result = future.result()
                    pending.append(result)
                    if len(pending) >= 15:
                        with db.session_scope() as session:
                            read, written, errors = _upsert_batch(
                                session, pending, location_ids
                            )
                        total_read += read
                        total_written += written
                        total_errors += errors
                        pending.clear()
                        gc.collect()
                        print(
                            f"lote: leídas={total_read} escritas={total_written} "
                            f"errores={total_errors}",
                            flush=True,
                        )
                    submit_next()
        if pending:
            with db.session_scope() as session:
                read, written, errors = _upsert_batch(session, pending, location_ids)
            total_read += read
            total_written += written
            total_errors += errors
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
                run_row.rows_read = total_read
                run_row.rows_written = total_written
                run_row.error = f"{total_errors} fechas sin datos" if total_errors else None
    try:
        refresh_coverage()
    except Exception as exc:  # noqa: BLE001 - coverage is derivative
        print(f"WARN: no se pudo refrescar coverage: {exc}", flush=True)
    try:
        refresh_analytics()
    except Exception as exc:  # noqa: BLE001 - analytics is derivative
        print(f"WARN: no se pudo refrescar analytics: {exc}", flush=True)
    print(
        f"ok: leídas={total_read} escritas={total_written} errores={total_errors}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--since", default="20060101")
    run_parser.add_argument("--until", default=date.today().strftime("%Y%m%d"))
    run_parser.add_argument("--days", type=int, default=0)
    run_parser.add_argument("--layers", default=",".join(LAYERS))
    run_parser.add_argument("--workers", type=int, default=2)
    run_parser.add_argument("--skip-known", action="store_true")
    run_parser.add_argument(
        "--step-days",
        type=int,
        default=1,
        help="Sample every N days for daily layers (useful to validate 2006+)",
    )
    run_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.command == "seed":
        seed_catalog()
        print("catálogo sembrado")
        return 0

    until = _parse_date(args.until)
    since = until - timedelta(days=args.days) if args.days else _parse_date(args.since)
    layer_names = [item.strip() for item in args.layers.split(",") if item.strip()]
    unknown = [item for item in layer_names if item not in LAYERS]
    if unknown:
        raise SystemExit(f"unknown layers: {', '.join(unknown)}")
    run(
        since=since,
        until=until,
        layer_names=layer_names,
        workers=args.workers,
        dry_run=args.dry_run,
        skip_known=args.skip_known,
        step_days=args.step_days,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
