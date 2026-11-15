"""EONET ingestion: full event catalog into PostgreSQL.

Events are fetched in monthly windows to avoid the API's single-response
limit for large years. Each window is idempotent: events are upserted and
their geometry is replaced.
"""
from __future__ import annotations

import argparse
import time
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from core.nasa_events import EonetClient
from core.nasa_events.sources.eonet import EonetApiError

from core import db
from processor.event_regions import assign_event
from core.models import Event, EventGeometry, IngestRun

SOURCE = "EONET"


def _month_windows(since: date, until: date):
    cursor = date(since.year, since.month, 1)
    while cursor <= until:
        if cursor.month == 12:
            nxt = date(cursor.year + 1, 1, 1)
        else:
            nxt = date(cursor.year, cursor.month + 1, 1)
        start = max(cursor, since)
        end = min(nxt - timedelta(days=1), until)
        if start <= end:
            yield start, end
        cursor = nxt


def _event_row(event) -> dict:
    dates = [item.date for item in event.geometry if item.date is not None]
    magnitude = next(
        (item for item in event.geometry if item.magnitude_value is not None), None
    )
    return {
        "id": event.id,
        "source": SOURCE,
        "title": event.title,
        "description": event.description,
        "link": event.link,
        "status": "closed" if event.closed is not None else "open",
        "category": event.categories[0] if event.categories else None,
        "first_seen": min(dates).date() if dates else None,
        "last_seen": max(dates).date() if dates else None,
        "closed_at": event.closed,
        "magnitude": magnitude.magnitude_value if magnitude else None,
        "magnitude_unit": magnitude.magnitude_unit if magnitude else None,
        "source_url": event.link,
    }


def _fetch_window(client: EonetClient, start: date, end: date) -> list:
    for attempt in range(4):
        try:
            payload = client.events(
                status="all",
                start=start.isoformat(),
                end=end.isoformat(),
                limit=1000,
            )
            events = EonetClient.parse_events(payload)
            time.sleep(1.2)
            if len(events) < 1000 or start >= end:
                if len(events) >= 1000:
                    print(f"WARN {start}..{end}: 1000 eventos en un día", flush=True)
                return events
            # The API caps one response at 1000 events. Split the window and
            # merge by id so long-lived events are not duplicated.
            print(f"split {start}..{end}: {len(events)} eventos", flush=True)
            middle = start + timedelta(days=(end - start).days // 2)
            left = _fetch_window(client, start, middle)
            right = _fetch_window(client, middle + timedelta(days=1), end)
            merged = {event.id: event for event in left + right}
            return list(merged.values())
        except EonetApiError as exc:
            if exc.status != 429 or attempt == 3:
                raise
            wait = 30 * (attempt + 1)
            print(f"429 en {start}..{end}; esperando {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError("EONET window returned no response")


def ingest(since: date, until: date) -> None:
    if not db.is_configured():
        raise SystemExit("DATABASE_URL is not configured")
    client = EonetClient(use_cache=True, timeout=90)
    with db.session_scope() as session:
        run = IngestRun(job="eonet", source=SOURCE, status="running")
        session.add(run)
        session.flush()
        run_id = run.id

    total_events = 0
    total_geometry = 0
    try:
        for start, end in _month_windows(since, until):
            events = _fetch_window(client, start, end)
            with db.session_scope() as session:
                for event in events:
                    row = _event_row(event)
                    stmt = insert(Event).values(**row)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["id"],
                        set_=row,
                    )
                    session.execute(stmt)
                    session.execute(
                        delete(EventGeometry).where(EventGeometry.event_id == event.id)
                    )
                    geometry_rows = [
                        {
                            "event_id": event.id,
                            "geometry_date": item.date,
                            "geometry_type": item.geometry_type,
                            "coordinates": item.coordinates,
                            "magnitude": item.magnitude_value,
                            "magnitude_unit": item.magnitude_unit,
                        }
                        for item in event.geometry
                        if item.date is not None
                    ]
                    if geometry_rows:
                        session.execute(insert(EventGeometry), geometry_rows)
                    assign_event(
                        session,
                        event.id,
                        [(item.coordinates, item.date) for item in event.geometry],
                    )
                total_events += len(events)
                total_geometry += sum(len(event.geometry) for event in events)
            print(
                f"{start}..{end}: eventos={len(events)} acumulado={total_events}",
                flush=True,
            )
    except Exception as exc:
        with db.session_scope() as session:
            row = session.get(IngestRun, run_id)
            if row:
                row.status = "failed"
                row.finished_at = datetime.now(timezone.utc)
                row.error = f"{type(exc).__name__}: {exc}"
        raise
    else:
        with db.session_scope() as session:
            row = session.get(IngestRun, run_id)
            if row:
                row.status = "success"
                row.finished_at = datetime.now(timezone.utc)
                row.rows_read = total_events
                row.rows_written = total_events
                row.details = {"geometry_rows": total_geometry}
    print(f"ok: eventos={total_events} geometrías={total_geometry}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2006-01-01")
    parser.add_argument("--until", default=date.today().isoformat())
    parser.add_argument("--years", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    until = datetime.strptime(args.until.replace("-", ""), "%Y%m%d").date()
    since = date(until.year - args.years + 1, 1, 1) if args.years else datetime.strptime(args.since.replace("-", ""), "%Y%m%d").date()
    if args.dry_run:
        print(f"dry-run: {since}..{until}")
        return 0
    ingest(since, until)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
