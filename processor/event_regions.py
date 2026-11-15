"""Assign EONET geometries to the 162 POC regions.

The regions are the frequency-4 cells of the geodesic grid; a point belongs to
the region whose centre is nearest. Lines and polygons are flattened to their
coordinate pairs, so a storm track can touch several regions.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime
from typing import Any

from core.nasa_events.hexgrid import region_of, to_vec
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.models import EventRegion


def _day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def iter_points(coordinates: Any) -> Iterable[tuple[float, float]]:
    """Yield (lon, lat) pairs from a GeoJSON coordinate tree."""
    if not isinstance(coordinates, (list, tuple)):
        return
    if (
        len(coordinates) >= 2
        and isinstance(coordinates[0], (int, float))
        and isinstance(coordinates[1], (int, float))
    ):
        yield float(coordinates[0]), float(coordinates[1])
        return
    for item in coordinates:
        yield from iter_points(item)


def representative_point(coordinates: Any) -> tuple[float, float] | None:
    """One point per geometry: the point itself or the centroid of its ring/line."""
    points = list(iter_points(coordinates))
    if not points:
        return None
    lons = [lon for lon, _ in points]
    if max(lons) - min(lons) > 180:  # dateline crossing
        lons = [lon + 360 if lon < 0 else lon for lon in lons]
    lon = sum(lons) / len(lons)
    if lon > 180:
        lon -= 360
    lat = sum(lat for _, lat in points) / len(points)
    return lon, lat


def _region_rows(
    event_id: str, geometries: Sequence[tuple[Any, Any]]
) -> list[dict]:
    stats: dict[int, dict] = {}
    for coordinates, when in geometries:
        day = _day(when)
        point = representative_point(coordinates)
        if point is None:
            continue
        region = region_of(to_vec(point[1], point[0]))
        entry = stats.setdefault(
            region, {"count": 0, "first": None, "last": None}
        )
        entry["count"] += 1
        if day is not None:
            if entry["first"] is None or day < entry["first"]:
                entry["first"] = day
            if entry["last"] is None or day > entry["last"]:
                entry["last"] = day
    if not stats:
        return []
    primary = max(
        stats,
        key=lambda region: (
            stats[region]["count"],
            stats[region]["last"] or date.min,
            -region,
        ),
    )
    return [
        {
            "event_id": event_id,
            "region_code": region,
            "first_date": entry["first"],
            "last_date": entry["last"],
            "n_geometries": entry["count"],
            "is_primary": region == primary,
        }
        for region, entry in stats.items()
    ]


def assign_events(
    session: Session, items: Sequence[tuple[str, Sequence[tuple[Any, Any]]]]
) -> int:
    """Replace the region assignments for a batch of events."""
    ids = [event_id for event_id, _ in items]
    if not ids:
        return 0
    rows: list[dict] = []
    for event_id, geometries in items:
        rows.extend(_region_rows(event_id, geometries))
    session.execute(delete(EventRegion).where(EventRegion.event_id.in_(ids)))
    if rows:
        statement = insert(EventRegion).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=["event_id", "region_code"],
            set_={
                "first_date": statement.excluded.first_date,
                "last_date": statement.excluded.last_date,
                "n_geometries": statement.excluded.n_geometries,
                "is_primary": statement.excluded.is_primary,
            },
        )
        session.execute(statement)
    return len(rows)


def assign_event(
    session: Session, event_id: str, geometries: Sequence[tuple[Any, Any]]
) -> int:
    return assign_events(session, [(event_id, geometries)])
