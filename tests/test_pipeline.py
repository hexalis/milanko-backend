"""End-to-end tests of the analysis pipeline with synthetic series."""
import math
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from core.nasa_events.analysis.pipeline import (  # noqa: E402
    anomaly_series,
    correlate_events,
    monthly_event_counts,
    summarize_events,
    trends_by_variable,
)
from core.nasa_events.models import Event, EventGeometry, Observation  # noqa: E402


def build_series(code: str = "T2M", start: date = date(2006, 1, 1), years: int = 10):
    observations = []
    day = start
    end = date(start.year + years, 1, 1)
    while day < end:
        doy = day.timetuple().tm_yday
        value = (day.year - start.year) * 0.1 + 10 + 3 * math.sin(2 * math.pi * doy / 365)
        observations.append(
            Observation(
                source="POWER",
                code=code,
                value=value,
                unit="C",
                time=day,
                time_label=day.strftime("%Y%m%d"),
                time_standard="LST",
                granularity="daily",
            )
        )
        day += timedelta(days=1)
    return observations


def make_event(day: date, categories=("wildfires",)) -> Event:
    return Event(
        id="EONET_TEST",
        title="test",
        description=None,
        link="",
        closed=None,
        categories=list(categories),
        sources=[],
        geometry=[
            EventGeometry(
                date=datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
                geometry_type="Point",
                coordinates=[0.0, 0.0],
            )
        ],
    )


class PipelineTest(unittest.TestCase):
    def test_trends_detect_increase(self):
        trends = trends_by_variable({"T2M": build_series()})
        result = trends["T2M"]
        self.assertEqual(result["mann_kendall"]["trend"], "increasing")
        self.assertGreater(result["sen_slope_per_year"], 0.05)
        self.assertTrue(result["seasonally_adjusted"])

    def test_anomalies_centered(self):
        anomalies = anomaly_series(build_series())
        z_values = [item["z"] for item in anomalies if item["z"] is not None]
        self.assertGreater(len(z_values), 3000)
        self.assertLess(abs(sum(z_values) / len(z_values)), 0.2)

    def test_event_summary(self):
        anomalies = {"T2M": anomaly_series(build_series())}
        event = make_event(date(2010, 1, 15))
        summaries = summarize_events([event], anomalies, reference_date=date(2010, 12, 31))
        self.assertEqual(len(summaries), 1)
        self.assertIn("T2M", summaries[0]["variables"])
        window = summaries[0]["window"]
        self.assertEqual(window["profile"], "wildfires")
        self.assertGreater(window["lead_days"], 0)

    def test_monthly_counts(self):
        event = make_event(date(2010, 1, 15))
        counts = monthly_event_counts([event], "20060101", "20101231")
        self.assertEqual(counts[(2010, 1)], 1)

    def test_correlations_shape(self):
        anomalies = {"T2M": anomaly_series(build_series())}
        event = make_event(date(2010, 1, 15))
        correlations = correlate_events(
            [event], anomalies, "20060101", "20151231", max_lag_months=3
        )
        self.assertEqual(len(correlations["T2M"]), 7)
        self.assertIn("q", correlations["T2M"][0])


if __name__ == "__main__":
    unittest.main()
