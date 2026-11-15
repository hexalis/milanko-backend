"""Seasonal baselines and anomaly detection for daily climate series.

Strategy (decided 2026-10-19):
  - daily: empirical day-of-year percentiles with a ±window_days moving window
    across all years of the 2006+ record (robust to seasonality)
  - monthly: means by calendar month (and optional POWER climatology comparison)
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, datetime
from statistics import mean, pstdev

from ..models import Observation

MIN_SAMPLES = 5
MAX_DOY = 365


def normalize_doy(when: date) -> int:
    """Day of year, mapping Feb 29 to Feb 28 so all years align."""
    if when.month == 2 and when.day == 29:
        return 59
    return when.timetuple().tm_yday


def percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolation percentile (q in 0..100)."""
    if not sorted_values:
        raise ValueError("empty list")
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * q / 100.0
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    fraction = rank - low
    return sorted_values[low] * (1 - fraction) + sorted_values[high] * fraction


@dataclass(slots=True)
class DayStats:
    day_of_year: int
    n: int
    mean: float
    std: float
    p05: float
    p25: float
    p50: float
    p75: float
    p95: float


@dataclass(slots=True)
class MonthStats:
    month: int
    n: int
    mean: float
    std: float
    p05: float
    p50: float
    p95: float


class DailyBaseline:
    """Empirical day-of-year baseline computed from a daily observation series."""

    def __init__(self, window_days: int = 7):
        self.window_days = window_days
        self.samples: dict[int, list[float]] = {}
        self.days: dict[int, DayStats] = {}

    @classmethod
    def from_observations(
        cls, observations: list[Observation], window_days: int = 7
    ) -> "DailyBaseline":
        baseline = cls(window_days)
        by_doy: dict[int, list[float]] = {}
        for obs in observations:
            if obs.value is None or obs.time is None:
                continue
            when = obs.time.date() if isinstance(obs.time, datetime) else obs.time
            by_doy.setdefault(normalize_doy(when), []).append(float(obs.value))
        for target in range(1, MAX_DOY + 1):
            values: list[float] = []
            for offset in range(-window_days, window_days + 1):
                doy = (target - 1 + offset) % MAX_DOY + 1
                values.extend(by_doy.get(doy, []))
            if len(values) < MIN_SAMPLES:
                continue
            values.sort()
            baseline.samples[target] = values
            baseline.days[target] = DayStats(
                day_of_year=target,
                n=len(values),
                mean=mean(values),
                std=pstdev(values),
                p05=percentile(values, 5),
                p25=percentile(values, 25),
                p50=percentile(values, 50),
                p75=percentile(values, 75),
                p95=percentile(values, 95),
            )
        return baseline

    def stats_for(self, when: date) -> DayStats | None:
        return self.days.get(normalize_doy(when))

    def percentile_rank(self, value: float, when: date) -> float | None:
        values = self.samples.get(normalize_doy(when))
        if not values:
            return None
        return 100.0 * bisect_left(values, value) / len(values)

    def describe(self, value: float, when: date) -> dict:
        """Anomaly (vs median), z-score and empirical percentile for a value."""
        stats = self.stats_for(when)
        if stats is None:
            return {"anomaly": None, "z": None, "percentile": None, "extreme": None}
        z = (value - stats.mean) / stats.std if stats.std > 0 else None
        rank = self.percentile_rank(value, when)
        extreme = "high" if value >= stats.p95 else "low" if value <= stats.p05 else None
        return {"anomaly": value - stats.p50, "z": z, "percentile": rank, "extreme": extreme}


def monthly_means(observations: list[Observation]) -> dict[tuple[int, int], float]:
    """(year, month) -> mean of daily values."""
    buckets: dict[tuple[int, int], list[float]] = {}
    for obs in observations:
        if obs.value is None or obs.time is None:
            continue
        when = obs.time.date() if isinstance(obs.time, datetime) else obs.time
        buckets.setdefault((when.year, when.month), []).append(float(obs.value))
    return {key: mean(values) for key, values in buckets.items()}


def monthly_climatology(observations: list[Observation]) -> dict[int, MonthStats]:
    """Calendar-month statistics across the whole series (1..12 -> MonthStats)."""
    buckets: dict[int, list[float]] = {}
    for obs in observations:
        if obs.value is None or obs.time is None:
            continue
        when = obs.time.date() if isinstance(obs.time, datetime) else obs.time
        buckets.setdefault(when.month, []).append(float(obs.value))
    result: dict[int, MonthStats] = {}
    for month, values in buckets.items():
        if len(values) < MIN_SAMPLES:
            continue
        values.sort()
        result[month] = MonthStats(
            month=month,
            n=len(values),
            mean=mean(values),
            std=pstdev(values),
            p05=percentile(values, 5),
            p50=percentile(values, 50),
            p95=percentile(values, 95),
        )
    return result
