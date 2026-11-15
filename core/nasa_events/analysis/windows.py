"""Adaptive event analysis windows (category-aware).

Instead of a fixed 90-day window, each event gets a window that depends on:
  - category profile (slow-onset events get more context: drought, sea ice)
  - event duration (long events scale the context, capped by max_context_days)
  - a hard cap of 90 days per side (default, configurable)
The resulting window never extends beyond the reference date (today by default).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from ..models import Event

CATEGORY_PROFILES: dict[str, dict[str, int]] = {
    "drought": {"lead": 60, "lag": 30},
    "dustHaze": {"lead": 14, "lag": 14},
    "earthquakes": {"lead": 7, "lag": 7},
    "floods": {"lead": 15, "lag": 30},
    "landslides": {"lead": 15, "lag": 30},
    "manmade": {"lead": 7, "lag": 14},
    "seaLakeIce": {"lead": 45, "lag": 30},
    "severeStorms": {"lead": 10, "lag": 21},
    "snow": {"lead": 10, "lag": 21},
    "tempExtremes": {"lead": 10, "lag": 10},
    "volcanoes": {"lead": 7, "lag": 21},
    "waterColor": {"lead": 21, "lag": 30},
    "wildfires": {"lead": 14, "lag": 21},
    "default": {"lead": 14, "lag": 21},
}


@dataclass(slots=True)
class AnalysisWindow:
    start: date
    end: date
    lead_days: int
    lag_days: int
    event_start: date
    event_end: date
    duration_days: int
    profile: str
    rationale: str

    def as_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "lead_days": self.lead_days,
            "lag_days": self.lag_days,
            "event_start": self.event_start.isoformat(),
            "event_end": self.event_end.isoformat(),
            "duration_days": self.duration_days,
            "profile": self.profile,
            "rationale": self.rationale,
        }


def _event_dates(event: Event) -> tuple[date, date]:
    dates: list[date] = []
    for geometry in event.geometry:
        if geometry.date is None:
            continue
        dates.append(
            geometry.date.date() if isinstance(geometry.date, datetime) else geometry.date
        )
    if not dates:
        raise ValueError(f"event {event.id} has no dated geometries")
    start = min(dates)
    last_observed = max(dates)
    end = event.closed.date() if event.closed else last_observed
    if end < start:
        end = start
    return start, end


def event_window(
    event: Event,
    *,
    reference_date: date | None = None,
    max_context_days: int = 90,
) -> AnalysisWindow:
    reference = reference_date or date.today()
    event_start, event_end = _event_dates(event)
    duration = (event_end - event_start).days + 1
    profile_name = next(
        (category for category in event.categories if category in CATEGORY_PROFILES),
        "default",
    )
    profile = CATEGORY_PROFILES[profile_name]
    scale = max(1.0, duration / 30.0)
    lead = min(round(profile["lead"] * scale), max_context_days)
    lag = min(round(profile["lag"] * scale), max_context_days)
    start = event_start - timedelta(days=lead)
    end = event_end + timedelta(days=lag)
    if end > reference:
        end = reference
    rationale = (
        f"perfil '{profile_name}': lead base={profile['lead']}d, lag base={profile['lag']}d; "
        f"duración={duration}d -> lead={lead}d, lag={lag}d (máx contexto {max_context_days}d)"
    )
    return AnalysisWindow(
        start=start,
        end=end,
        lead_days=lead,
        lag_days=lag,
        event_start=event_start,
        event_end=event_end,
        duration_days=duration,
        profile=profile_name,
        rationale=rationale,
    )


def fixed_window(
    event: Event,
    *,
    days: int = 90,
    reference_date: date | None = None,
) -> AnalysisWindow:
    """Uniform ±days window (useful as a comparable baseline across categories)."""
    reference = reference_date or date.today()
    event_start, event_end = _event_dates(event)
    start = event_start - timedelta(days=days)
    end = min(event_end + timedelta(days=days), reference)
    return AnalysisWindow(
        start=start,
        end=end,
        lead_days=days,
        lag_days=days,
        event_start=event_start,
        event_end=event_end,
        duration_days=(event_end - event_start).days + 1,
        profile="fixed",
        rationale=f"ventana fija ±{days}d",
    )
