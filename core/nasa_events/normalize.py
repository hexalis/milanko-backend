"""Shared cleaning/normalization helpers."""
from __future__ import annotations

from datetime import date, datetime

FILL = -999.0
MONTH_LABELS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def is_fill(value, fill: float = FILL, tol: float = 1e-6) -> bool:
    """True when the value equals the API fill marker (-999 by default)."""
    try:
        return fill is not None and abs(float(value) - float(fill)) <= tol
    except (TypeError, ValueError):
        return False


def clean_value(raw, fill: float = FILL) -> tuple[float | None, str]:
    """Return (value, quality). Fill values become None with quality='fill'."""
    if raw is None:
        return None, "missing"
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, "invalid"
    if is_fill(value, fill):
        return None, "fill"
    return value, "ok"


def parse_date_key(label: str, granularity: str) -> date | datetime | None:
    """Parse POWER-style time keys into a date/datetime (naive, source time standard)."""
    label = label.strip()
    if granularity == "climatology":
        return None
    formats = {"daily": "%Y%m%d", "monthly": "%Y%m", "hourly": "%Y%m%d%H"}
    fmt = formats.get(granularity)
    if fmt is None:
        raise ValueError(f"unsupported granularity: {granularity}")
    parsed = datetime.strptime(label, fmt)
    return parsed.date() if granularity in ("daily", "monthly") else parsed


def lst_offset_hours(lon: float) -> float:
    """Approximate UTC offset of solar local time for a longitude (lon/15 h)."""
    return lon / 15.0


def month_number(label: str) -> int | None:
    """JAN..DEC -> 1..12; ANN -> None."""
    label = label.strip().upper()
    if label in MONTH_LABELS:
        return MONTH_LABELS.index(label) + 1
    return None
