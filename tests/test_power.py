"""Unit tests for the POWER client/parsers using real Fase 0 fixtures."""
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "tests" / "fixtures"

from core.nasa_events.sources.power import PowerApiError, PowerClient  # noqa: E402


class PowerParseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(
            (SAMPLES / "power" / "point_daily_re_2026.json").read_text(encoding="utf-8")
        )

    def test_point_daily(self):
        observations = PowerClient.parse_point_payload(self.payload, "daily")
        self.assertTrue(observations)
        codes = {o.code for o in observations}
        self.assertIn("T2M", codes)
        t2m = [o for o in observations if o.code == "T2M"]
        self.assertEqual(len(t2m), 286)
        self.assertEqual(t2m[0].time, date(2026, 1, 1))
        self.assertEqual(t2m[0].unit, "C")
        self.assertEqual(t2m[0].time_standard, "LST")
        self.assertEqual(t2m[0].granularity, "daily")
        self.assertIsNotNone(t2m[0].lat)
        self.assertIsNotNone(t2m[0].lon)

    def test_fill_becomes_none(self):
        t2m = [
            o
            for o in PowerClient.parse_point_payload(self.payload, "daily")
            if o.code == "T2M"
        ]
        self.assertIsNone(t2m[-1].value)
        self.assertEqual(t2m[-1].quality, "fill")

    def test_monthly_skips_annual_aggregate(self):
        payload = {
            "properties": {"parameter": {"T2M": {"202401": 1.0, "202402": 2.0, "202413": 3.0}}},
            "parameters": {"T2M": {"units": "C"}},
            "header": {"fill_value": -999.0, "time_standard": "LST"},
            "geometry": {"coordinates": [-70.66, -33.45, 0]},
        }
        observations = PowerClient.parse_point_payload(payload, "monthly")
        self.assertEqual([o.time_label for o in observations], ["202401", "202402"])

    def test_regional(self):
        payload = json.loads(
            (SAMPLES / "power" / "regional_daily_3deg.json").read_text(encoding="utf-8")
        )
        observations = PowerClient.parse_regional_payload(payload, "daily")
        self.assertEqual(len(observations), 35 * 3)
        self.assertEqual({o.code for o in observations}, {"T2M"})
        self.assertAlmostEqual(observations[0].lat, -35.0)

    def test_climatology(self):
        payload = json.loads(
            (SAMPLES / "power" / "point_climatology_ag.json").read_text(encoding="utf-8")
        )
        observations = PowerClient.parse_point_payload(payload, "climatology")
        labels = {o.time_label for o in observations}
        self.assertIn("JAN", labels)
        self.assertIn("ANN", labels)
        self.assertIsNone(observations[0].time)

    def test_error_payload(self):
        payload = json.loads(
            (SAMPLES / "power" / "error_invalid_param.json").read_text(encoding="utf-8")
        )
        with self.assertRaises(PowerApiError) as ctx:
            PowerClient.parse_point_payload(payload, "daily")
        self.assertIn("FOO_XYZ", str(ctx.exception))

    def test_date_validation(self):
        with self.assertRaises(ValueError):
            PowerClient.validate_dates("monthly", "202601", "202609")
        PowerClient.validate_dates("monthly", "2024", "2026")
        PowerClient.validate_dates("daily", "20260101", "20260131")

    def test_psc_requires_elevation(self):
        client = PowerClient(use_cache=False)
        with self.assertRaises(ValueError):
            client.point_payloads(
                ["PSC"], -33.45, -70.66, "20260101", "20260102", site_elevation=None
            )

    def test_regional_span_validation(self):
        client = PowerClient(use_cache=False)
        with self.assertRaises(ValueError):
            client.regional(
                "T2M",
                lat_min=-34.0,
                lat_max=-33.0,
                lon_min=-71.0,
                lon_max=-70.0,
                start="20260101",
                end="20260102",
            )


if __name__ == "__main__":
    unittest.main()
