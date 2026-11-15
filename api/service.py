"""Service layer: library calls → API payloads."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from core.nasa_events import EonetClient, PowerClient
from core.nasa_events.analysis import (
    anomaly_series,
    correlate_events,
    daily_series,
    event_window,
    summarize_events,
    trends_by_variable,
)
from core.nasa_events.catalog import load_core_selection, variable_metadata
from core.nasa_events.models import Event

POWER_SOURCE = "NASA POWER"
MAX_VARIABLES = 40


# --------------------------------------------------------------------- helpers
def _core_index() -> dict[str, dict]:
    return {row["codigo"]: row for row in load_core_selection()}


def validate_power_codes(variables: list[str]) -> list[str]:
    metadata = variable_metadata()
    valid = {code for code, row in metadata.items() if row["Fuente"] == POWER_SOURCE}
    cleaned = [code.strip() for code in variables if code and code.strip()]
    if not cleaned:
        raise ValueError("You must provide at least one POWER variable")
    unknown = sorted({code for code in cleaned if code not in valid})
    if unknown:
        raise ValueError(f"Unknown POWER variables: {', '.join(unknown)}")
    deduped = list(dict.fromkeys(cleaned))
    if len(deduped) > MAX_VARIABLES:
        raise ValueError(f"Maximum {MAX_VARIABLES} variables per query")
    return deduped


def normalize_range(start: str, end: str | None) -> tuple[str, str]:
    end_value = end or date.today().strftime("%Y%m%d")
    try:
        datetime.strptime(start, "%Y%m%d")
        datetime.strptime(end_value, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"Invalid dates (YYYYMMDD format): {exc}") from exc
    if start > end_value:
        raise ValueError("start must be less than or equal to end")
    return start, end_value


def to_eonet_date(ymd: str) -> str:
    return f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}"


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must have 4 values: minLon,maxLat,maxLon,minLat")
    try:
        return (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))
    except ValueError as exc:
        raise ValueError("bbox contains non-numeric values") from exc


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _request_meta(
    codes: list[str],
    lat: float,
    lon: float,
    start: str,
    end: str,
    community: str,
    site_elevation: float | None,
) -> dict:
    return {
        "variables": codes,
        "lat": lat,
        "lon": lon,
        "start": start,
        "end": end,
        "community": community,
        "site_elevation": site_elevation,
    }


def _series(
    power: PowerClient,
    codes: list[str],
    lat: float,
    lon: float,
    start: str,
    end: str,
    community: str,
    site_elevation: float | None,
    granularity: str = "daily",
):
    return daily_series(
        power,
        codes,
        lat,
        lon,
        start,
        end,
        community=community,
        site_elevation=site_elevation,
        temporal=granularity,
    )


def _trends_payload(series: dict, alpha: float) -> dict[str, dict]:
    raw = trends_by_variable(series, alpha)
    return {code: {"code": code, **value} for code, value in raw.items()}


def _anomalies_by_code(series: dict, window_days: int) -> dict[str, list[dict]]:
    return {
        code: anomaly_series(observations, window_days)
        for code, observations in series.items()
    }


def _correlations_payload(raw: dict[str, list[dict]]) -> dict[str, dict]:
    payload: dict[str, dict] = {}
    for code, rows in raw.items():
        usable = [row for row in rows if row.get("r") is not None]
        best = max(usable, key=lambda row: abs(row["r"])) if usable else None
        payload[code] = {"code": code, "best": best, "lags": rows}
    return payload


# -------------------------------------------------------------------- catálogo
def catalog_variables(
    source: str | None = None, section: str | None = None, query: str | None = None
) -> list[dict]:
    core = _core_index()
    items: list[dict] = []
    for code, row in variable_metadata().items():
        if source and row["Fuente"] != source:
            continue
        if section and row["Tema"] != section:
            continue
        haystack = f"{code} {row['Nombre']} {row['Definición / qué mide']}".lower()
        if query and query.lower() not in haystack:
            continue
        items.append(
            {
                "code": code,
                "name": row["Nombre"],
                "source": row["Fuente"],
                "section": row["Tema"],
                "unit": row["Unidad"],
                "temporal": row["Temporalidad"],
                "coverage": row["Cobertura"],
                "definition": row["Definición / qué mide"],
                "disposition": core.get(code, {}).get("disposicion", ""),
                "usage": row.get("Uso sugerido en el reto", ""),
            }
        )
    return items


def catalog_variable(code: str) -> dict | None:
    return next((item for item in catalog_variables() if item["code"] == code), None)


# ---------------------------------------------------------------------- eventos
def serialize_event(event: Event) -> dict:
    dates = [geometry.date for geometry in event.geometry if geometry.date is not None]
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "link": event.link,
        "closed": _iso(event.closed),
        "categories": event.categories,
        "sources": event.sources,
        "geometry": [
            {
                "date": _iso(geometry.date),
                "type": geometry.geometry_type,
                "coordinates": geometry.coordinates,
                "magnitude_value": geometry.magnitude_value,
                "magnitude_unit": geometry.magnitude_unit,
            }
            for geometry in event.geometry
        ],
        "first_date": _iso(min(dates)) if dates else None,
        "last_date": _iso(max(dates)) if dates else None,
        "duration_days": event.duration_days,
        "n_geometries": len(event.geometry),
    }


def list_events(
    eonet: EonetClient,
    categories: list[str] | None,
    status: str,
    start: str | None,
    end: str | None,
    days: int | None,
    bbox: tuple[float, float, float, float] | None,
    limit: int,
    mag_id: str | None,
    mag_min: float | None,
) -> list[dict]:
    payload = eonet.events(
        status=status,
        category=categories,
        start=start,
        end=end,
        days=days,
        bbox=bbox,
        limit=limit,
        mag_id=mag_id,
        mag_min=mag_min,
    )
    return [serialize_event(event) for event in EonetClient.parse_events(payload)]


def get_event(eonet: EonetClient, event_id: str) -> Event:
    payload = eonet.event(event_id)
    events = EonetClient.parse_events({"events": [payload]})
    if not events:
        raise ValueError(f"Event not found: {event_id}")
    return events[0]


# --------------------------------------------------------------- observaciones
def observations(
    power: PowerClient,
    codes: list[str],
    lat: float,
    lon: float,
    start: str,
    end: str | None,
    community: str,
    site_elevation: float | None,
    granularity: str = "daily",
) -> dict:
    start, end = normalize_range(start, end)
    series = _series(
        power, codes, lat, lon, start, end, community, site_elevation, granularity
    )
    variables: dict[str, dict] = {}
    for code, values in series.items():
        first = values[0]
        variables[code] = {
            "unit": first.unit,
            "time_standard": first.time_standard,
            "granularity": first.granularity,
            "values": [
                {
                    "time": item.time.isoformat() if hasattr(item.time, "isoformat") else str(item.time),
                    "value": item.value,
                    "quality": item.quality,
                }
                for item in values
                if item.time is not None
            ],
        }
    return {
        "request": _request_meta(codes, lat, lon, start, end, community, site_elevation),
        "variables": variables,
    }


def anomalies(
    power: PowerClient,
    codes: list[str],
    lat: float,
    lon: float,
    start: str,
    end: str | None,
    community: str,
    site_elevation: float | None,
    window_days: int,
) -> dict:
    start, end = normalize_range(start, end)
    series = _series(power, codes, lat, lon, start, end, community, site_elevation)
    anomalies_by_code = _anomalies_by_code(series, window_days)
    variables: dict[str, dict] = {}
    for code, values in anomalies_by_code.items():
        first = series[code][0]
        variables[code] = {
            "unit": first.unit,
            "time_standard": first.time_standard,
            "values": values,
        }
    return {
        "request": _request_meta(codes, lat, lon, start, end, community, site_elevation),
        "baseline_window_days": window_days,
        "variables": variables,
    }


def trends(
    power: PowerClient,
    codes: list[str],
    lat: float,
    lon: float,
    start: str,
    end: str | None,
    community: str,
    site_elevation: float | None,
    alpha: float,
) -> dict:
    start, end = normalize_range(start, end)
    series = _series(power, codes, lat, lon, start, end, community, site_elevation)
    return {
        "request": _request_meta(codes, lat, lon, start, end, community, site_elevation),
        "trends": _trends_payload(series, alpha),
    }


def correlations(
    power: PowerClient,
    eonet: EonetClient,
    codes: list[str],
    lat: float,
    lon: float,
    start: str,
    end: str | None,
    community: str,
    site_elevation: float | None,
    categories: list[str] | None,
    bbox: tuple[float, float, float, float] | None,
    status: str,
    limit: int,
    max_lag_months: int,
    method: str,
    baseline_window_days: int = 7,
    mag_id: str | None = None,
    mag_min: float | None = None,
) -> dict:
    start, end = normalize_range(start, end)
    series = _series(power, codes, lat, lon, start, end, community, site_elevation)
    anomalies_by_code = _anomalies_by_code(series, baseline_window_days)
    payload = eonet.events(
        status=status,
        category=categories,
        start=to_eonet_date(start),
        end=to_eonet_date(end),
        bbox=bbox,
        limit=limit,
        mag_id=mag_id,
        mag_min=mag_min,
    )
    events = EonetClient.parse_events(payload)
    raw = correlate_events(
        events,
        anomalies_by_code,
        start,
        end,
        max_lag_months=max_lag_months,
        method=method,
    )
    return {
        "request": _request_meta(codes, lat, lon, start, end, community, site_elevation)
        | {
            "category": categories,
            "bbox": list(bbox) if bbox else None,
            "status": status,
            "limit": limit,
            "max_lag_months": max_lag_months,
            "method": method,
        },
        "events_count": len(events),
        "correlations": _correlations_payload(raw),
    }


# -------------------------------------------------------------------- análisis
def event_analysis(
    power: PowerClient,
    eonet: EonetClient,
    event_id: str,
    codes: list[str],
    lat: float,
    lon: float,
    start: str,
    end: str | None,
    community: str,
    site_elevation: float | None,
    baseline_window_days: int,
    max_context_days: int,
) -> dict:
    event = get_event(eonet, event_id)
    start, end = normalize_range(start, end)
    series = _series(power, codes, lat, lon, start, end, community, site_elevation)
    anomalies_by_code = _anomalies_by_code(series, baseline_window_days)
    window = event_window(event, max_context_days=max_context_days)
    summaries = summarize_events(
        [event], anomalies_by_code, max_context_days=max_context_days
    )
    summary = summaries[0] if summaries else {"variables": {}}
    return {
        "request": _request_meta(codes, lat, lon, start, end, community, site_elevation)
        | {
            "event_id": event_id,
            "baseline_window_days": baseline_window_days,
            "max_context_days": max_context_days,
        },
        "event": serialize_event(event),
        "window": window.as_dict(),
        "variables": summary["variables"],
    }


def point_analysis(power: PowerClient, eonet: EonetClient, body: Any) -> dict:
    start, end = normalize_range(body.start, body.end)
    codes = validate_power_codes(body.variables)
    series = _series(power, codes, body.lat, body.lon, start, end, body.community, body.site_elevation)
    anomalies_by_code = _anomalies_by_code(series, body.baseline_window_days)
    trends_payload = _trends_payload(series, body.alpha)

    events_count = 0
    summaries: list[dict] = []
    correlations_payload: dict[str, dict] = {}
    if body.events is not None:
        payload = eonet.events(
            status=body.events.status,
            category=body.events.category,
            start=to_eonet_date(start),
            end=to_eonet_date(end),
            bbox=tuple(body.events.bbox) if body.events.bbox else None,
            limit=body.events.limit,
            mag_id=body.events.mag_id,
            mag_min=body.events.mag_min,
        )
        events = EonetClient.parse_events(payload)
        events_count = len(events)
        summaries = summarize_events(
            events, anomalies_by_code, max_context_days=body.max_context_days
        )
        raw = correlate_events(
            events,
            anomalies_by_code,
            start,
            end,
            max_lag_months=body.max_lag_months,
            method=body.correlation_method,
        )
        correlations_payload = _correlations_payload(raw)

    return {
        "request": {
            "lat": body.lat,
            "lon": body.lon,
            "variables": codes,
            "start": start,
            "end": end,
            "community": body.community,
            "site_elevation": body.site_elevation,
            "baseline_window_days": body.baseline_window_days,
            "max_context_days": body.max_context_days,
            "max_lag_months": body.max_lag_months,
            "alpha": body.alpha,
            "correlation_method": body.correlation_method,
            "events": body.events.model_dump() if body.events is not None else None,
        },
        "trends": trends_payload,
        "events_count": events_count,
        "event_summaries": summaries,
        "correlations": correlations_payload,
    }
