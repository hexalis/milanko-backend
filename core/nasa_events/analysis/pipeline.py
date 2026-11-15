"""High-level analysis pipeline (Fase 2).

Combines:
  - daily POWER series (cached, chunked)
  - empirical day-of-year anomalies
  - monthly trends (Mann-Kendall + Sen)
  - adaptive event windows and event-centred anomaly summaries
  - lagged correlations between monthly event counts and monthly anomaly z-scores (FDR-corrected)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from statistics import mean

from ..models import Event, Observation
from ..sources.power import PowerClient
from .baseline import DailyBaseline, monthly_means
from .stats import benjamini_hochberg, lagged_correlations, mann_kendall, sen_slope
from .windows import event_window


@dataclass(slots=True)
class AnalysisConfig:
    lat: float
    lon: float
    variables: list[str]
    start: str = "20060101"
    end: str | None = None
    community: str = "RE"
    site_elevation: float | None = None
    baseline_window_days: int = 7
    max_context_days: int = 90
    max_lag_months: int = 6
    correlation_method: str = "spearman"

    def end_date(self) -> str:
        return self.end or date.today().strftime("%Y%m%d")

    def as_dict(self) -> dict:
        return {
            "lat": self.lat,
            "lon": self.lon,
            "variables": list(self.variables),
            "start": self.start,
            "end": self.end_date(),
            "community": self.community,
            "baseline_window_days": self.baseline_window_days,
            "max_context_days": self.max_context_days,
            "max_lag_months": self.max_lag_months,
            "correlation_method": self.correlation_method,
        }


def daily_series(
    client: PowerClient,
    variables: list[str],
    lat: float,
    lon: float,
    start: str,
    end: str,
    *,
    community: str | None = None,
    site_elevation: float | None = None,
    temporal: str = "daily",
) -> dict[str, list[Observation]]:
    if temporal == "monthly":
        # POWER's monthly endpoint takes years, while the API keeps YYYYMMDD.
        start, end = start[:4], end[:4]
    observations = client.point(
        variables,
        lat,
        lon,
        start,
        end,
        temporal=temporal,
        community=community,
        site_elevation=site_elevation,
    )
    series: dict[str, list[Observation]] = {}
    for observation in observations:
        series.setdefault(observation.code, []).append(observation)
    for values in series.values():
        values.sort(key=lambda item: item.time)
    return series


def anomaly_series(observations: list[Observation], window_days: int = 7) -> list[dict]:
    baseline = DailyBaseline.from_observations(observations, window_days)
    result: list[dict] = []
    for observation in observations:
        if observation.value is None or observation.time is None:
            continue
        when = (
            observation.time.date()
            if isinstance(observation.time, datetime)
            else observation.time
        )
        info = baseline.describe(observation.value, when)
        result.append({"time": when.isoformat(), "value": observation.value, **info})
    return result


def trends_by_variable(
    series: dict[str, list[Observation]], alpha: float = 0.05
) -> dict[str, dict]:
    """Trends on seasonally adjusted monthly anomalies (month-of-year removed)."""
    trends: dict[str, dict] = {}
    for code, observations in series.items():
        monthly = monthly_means(observations)
        if len(monthly) < 12:
            trends[code] = {
                "n_months": len(monthly),
                "seasonally_adjusted": True,
                "mann_kendall": None,
                "sen_slope_per_month": None,
                "sen_slope_per_year": None,
            }
            continue
        by_month: dict[int, list[float]] = {}
        for (year, month), value in monthly.items():
            by_month.setdefault(month, []).append(value)
        month_climatology = {month: mean(values) for month, values in by_month.items()}
        ordered_keys = sorted(monthly)
        anomaly_values = [
            monthly[key] - month_climatology[key[1]] for key in ordered_keys
        ]
        mk = mann_kendall(anomaly_values, alpha=alpha)
        slope = sen_slope(anomaly_values)
        trends[code] = {
            "n_months": len(anomaly_values),
            "seasonally_adjusted": True,
            "month_climatology": month_climatology,
            "mann_kendall": mk,
            "sen_slope_per_month": slope,
            "sen_slope_per_year": slope * 12 if slope is not None else None,
        }
    return trends


def summarize_events(
    events: list[Event],
    anomalies_by_variable: dict[str, list[dict]],
    *,
    max_context_days: int = 90,
    reference_date: date | None = None,
) -> list[dict]:
    summaries: list[dict] = []
    for event in events:
        try:
            window = event_window(
                event, reference_date=reference_date, max_context_days=max_context_days
            )
        except ValueError:
            continue
        per_variable: dict[str, dict] = {}
        for code, anomalies in anomalies_by_variable.items():
            in_window = [
                item
                for item in anomalies
                if window.start.isoformat() <= item["time"] <= window.end.isoformat()
            ]
            if not in_window:
                continue
            z_values = [item["z"] for item in in_window if item["z"] is not None]
            anomaly_values = [
                item["anomaly"] for item in in_window if item["anomaly"] is not None
            ]
            extremes = sum(1 for item in in_window if item.get("extreme"))
            per_variable[code] = {
                "n_days": len(in_window),
                "mean_anomaly": mean(anomaly_values) if anomaly_values else None,
                "mean_z": mean(z_values) if z_values else None,
                "extreme_fraction": extremes / len(in_window),
            }
        summaries.append(
            {
                "event_id": event.id,
                "title": event.title,
                "categories": event.categories,
                "window": window.as_dict(),
                "variables": per_variable,
            }
        )
    return summaries


def _parse_ymd(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def _month_range(start: str, end: str) -> list[tuple[int, int]]:
    stop = _parse_ymd(end)
    year, month = _parse_ymd(start).year, _parse_ymd(start).month
    months: list[tuple[int, int]] = []
    while (year, month) <= (stop.year, stop.month):
        months.append((year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def monthly_event_counts(
    events: list[Event], start: str, end: str
) -> dict[tuple[int, int], int]:
    start_date = _parse_ymd(start)
    end_date = _parse_ymd(end)
    counts: dict[tuple[int, int], int] = {}
    for event in events:
        first = event.first_date
        if first is None:
            continue
        when = first.date() if isinstance(first, datetime) else first
        if start_date <= when <= end_date:
            key = (when.year, when.month)
            counts[key] = counts.get(key, 0) + 1
    return counts


def correlate_events(
    events: list[Event],
    anomalies_by_variable: dict[str, list[dict]],
    start: str,
    end: str,
    *,
    max_lag_months: int = 6,
    method: str = "spearman",
) -> dict[str, list[dict]]:
    """Correlate monthly event counts with monthly mean anomaly z-scores.

    Positive lag = anomalies lead events by `lag` months.
    """
    months = _month_range(start, end)
    counts = monthly_event_counts(events, start, end)
    results: dict[str, list[dict]] = {}
    for code, anomalies in anomalies_by_variable.items():
        z_by_month: dict[tuple[int, int], list[float]] = {}
        for item in anomalies:
            if item.get("z") is None:
                continue
            key = (int(item["time"][0:4]), int(item["time"][5:7]))
            z_by_month.setdefault(key, []).append(item["z"])
        monthly_z = {key: mean(values) for key, values in z_by_month.items()}
        x_values: list[float] = []
        y_values: list[float] = []
        for month in months:
            if month in monthly_z:
                x_values.append(float(counts.get(month, 0)))
                y_values.append(monthly_z[month])
        rows = lagged_correlations(x_values, y_values, max_lag=max_lag_months, method=method)
        qvalues = benjamini_hochberg(
            [row["p"] if row["p"] is not None else 1.0 for row in rows]
        )
        for row, qvalue in zip(rows, qvalues):
            row["q"] = qvalue
        results[code] = rows
    return results


def run_point_analysis(
    config: AnalysisConfig,
    events: list[Event] | None = None,
    *,
    client: PowerClient | None = None,
    reference_date: date | None = None,
) -> dict:
    client = client or PowerClient(
        community=config.community, site_elevation=config.site_elevation
    )
    series = daily_series(
        client,
        config.variables,
        config.lat,
        config.lon,
        config.start,
        config.end_date(),
        community=config.community,
        site_elevation=config.site_elevation,
    )
    anomalies = {
        code: anomaly_series(observations, config.baseline_window_days)
        for code, observations in series.items()
    }
    result: dict = {
        "config": config.as_dict(),
        "trends": trends_by_variable(series),
        "anomalies": anomalies,
    }
    if events:
        result["event_summaries"] = summarize_events(
            events,
            anomalies,
            max_context_days=config.max_context_days,
            reference_date=reference_date,
        )
        result["correlations"] = correlate_events(
            events,
            anomalies,
            config.start,
            config.end_date(),
            max_lag_months=config.max_lag_months,
            method=config.correlation_method,
        )
    return result
