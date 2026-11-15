"""Fase 2 — analysis: baselines, adaptive windows, trend/correlation stats."""
from __future__ import annotations

from .baseline import DailyBaseline, DayStats, MonthStats, monthly_climatology, monthly_means
from .pipeline import (
    AnalysisConfig,
    anomaly_series,
    correlate_events,
    daily_series,
    monthly_event_counts,
    summarize_events,
    trends_by_variable,
)
from .stats import (
    benjamini_hochberg,
    lagged_correlations,
    mann_kendall,
    pearson,
    sen_slope,
    spearman,
)
from .windows import CATEGORY_PROFILES, AnalysisWindow, event_window, fixed_window

__all__ = [
    "AnalysisConfig",
    "AnalysisWindow",
    "CATEGORY_PROFILES",
    "DailyBaseline",
    "DayStats",
    "MonthStats",
    "anomaly_series",
    "benjamini_hochberg",
    "correlate_events",
    "daily_series",
    "event_window",
    "fixed_window",
    "lagged_correlations",
    "mann_kendall",
    "monthly_climatology",
    "monthly_event_counts",
    "monthly_means",
    "pearson",
    "sen_slope",
    "spearman",
    "summarize_events",
    "trends_by_variable",
]
