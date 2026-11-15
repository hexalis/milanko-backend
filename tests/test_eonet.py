"""Unit tests for the EONET client/parsers using real Fase 0 fixtures."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "tests" / "fixtures"

from core.nasa_events.sources.eonet import EonetApiError, EonetClient  # noqa: E402


class EonetParseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events_payload = json.loads(
            (SAMPLES / "eonet" / "events_open_10.json").read_text(encoding="utf-8")
        )
        cls.geojson_payload = json.loads(
            (SAMPLES / "eonet" / "events_geojson_10.json").read_text(encoding="utf-8")
        )
        cls.closed_payload = json.loads(
            (SAMPLES / "eonet" / "events_bbox_chile.json").read_text(encoding="utf-8")
        )

    def test_events(self):
        events = EonetClient.parse_events(self.events_payload)
        self.assertEqual(len(events), 10)
        first = events[0]
        self.assertTrue(first.id)
        self.assertTrue(first.categories)
        self.assertTrue(first.geometry)
        self.assertIsNotNone(first.geometry[0].date.tzinfo)

    def test_closed_event_duration(self):
        events = EonetClient.parse_events(self.closed_payload)
        closed = [event for event in events if event.closed is not None]
        self.assertTrue(closed)
        self.assertIsNotNone(closed[0].duration_days)
        self.assertGreaterEqual(closed[0].duration_days, 0)

    def test_geojson(self):
        features = EonetClient.parse_geojson(self.geojson_payload)
        self.assertEqual(len(features), 19)
        first = features[0]
        self.assertTrue(first.event_id)
        self.assertTrue(first.categories)
        self.assertIsNotNone(first.date)

    def test_error_raises(self):
        body = b"<!DOCTYPE html><html><title>Server Error</title></html>"
        with self.assertRaises(EonetApiError):
            EonetClient.raise_for_status(500, body, "https://eonet.example/events/BAD")

    def test_bad_geojson(self):
        with self.assertRaises(EonetApiError):
            EonetClient.parse_geojson({"type": "Feature"})


if __name__ == "__main__":
    unittest.main()
