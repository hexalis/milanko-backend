"""Unit tests for seasonal baselines and anomalies."""
import math
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from core.nasa_events.analysis.baseline import (  # noqa: E402
    DailyBaseline,
    monthly_climatology,
    monthly_means,
    normalize_doy,
)
from core.nasa_events.models import Observation  # noqa: E402


def build_series(start_year: int = 2010, years: int = 10) -> list[Observation]:
    observations = []
    day = date(start_year, 1, 1)
    end = date(start_year + years, 1, 1)
    while day < end:
        doy = day.timetuple().tm_yday
        value = 10 + 5 * math.sin(2 * math.pi * doy / 365)
        observations.append(
            Observation(
                source="POWER",
                code="T2M",
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


class BaselineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observations = build_series()
        cls.baseline = DailyBaseline.from_observations(cls.observations, window_days=7)

    def test_extreme_high(self):
        info = self.baseline.describe(50.0, date(2015, 7, 1))
        self.assertEqual(info["extreme"], "high")
        self.assertGreater(info["z"], 2)
        self.assertGreater(info["percentile"], 99)

    def test_normal_value(self):
        when = date(2015, 7, 1)
        doy = when.timetuple().tm_yday
        typical = 10 + 5 * math.sin(2 * math.pi * doy / 365)
        info = self.baseline.describe(typical, when)
        self.assertLess(abs(info["z"]), 1.0)
        self.assertIsNone(info["extreme"])

    def test_leap_day_mapping(self):
        self.assertEqual(normalize_doy(date(2024, 2, 29)), 59)
        self.assertIsNotNone(self.baseline.stats_for(date(2024, 2, 29)))

    def test_monthly_means(self):
        means = monthly_means(build_series(years=2))
        self.assertEqual(len(means), 24)
        self.assertIn((2010, 1), means)

    def test_monthly_climatology(self):
        climatology = monthly_climatology(self.observations)
        self.assertEqual(set(climatology), set(range(1, 13)))
        # synthetic series peaks around April (doy ~91)
        self.assertGreater(climatology[4].mean, climatology[1].mean)


if __name__ == "__main__":
    unittest.main()
