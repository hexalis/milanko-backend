"""Populate event_regions from the persisted EONET geometries.

Run after deploying the event_regions migration and whenever the assignment
logic changes. It is idempotent: each event's assignments are replaced.
"""
from __future__ import annotations

import argparse
from collections import defaultdict

from sqlalchemy import select

from core import db
from processor.event_regions import assign_events
from core.models import Event, EventGeometry


def run(batch: int = 500) -> None:
    if not db.is_configured():
        raise SystemExit("DATABASE_URL is not configured")
    with db.session_scope() as session:
        events = session.execute(
            select(Event.id, Event.first_seen, Event.last_seen).order_by(Event.id)
        ).all()
        geometries = session.execute(
            select(
                EventGeometry.event_id,
                EventGeometry.coordinates,
                EventGeometry.geometry_date,
            ).order_by(EventGeometry.event_id)
        ).all()
    grouped: dict[str, list] = defaultdict(list)
    for row in geometries:
        grouped[row.event_id].append((row.coordinates, row.geometry_date))
    items = [(event.id, grouped.get(event.id, [])) for event in events]
    total = 0
    for start in range(0, len(items), batch):
        chunk = items[start : start + batch]
        with db.session_scope() as session:
            total += assign_events(session, chunk)
        print(
            f"eventos={min(start + batch, len(items))}/{len(items)} asignaciones={total}",
            flush=True,
        )
    print(f"ok: {len(items)} eventos, {total} asignaciones evento-región", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=500)
    args = parser.parse_args()
    run(batch=args.batch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
