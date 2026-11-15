"""Unit tests for the FIRMS parser using a real Fase 0 fixture."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "tests" / "fixtures"

from core.nasa_events.sources.firms import FirmsApiError, FirmsClient  # noqa: E402


class FirmsParseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (SAMPLES / "complements" / "firms_area_chile_5d.csv").read_text(
            encoding="utf-8"
        )

    def test_parse_area_csv(self):
        detections = FirmsClient.parse_csv(self.text)
        self.assertGreaterEqual(len(detections), 250)
        first = detections[0]
        self.assertAlmostEqual(first.lat, -19.11391, places=4)
        self.assertAlmostEqual(first.lon, -66.54945, places=4)
        self.assertEqual(first.acq_time, datetime(2026, 10, 15, 4, 55, tzinfo=timezone.utc))
        self.assertIsNotNone(first.confidence)
        self.assertEqual(first.daynight, "N")

    def test_day_range_limit(self):
        client = FirmsClient(map_key="dummy", use_cache=False)
        with self.assertRaises(ValueError):
            client.area_csv(day_range=7)

    def test_missing_key(self):
        client = FirmsClient(map_key="", use_cache=False)
        with self.assertRaises(FirmsApiError):
            client.area_csv(day_range=1)


if __name__ == "__main__":
    unittest.main()
