"""Unit tests for normalization helpers."""
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from core.nasa_events.normalize import (  # noqa: E402
    clean_value,
    is_fill,
    lst_offset_hours,
    month_number,
    parse_date_key,
)


class NormalizeTest(unittest.TestCase):
    def test_fill(self):
        self.assertTrue(is_fill(-999.0))
        self.assertTrue(is_fill("-999"))
        self.assertFalse(is_fill(0.0))
        self.assertEqual(clean_value(-999.0), (None, "fill"))
        self.assertEqual(clean_value("12.5"), (12.5, "ok"))
        self.assertEqual(clean_value(None), (None, "missing"))
        self.assertEqual(clean_value("abc"), (None, "invalid"))

    def test_parse_keys(self):
        self.assertEqual(parse_date_key("20260101", "daily"), date(2026, 1, 1))
        self.assertEqual(parse_date_key("202601", "monthly"), date(2026, 1, 1))
        self.assertEqual(parse_date_key("2026010112", "hourly"), datetime(2026, 1, 1, 12))
        self.assertIsNone(parse_date_key("JAN", "climatology"))
        with self.assertRaises(ValueError):
            parse_date_key("2026-01-01", "daily")

    def test_lst_offset(self):
        self.assertAlmostEqual(lst_offset_hours(-70.66), -4.710666, places=4)

    def test_month_number(self):
        self.assertEqual(month_number("JAN"), 1)
        self.assertEqual(month_number("DEC"), 12)
        self.assertIsNone(month_number("ANN"))


if __name__ == "__main__":
    unittest.main()
