"""Unit tests for the AERONET parser using a real Fase 0 fixture."""
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "tests" / "fixtures"

from core.nasa_events.sources.aeronet import AeronetClient, AeronetError  # noqa: E402


class AeronetParseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (SAMPLES / "complements" / "aeronet_gsfc_2026sep_oct.csv").read_text(
            encoding="utf-8", errors="replace"
        )

    def test_parse_records(self):
        records = AeronetClient.parse(self.text)
        self.assertGreater(len(records), 1500)
        first = records[0]
        self.assertEqual(first.site, "GSFC")
        self.assertEqual(first.datetime, datetime(2026, 9, 1, 11, 23, 35))
        self.assertAlmostEqual(first.values["AOD_1640nm"], 0.035325, places=6)
        self.assertIn("AOD_1020nm", first.values)

    def test_fill_is_none(self):
        records = AeronetClient.parse(self.text)
        self.assertTrue(any(value is None for value in records[0].values.values()))

    def test_bad_text(self):
        with self.assertRaises(AeronetError):
            AeronetClient.parse("<html>no data</html>")


if __name__ == "__main__":
    unittest.main()
