"""Read-only region queries backed by PostgreSQL."""
from __future__ import annotations

from datetime import date

from core.nasa_events.models import Observation as DomainObservation
from sqlalchemy import Select, func, select, text
from sqlalchemy.orm import Session

from core.models import Event, EventGeometry, EventRegion, Location, Observation, Variable


def _region(row: Location) -> dict:
    return {
        "code": row.region_code,
        "slug": row.slug,
        "name": row.name,
        "lat": row.lat,
        "lon": row.lon,
        "area_km2": row.area_km2,
        "grid_version": row.grid_version,
    }


def list_regions(session: Session) -> list[dict]:
    rows = session.scalars(
        select(Location)
        .where(Location.kind == "hex_region")
        .order_by(Location.region_code)
    ).all()
    return [_region(row) for row in rows]


def get_region(session: Session, region_code: int) -> dict | None:
    row = session.scalar(
        select(Location).where(
            Location.kind == "hex_region", Location.region_code == region_code
        )
    )
    return _region(row) if row is not None else None


def region_observations(
    session: Session,
    region_code: int,
    *,
    variables: list[str] | None,
    start: date,
    end: date,
    limit: int = 5000,
) -> dict | None:
    location = session.scalar(
        select(Location).where(
            Location.kind == "hex_region", Location.region_code == region_code
        )
    )
    if location is None:
        return None

    statement: Select = (
        select(
            Observation.variable_code,
            Observation.observed_on,
            Observation.value,
            Observation.unit,
            Observation.quality,
            Observation.valid_fraction,
            Observation.temporal_resolution,
            Observation.metrics,
            Observation.resolution_deg,
            Observation.method_version,
            Observation.palette_version,
            Variable.name.label("variable_name"),
            Variable.unit.label("variable_unit"),
        )
        .join(Variable, Variable.code == Observation.variable_code)
        .where(
            Observation.location_id == location.id,
            Observation.observed_on >= start,
            Observation.observed_on <= end,
        )
        .order_by(Observation.observed_on, Observation.variable_code)
        .limit(limit)
    )
    if variables:
        statement = statement.where(Observation.variable_code.in_(variables))

    items = []
    for row in session.execute(statement):
        items.append(
            {
                "variable": row.variable_code,
                "name": row.variable_name,
                "date": row.observed_on.isoformat(),
                "value": row.value,
                "unit": row.unit or row.variable_unit,
                "quality": row.quality,
                "valid_fraction": row.valid_fraction,
                "temporal_resolution": row.temporal_resolution,
                "metrics": row.metrics,
                "resolution_deg": row.resolution_deg,
                "method_version": row.method_version,
                "palette_version": row.palette_version,
            }
        )
    return {"region": _region(location), "count": len(items), "observations": items}


def series_for_region(
    session: Session,
    region_code: int,
    *,
    variables: list[str] | None = None,
    start: date,
    end: date,
    source: str = "NASA POWER",
) -> dict[str, list]:
    location = session.scalar(
        select(Location).where(
            Location.kind == "hex_region", Location.region_code == region_code
        )
    )
    if location is None:
        return {}
    statement = (
        select(
            Observation.variable_code,
            Observation.source,
            Observation.observed_on,
            Observation.value,
            Observation.unit,
            Observation.time_standard,
            Observation.temporal_resolution,
            Observation.quality,
            Observation.metrics,
            Variable.unit.label("variable_unit"),
        )
        .join(Variable, Variable.code == Observation.variable_code)
        .where(
            Observation.location_id == location.id,
            Observation.source == source,
            Observation.observed_on >= start,
            Observation.observed_on <= end,
        )
        .order_by(Observation.variable_code, Observation.observed_on)
    )
    if variables:
        statement = statement.where(Observation.variable_code.in_(variables))
    grouped: dict[str, list] = {}
    for row in session.execute(statement):
        grouped.setdefault(row.variable_code, []).append(
            DomainObservation(
                source=row.source,
                code=row.variable_code,
                value=row.value,
                unit=row.unit or row.variable_unit,
                time=row.observed_on,
                time_label=row.observed_on.isoformat(),
                time_standard=row.time_standard or "UTC",
                lat=None,
                lon=None,
                granularity=row.temporal_resolution,
                quality=row.quality,
                meta={"metrics": row.metrics} if row.metrics else {},
            )
        )
    return grouped


def coverage(session: Session, source: str | None = None) -> list[dict]:
    rows = session.execute(
        text(
            """
            SELECT variable_code, source, name, unit, count, start, "end"
            FROM variable_coverage
            WHERE (CAST(:source AS VARCHAR) IS NULL OR source = CAST(:source AS VARCHAR))
            ORDER BY source, variable_code
            """
        ),
        {"source": source},
    ).mappings()
    return [
        {
            "variable": row["variable_code"],
            "source": row["source"],
            "name": row["name"],
            "unit": row["unit"],
            "count": int(row["count"]),
            "start": row["start"].isoformat() if row["start"] else None,
            "end": row["end"].isoformat() if row["end"] else None,
        }
        for row in rows
    ]


def persisted_events(
    session: Session,
    *,
    categories: list[str] | None,
    status: str,
    start: date,
    end: date,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    statement = (
        select(Event)
        .where(Event.first_seen <= end, Event.last_seen >= start)
        .order_by(Event.first_seen, Event.id)
        .limit(limit)
        .offset(offset)
    )
    if categories:
        statement = statement.where(Event.category.in_(categories))
    if status in {"open", "closed"}:
        statement = statement.where(Event.status == status)
    events = session.scalars(statement).all()
    if not events:
        return []
    ids = [event.id for event in events]
    geometries = session.scalars(
        select(EventGeometry)
        .where(EventGeometry.event_id.in_(ids))
        .order_by(EventGeometry.event_id, EventGeometry.geometry_date)
    ).all()
    by_event: dict[str, list[EventGeometry]] = {}
    for geometry in geometries:
        by_event.setdefault(geometry.event_id, []).append(geometry)
    result = []
    for event in events:
        geometry_rows = by_event.get(event.id, [])
        result.append(
            {
                "id": event.id,
                "title": event.title,
                "description": event.description,
                "link": event.link or "",
                "closed": event.closed_at.isoformat() if event.closed_at else None,
                "categories": [event.category] if event.category else [],
                "sources": [],
                "geometry": [
                    {
                        "date": item.geometry_date.isoformat() if item.geometry_date else None,
                        "type": item.geometry_type or "Point",
                        "coordinates": item.coordinates,
                        "magnitude_value": item.magnitude,
                        "magnitude_unit": item.magnitude_unit,
                    }
                    for item in geometry_rows
                ],
                "first_date": event.first_seen.isoformat() if event.first_seen else None,
                "last_date": event.last_seen.isoformat() if event.last_seen else None,
                "duration_days": (
                    (event.last_seen - event.first_seen).days
                    if event.first_seen and event.last_seen
                    else None
                ),
                "n_geometries": len(geometry_rows),
            }
        )
    return result


def latest_for_region(
    session: Session, region_code: int, source: str | None = None
) -> dict | None:
    location = session.scalar(
        select(Location).where(
            Location.kind == "hex_region", Location.region_code == region_code
        )
    )
    if location is None:
        return None
    rows = session.execute(
        text(
            """
            SELECT
                v.code AS variable_code, o.source, v.name, v.unit, o.observed_on,
                o.value, o.quality, o.valid_fraction, o.temporal_resolution
            FROM variables v
            JOIN LATERAL (
                SELECT
                    o.source, o.observed_on, o.value, o.quality,
                    o.valid_fraction, o.temporal_resolution
                FROM observations o
                WHERE o.location_id = :location_id
                  AND o.variable_code = v.code
                  AND o.value IS NOT NULL
                  AND (CAST(:source AS VARCHAR) IS NULL OR o.source = CAST(:source AS VARCHAR))
                ORDER BY o.observed_on DESC
                LIMIT 1
            ) o ON true
            ORDER BY v.code
            """
        ),
        {"location_id": location.id, "source": source},
    ).mappings()
    items = [
        {
            "variable": row["variable_code"],
            "source": row["source"],
            "name": row["name"],
            "unit": row["unit"],
            "date": row["observed_on"].isoformat(),
            "value": row["value"],
            "quality": row["quality"],
            "valid_fraction": row["valid_fraction"],
            "temporal_resolution": row["temporal_resolution"],
        }
        for row in rows
    ]
    items.sort(key=lambda item: (item["source"], item["variable"]))
    return {"region": _region(location), "count": len(items), "variables": items}


def count_persisted_events(
    session: Session,
    *,
    categories: list[str] | None,
    status: str,
    start: date,
    end: date,
) -> int:
    statement = (
        select(func.count())
        .select_from(Event)
        .where(Event.first_seen <= end, Event.last_seen >= start)
    )
    if categories:
        statement = statement.where(Event.category.in_(categories))
    if status in {"open", "closed"}:
        statement = statement.where(Event.status == status)
    return int(session.scalar(statement) or 0)


def event_stats(
    session: Session,
    *,
    categories: list[str] | None,
    status: str,
    start: date,
    end: date,
) -> dict:
    filters = [Event.first_seen <= end, Event.last_seen >= start]
    if categories:
        filters.append(Event.category.in_(categories))
    if status in {"open", "closed"}:
        filters.append(Event.status == status)

    total = int(session.scalar(select(func.count()).select_from(Event).where(*filters)) or 0)
    status_rows = session.execute(
        select(Event.status, func.count()).where(*filters).group_by(Event.status)
    ).all()
    category_rows = session.execute(
        select(Event.category, func.count())
        .where(*filters)
        .group_by(Event.category)
        .order_by(func.count().desc())
    ).all()
    year_expr = func.extract("year", Event.first_seen)
    year_rows = session.execute(
        select(year_expr.label("year"), func.count())
        .where(*filters)
        .group_by(year_expr)
        .order_by(year_expr)
    ).all()
    return {
        "total": total,
        "statuses": {row[0] or "unknown": int(row[1]) for row in status_rows},
        "categories": [
            {"category": row[0], "count": int(row[1])} for row in category_rows
        ],
        "years": [{"year": int(row[0]), "count": int(row[1])} for row in year_rows],
    }


def region_snapshot(
    session: Session,
    *,
    variable: str,
    date: date,
    metric: str,
    source: str | None = None,
) -> dict | None:
    variable_row = session.get(Variable, variable)
    if variable_row is None:
        return None
    source = source or variable_row.source
    if metric == "anomaly":
        rows = session.execute(
            text(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (m.location_id)
                        m.location_id, m.month, m.value
                    FROM region_monthly m
                    WHERE m.variable_code = :variable
                      AND m.source = :source
                      AND m.month <= date_trunc('month', CAST(:date AS date))::date
                    ORDER BY m.location_id, m.month DESC
                ),
                baseline AS (
                    SELECT
                        m.location_id,
                        avg(m.value) AS mean,
                        stddev_samp(m.value) AS sd
                    FROM region_monthly m
                    WHERE m.variable_code = :variable
                      AND m.source = :source
                      AND EXTRACT(month FROM m.month) =
                          EXTRACT(month FROM CAST(:date AS date))
                      AND m.month < date_trunc('month', CAST(:date AS date))::date
                    GROUP BY m.location_id
                )
                SELECT
                    l.region_code,
                    latest.month AS observed_on,
                    latest.value,
                    baseline.mean,
                    baseline.sd,
                    latest.value - baseline.mean AS anomaly,
                    CASE
                        WHEN baseline.sd > 0
                        THEN (latest.value - baseline.mean) / baseline.sd
                    END AS z
                FROM locations l
                LEFT JOIN latest ON latest.location_id = l.id
                LEFT JOIN baseline ON baseline.location_id = l.id
                WHERE l.kind = 'hex_region'
                ORDER BY l.region_code
                """
            ),
            {"variable": variable, "source": source, "date": date},
        ).mappings()
    else:
        rows = session.execute(
            text(
                """
                SELECT
                    l.region_code,
                    o.observed_on,
                    o.value,
                    NULL::double precision AS mean,
                    NULL::double precision AS sd,
                    NULL::double precision AS anomaly,
                    NULL::double precision AS z
                FROM locations l
                LEFT JOIN LATERAL (
                    SELECT o.observed_on, o.value
                    FROM observations o
                    WHERE o.location_id = l.id
                      AND o.variable_code = :variable
                      AND o.source = :source
                      AND o.observed_on <= CAST(:date AS date)
                      AND o.value IS NOT NULL
                    ORDER BY o.observed_on DESC
                    LIMIT 1
                ) o ON true
                WHERE l.kind = 'hex_region'
                ORDER BY l.region_code
                """
            ),
            {"variable": variable, "source": source, "date": date},
        ).mappings()

    regions = [
        {
            "code": row["region_code"],
            "value": row["value"],
            "date": row["observed_on"].isoformat() if row["observed_on"] else None,
            "anomaly": row["anomaly"],
            "z": row["z"],
            "baseline": row["mean"],
        }
        for row in rows
    ]
    key = "anomaly" if metric == "anomaly" else "value"
    values = [item[key] for item in regions if item[key] is not None]
    return {
        "variable": variable,
        "source": source,
        "unit": variable_row.unit,
        "date": date.isoformat(),
        "metric": metric,
        "count": len(values),
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "regions": regions,
    }


def region_rankings(
    session: Session,
    *,
    variable: str,
    metric: str,
    order: str = "desc",
    as_of: date | None = None,
    start: date | None = None,
    limit: int = 10,
    source: str | None = None,
) -> dict | None:
    variable_row = session.get(Variable, variable)
    if variable_row is None:
        return None
    source = source or variable_row.source
    direction = "DESC" if order == "desc" else "ASC"
    if metric == "trend":
        rows = session.execute(
            text(
                f"""
                SELECT
                    l.region_code,
                    l.name,
                    regr_slope(
                        m.value,
                        EXTRACT(EPOCH FROM m.month) / 86400.0
                    ) * 365.25 AS slope_per_year,
                    regr_r2(
                        m.value,
                        EXTRACT(EPOCH FROM m.month) / 86400.0
                    ) AS r2,
                    count(*) AS n_months,
                    max(m.month) AS last_month,
                    (array_agg(m.value ORDER BY m.month DESC))[1] AS latest_value
                FROM region_monthly m
                JOIN locations l ON l.id = m.location_id
                WHERE l.kind = 'hex_region'
                  AND m.source = :source
                  AND m.variable_code = :variable
                  AND m.month >= CAST(:start AS date)
                GROUP BY l.region_code, l.name
                HAVING count(*) >= 24
                ORDER BY slope_per_year {direction}, l.region_code
                """
            ),
            {
                "source": source,
                "variable": variable,
                "start": start or date(2006, 1, 1),
            },
        ).mappings()
        all_items = [
            {
                "code": row["region_code"],
                "name": row["name"],
                "value": row["latest_value"],
                "date": row["last_month"].isoformat() if row["last_month"] else None,
                "slope_per_year": row["slope_per_year"],
                "r2": row["r2"],
                "n_months": int(row["n_months"]),
            }
            for row in rows
        ]
        total = len(all_items)
        items = all_items[:limit]
    else:
        snapshot = region_snapshot(
            session,
            variable=variable,
            date=as_of or date.today(),
            metric=metric,
            source=source,
        )
        if snapshot is None:
            return None
        names = {row["code"]: row["name"] for row in list_regions(session)}
        key = "anomaly" if metric == "anomaly" else "value"
        rows = [row for row in snapshot["regions"] if row[key] is not None]
        rows.sort(key=lambda row: row[key], reverse=(order == "desc"))
        total = len(rows)
        items = [
            {
                "code": row["code"],
                "name": names.get(row["code"], ""),
                "value": row["value"],
                "date": row["date"],
                "anomaly": row["anomaly"],
                "z": row["z"],
            }
            for row in rows[:limit]
        ]
    return {
        "variable": variable,
        "source": source,
        "unit": variable_row.unit,
        "metric": metric,
        "order": order,
        "date": (as_of or date.today()).isoformat() if metric != "trend" else None,
        "count": len(items),
        "total": total,
        "regions": items,
    }


def region_events(
    session: Session,
    region_code: int,
    *,
    categories: list[str] | None,
    status: str,
    start: date,
    end: date,
    limit: int = 100,
) -> list[dict]:
    statement = (
        select(Event, EventRegion)
        .join(EventRegion, EventRegion.event_id == Event.id)
        .where(
            EventRegion.region_code == region_code,
            Event.first_seen <= end,
            Event.last_seen >= start,
        )
        .order_by(
            EventRegion.first_date.desc().nullslast(),
            Event.first_seen.desc().nullslast(),
            Event.id,
        )
        .limit(limit)
    )
    if categories:
        statement = statement.where(Event.category.in_(categories))
    if status in {"open", "closed"}:
        statement = statement.where(Event.status == status)
    rows = session.execute(statement).all()
    return [
        {
            "id": event.id,
            "title": event.title,
            "category": event.category,
            "status": event.status,
            "first_date": event.first_seen.isoformat() if event.first_seen else None,
            "last_date": event.last_seen.isoformat() if event.last_seen else None,
            "link": event.link,
            "magnitude": event.magnitude,
            "magnitude_unit": event.magnitude_unit,
            "n_geometries": assignment.n_geometries,
            "is_primary": assignment.is_primary,
        }
        for event, assignment in rows
    ]


def event_context(session: Session, event_id: str) -> dict | None:
    event = session.get(Event, event_id)
    if event is None:
        return None
    assignments = session.execute(
        select(EventRegion, Location)
        .join(
            Location,
            (Location.region_code == EventRegion.region_code)
            & (Location.kind == "hex_region"),
        )
        .where(EventRegion.event_id == event_id)
        .order_by(
            EventRegion.is_primary.desc(),
            EventRegion.n_geometries.desc(),
            EventRegion.region_code,
        )
    ).all()
    regions = [
        {
            "code": assignment.region_code,
            "name": location.name,
            "n_geometries": assignment.n_geometries,
            "is_primary": assignment.is_primary,
            "lat": location.lat,
            "lon": location.lon,
        }
        for assignment, location in assignments
    ]
    primary = regions[0] if regions else None
    period_end = event.last_seen or event.first_seen or date.today()
    variables: list[dict] = []
    if primary is not None:
        location = session.scalar(
            select(Location).where(
                Location.kind == "hex_region",
                Location.region_code == primary["code"],
            )
        )
        if location is not None:
            rows = session.execute(
                text(
                    """
                    WITH latest AS (
                        SELECT DISTINCT ON (m.variable_code)
                            m.location_id, m.source, m.variable_code, m.month, m.value
                        FROM region_monthly m
                        WHERE m.location_id = :location_id
                          AND m.variable_code IN ('T2M', 'PRECTOTCORR', 'LST_DAY', 'NDVI')
                          AND m.month <= date_trunc('month', CAST(:date AS date))::date
                        ORDER BY m.variable_code, m.month DESC
                    )
                    SELECT
                        latest.variable_code,
                        v.name,
                        v.unit,
                        latest.source,
                        latest.month,
                        latest.value,
                        baseline.mean,
                        baseline.sd,
                        latest.value - baseline.mean AS anomaly,
                        CASE
                            WHEN baseline.sd > 0
                            THEN (latest.value - baseline.mean) / baseline.sd
                        END AS z
                    FROM latest
                    JOIN variables v ON v.code = latest.variable_code
                    LEFT JOIN LATERAL (
                        SELECT avg(m.value) AS mean, stddev_samp(m.value) AS sd
                        FROM region_monthly m
                        WHERE m.location_id = latest.location_id
                          AND m.variable_code = latest.variable_code
                          AND m.source = latest.source
                          AND EXTRACT(month FROM m.month) =
                              EXTRACT(month FROM latest.month)
                          AND m.month < latest.month
                    ) baseline ON true
                    ORDER BY latest.variable_code
                    """
                ),
                {"location_id": location.id, "date": period_end},
            ).mappings()
            variables = [
                {
                    "variable": row["variable_code"],
                    "name": row["name"],
                    "unit": row["unit"],
                    "source": row["source"],
                    "month": row["month"].isoformat() if row["month"] else None,
                    "value": row["value"],
                    "baseline": row["mean"],
                    "anomaly": row["anomaly"],
                    "z": row["z"],
                }
                for row in rows
            ]
    return {
        "event": {
            "id": event.id,
            "title": event.title,
            "description": event.description,
            "link": event.link,
            "category": event.category,
            "status": event.status,
            "first_date": event.first_seen.isoformat() if event.first_seen else None,
            "last_date": event.last_seen.isoformat() if event.last_seen else None,
            "closed": event.closed_at.isoformat() if event.closed_at else None,
            "magnitude": event.magnitude,
            "magnitude_unit": event.magnitude_unit,
        },
        "region": primary,
        "regions": regions,
        "period": {
            "start": event.first_seen.isoformat() if event.first_seen else None,
            "end": event.last_seen.isoformat() if event.last_seen else None,
        },
        "variables": variables,
    }


def event_map(
    session: Session,
    *,
    categories: list[str] | None,
    status: str,
    start: date,
    end: date,
    limit: int = 5000,
) -> dict:
    """One point per event (its primary region centre) for the globe layer.

    The globe aggregates these points into base cells, so the region centre is
    enough and avoids sorting every geometry vertex on each request.
    """
    filters = ["e.first_seen <= :end", "e.last_seen >= :start"]
    params: dict = {"start": start, "end": end, "limit": limit}
    if categories:
        filters.append("e.category = ANY(:categories)")
        params["categories"] = categories
    if status in {"open", "closed"}:
        filters.append("e.status = :status")
        params["status"] = status
    rows = session.execute(
        text(
            f"""
            SELECT * FROM (
                SELECT DISTINCT ON (er.event_id)
                    e.id, e.title, e.category, e.status,
                    e.first_seen, e.last_seen,
                    er.first_date, er.last_date,
                    l.lat, l.lon
                FROM event_regions er
                JOIN events e ON e.id = er.event_id
                JOIN locations l
                  ON l.region_code = er.region_code
                 AND l.kind = 'hex_region'
                WHERE {' AND '.join(filters)}
                ORDER BY er.event_id, er.is_primary DESC, er.n_geometries DESC
            ) latest
            ORDER BY latest.last_seen DESC NULLS LAST
            LIMIT :limit
            """
        ),
        params,
    ).mappings()
    points = [
        {
            "id": row["id"],
            "title": row["title"],
            "category": row["category"],
            "status": row["status"],
            "lat": row["lat"],
            "lon": row["lon"],
            "date": (
                row["last_date"]
                or row["last_seen"]
                or row["first_date"]
                or row["first_seen"]
            ).isoformat()
            if (
                row["last_date"]
                or row["last_seen"]
                or row["first_date"]
                or row["first_seen"]
            )
            else None,
        }
        for row in rows
    ]
    return {"count": len(points), "points": points}
