"""Unit tests for adaptive event windows."""
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from core.nasa_events.analysis.windows import CATEGORY_PROFILES, event_window, fixed_window  # noqa: E402
from core.nasa_events.models import Event, EventGeometry  # noqa: E402


def make_event(categories, dates, closed=None) -> Event:
    geometry = [
        EventGeometry(
            date=datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
            geometry_type="Point",
            coordinates=[0.0, 0.0],
        )
        for day in dates
    ]
    return Event(
        id="EONET_TEST",
        title="test",
        description=None,
        link="",
        closed=closed,
        categories=categories,
        sources=[],
        geometry=geometry,
    )


class WindowsTest(unittest.TestCase):
    def test_wildfire_short_event(self):
        event = make_event(["wildfires"], [date(2026, 10, 10)])
        window = event_window(event, reference_date=date(2026, 10, 19))
        self.assertEqual(window.lead_days, 14)
        self.assertEqual(window.lag_days, 21)
        self.assertEqual(window.start, date(2026, 9, 26))
        self.assertEqual(window.end, date(2026, 10, 19))  # clamped to reference

    def test_drought_long_event_capped(self):
        event = make_event(
            ["drought"],
            [date(2026, 1, 1), date(2026, 4, 30)],
            closed=datetime(2026, 4, 30, tzinfo=timezone.utc),
        )
        window = event_window(event, reference_date=date(2026, 10, 19))
        self.assertEqual(window.duration_days, 120)
        self.assertEqual(window.lead_days, 90)  # capped at max_context_days
        self.assertEqual(window.lag_days, 90)

    def test_unknown_category_uses_default(self):
        event = make_event(["notARealCategory"], [date(2026, 5, 1)])
        window = event_window(event, reference_date=date(2026, 5, 31))
        self.assertEqual(window.profile, "default")
        self.assertEqual(window.lead_days, CATEGORY_PROFILES["default"]["lead"])

    def test_fixed_window(self):
        event = make_event(["wildfires"], [date(2026, 10, 10)])
        window = fixed_window(event, days=30, reference_date=date(2026, 10, 19))
        self.assertEqual(window.start, date(2026, 9, 10))
        self.assertEqual(window.end, date(2026, 10, 19))
        self.assertEqual(window.profile, "fixed")


if __name__ == "__main__":
    unittest.main()
