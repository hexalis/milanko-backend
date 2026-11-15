"""API tests with fake NASA clients (no network)."""
from __future__ import annotations

import math
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from api.app import app  # noqa: E402
from api.deps import get_eonet_client, get_power_client  # noqa: E402
from core.nasa_events.models import Observation  # noqa: E402

EVENT = {
    "id": "EONET_TEST",
    "title": "Test wildfire",
    "description": None,
    "link": "https://example.test/event",
    "closed": None,
    "categories": [{"id": "wildfires", "title": "Wildfires"}],
    "sources": [{"id": "TEST", "url": "https://example.test/source"}],
    "geometry": [
        {
            "magnitudeValue": 10.0,
            "magnitudeUnit": "acres",
            "date": "2011-06-15T00:00:00Z",
            "type": "Point",
            "coordinates": [0.0, 0.0],
        }
    ],
}


class FakePowerClient:
    def point(self, codes, lat, lon, start, end, **kwargs):
        observations = []
        if kwargs.get("temporal") == "monthly":
            month = date(2010, 1, 1)
            stop_month = date(2013, 1, 1)
            while month < stop_month:
                for index, code in enumerate(codes):
                    observations.append(
                        Observation(
                            source="POWER",
                            code=code,
                            value=10 + index + (month.year - 2010) * 0.1 + month.month * 0.01,
                            unit="C",
                            time=month,
                            time_label=month.strftime("%Y%m"),
                            time_standard="LST",
                            granularity="monthly",
                            lat=lat,
                            lon=lon,
                        )
                    )
                month = date(month.year + (month.month == 12), (month.month % 12) + 1, 1)
            return observations
        day = date(2010, 1, 1)
        stop = date(2013, 1, 1)
        while day < stop:
            doy = day.timetuple().tm_yday
            for index, code in enumerate(codes):
                value = 10 + index + 3 * math.sin(2 * math.pi * doy / 365) + (day.year - 2010) * 0.1
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
                        lat=lat,
                        lon=lon,
                    )
                )
            day += timedelta(days=1)
        return observations


class FakeEonetClient:
    def categories(self):
        return {"categories": [{"id": "wildfires", "title": "Wildfires"}]}

    def events(self, **kwargs):
        return {"events": [EVENT]}

    def event(self, event_id):
        return EVENT


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.dependency_overrides[get_power_client] = lambda: FakePowerClient()
        app.dependency_overrides[get_eonet_client] = lambda: FakeEonetClient()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["core_variables"], 80)

    def test_catalog_variables(self):
        response = self.client.get("/catalog/variables")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 208)
        power_only = self.client.get("/catalog/variables", params={"source": "NASA POWER"})
        self.assertEqual(power_only.json()["count"], 153)

    def test_catalog_variable_detail(self):
        response = self.client.get("/catalog/variables/T2M")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["disposition"], "nucleo")
        self.assertEqual(self.client.get("/catalog/variables/NOPE").status_code, 404)

    def test_event_categories(self):
        response = self.client.get("/catalog/events/categories")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["categories"][0]["id"], "wildfires")

    def test_events(self):
        response = self.client.get(
            "/events", params={"category": "wildfires", "status": "all", "limit": 10}
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["events"][0]["id"], "EONET_TEST")
        self.assertEqual(body["events"][0]["categories"], ["wildfires"])

    def test_event_detail(self):
        response = self.client.get("/events/EONET_TEST")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["n_geometries"], 1)

    def test_observations(self):
        response = self.client.get(
            "/observations",
            params={
                "variables": "T2M,RH2M",
                "lat": -33.45,
                "lon": -70.66,
                "start": "20100101",
                "end": "20121231",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body["variables"]), {"T2M", "RH2M"})
        self.assertEqual(len(body["variables"]["T2M"]["values"]), 1096)
        self.assertEqual(body["variables"]["T2M"]["unit"], "C")
        self.assertEqual(body["variables"]["T2M"]["time_standard"], "LST")

    def test_observations_monthly(self):
        response = self.client.get(
            "/observations",
            params={
                "variables": "T2M",
                "lat": -33.45,
                "lon": -70.66,
                "start": "20100101",
                "end": "20121231",
                "granularity": "monthly",
            },
        )
        self.assertEqual(response.status_code, 200)
        series = response.json()["variables"]["T2M"]
        self.assertEqual(series["granularity"], "monthly")
        self.assertEqual(len(series["values"]), 36)

    def test_observations_unknown_variable(self):
        response = self.client.get(
            "/observations",
            params={"variables": "FOO", "lat": 0, "lon": 0, "start": "20100101", "end": "20100105"},
        )
        self.assertEqual(response.status_code, 422)

    def test_anomalies(self):
        response = self.client.get(
            "/anomalies",
            params={
                "variables": "T2M",
                "lat": -33.45,
                "lon": -70.66,
                "start": "20100101",
                "end": "20121231",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["baseline_window_days"], 7)
        point = body["variables"]["T2M"]["values"][0]
        self.assertIn("z", point)
        self.assertIn("extreme", point)

    def test_trends(self):
        response = self.client.get(
            "/trends",
            params={
                "variables": "T2M",
                "lat": -33.45,
                "lon": -70.66,
                "start": "20100101",
                "end": "20121231",
            },
        )
        self.assertEqual(response.status_code, 200)
        trend = response.json()["trends"]["T2M"]
        self.assertEqual(trend["mann_kendall"]["trend"], "increasing")
        self.assertGreater(trend["sen_slope_per_year"], 0)

    def test_correlations(self):
        response = self.client.get(
            "/correlations",
            params={
                "variables": "T2M",
                "lat": -33.45,
                "lon": -70.66,
                "category": "wildfires",
                "start": "20100101",
                "end": "20121231",
                "max_lag_months": 3,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["events_count"], 1)
        self.assertEqual(len(body["correlations"]["T2M"]["lags"]), 7)
        self.assertIn("q", body["correlations"]["T2M"]["lags"][0])

    def test_event_analysis(self):
        response = self.client.get(
            "/events/EONET_TEST/analysis",
            params={
                "variables": "T2M",
                "lat": -33.45,
                "lon": -70.66,
                "start": "20100101",
                "end": "20121231",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["window"]["profile"], "wildfires")
        self.assertIn("T2M", body["variables"])

    def test_point_analysis(self):
        response = self.client.post(
            "/analysis/point",
            json={
                "lat": -33.45,
                "lon": -70.66,
                "variables": ["T2M", "RH2M"],
                "start": "20100101",
                "end": "20121231",
                "events": {"category": ["wildfires"], "status": "all", "limit": 10},
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["events_count"], 1)
        self.assertEqual(len(body["event_summaries"]), 1)
        self.assertIn("T2M", body["trends"])
        self.assertIn("T2M", body["correlations"])

    def test_validation(self):
        self.assertEqual(
            self.client.get(
                "/observations",
                params={"variables": "T2M", "lat": 100, "lon": 0, "start": "20100101"},
            ).status_code,
            422,
        )
        self.assertEqual(self.client.get("/events", params={"limit": 5000}).status_code, 422)

    def test_openapi_contains_paths(self):
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        paths = response.json()["paths"]
        for path in ("/observations", "/anomalies", "/trends", "/correlations", "/analysis/point"):
            self.assertIn(path, paths)


if __name__ == "__main__":
    unittest.main()
