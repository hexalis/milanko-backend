"""Canonical data models for normalized observations and events."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(slots=True)
class Observation:
    """A single normalized value (one variable, one time, one place)."""

    source: str
    code: str
    value: float | None
    unit: str | None
    time: date | datetime | None
    time_label: str
    time_standard: str
    lat: float | None = None
    lon: float | None = None
    granularity: str = "daily"
    quality: str = "ok"  # ok | fill | missing | invalid | blank
    meta: dict = field(default_factory=dict)


@dataclass(slots=True)
class EventGeometry:
    date: datetime
    geometry_type: str
    coordinates: list
    magnitude_value: float | None = None
    magnitude_unit: str | None = None


@dataclass(slots=True)
class Event:
    id: str
    title: str
    description: str | None
    link: str
    closed: datetime | None
    categories: list[str]
    sources: list[dict]
    geometry: list[EventGeometry]

    @property
    def first_date(self) -> datetime | None:
        return min((g.date for g in self.geometry), default=None)

    @property
    def duration_days(self) -> float | None:
        if self.closed and self.first_date:
            return (self.closed - self.first_date).total_seconds() / 86400
        return None


@dataclass(slots=True)
class EventFeature:
    """One observation row from EONET's GeoJSON endpoint (one feature per date)."""

    event_id: str
    title: str
    date: datetime | None
    geometry_type: str
    coordinates: list
    magnitude_value: float | None = None
    magnitude_unit: str | None = None
    categories: list[str] = field(default_factory=list)
