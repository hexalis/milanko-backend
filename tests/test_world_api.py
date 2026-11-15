"""API tests for the world base and hexbin endpoints (no network)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from api.app import app  # noqa: E402
from api.deps import get_eonet_client  # noqa: E402

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


class FakeEonetClient:
    def events(self, **kwargs):
        return {"events": [EVENT]}

    def categories(self):
        return {"categories": [{"id": "wildfires", "title": "Wildfires"}]}


class WorldApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.dependency_overrides[get_eonet_client] = lambda: FakeEonetClient()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()

    def test_world_config(self):
        response = self.client.get("/world/config")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["world_base_url"], "/world/")
        self.assertIn("56", body["base_urls"])
        self.assertIn("80", body["base_urls"])
        self.assertEqual(body["grid"]["frequencies"]["80"]["cells"], 64002)

    def test_world_meta(self):
        response = self.client.get("/world/meta.json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("grids", response.json())

    def test_world_base_binary(self):
        response = self.client.get("/world/base-80.bin")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"ETDW"))
        self.assertGreater(len(response.content), 800_000)

    def test_world_fine_binary(self):
        response = self.client.get("/world/fine-288/r000.bin")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"ETDW"))
        self.assertEqual(self.client.get("/world/fine-288/nope.bin").status_code, 404)

    def test_world_cells(self):
        response = self.client.get(
            "/world/cells", params={"f": 56, "limit": 5}
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["returned"], 5)
        cell = body["cells"][0]
        self.assertIn("biome", cell)
        self.assertIn("region", cell)
        self.assertTrue(0 <= cell["region"] < 162)

    def test_world_cells_water_filter(self):
        response = self.client.get(
            "/world/cells", params={"f": 80, "water": "true", "limit": 3}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(cell["water"] for cell in response.json()["cells"]))

    def test_hexgrid_meta(self):
        response = self.client.get("/hexgrid/meta")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["regions"], 162)
        self.assertEqual(body["frequencies"]["56"]["cells"], 31362)

    def test_hexbin_events(self):
        response = self.client.get(
            "/hexbin/events",
            params={"f": 56, "category": "wildfires", "status": "all"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["events_total"], 1)
        self.assertEqual(body["cells_returned"], 1)
        cell = body["cells"][0]
        self.assertEqual(cell["count"], 1)
        self.assertEqual(cell["events"][0]["id"], "EONET_TEST")
        self.assertEqual(cell["magnitude_totals"], {"acres": 10.0})

    def test_hexbin_events_geojson(self):
        response = self.client.get(
            "/hexbin/events",
            params={
                "f": 56,
                "category": "wildfires",
                "status": "all",
                "format": "geojson",
                "include_geometry": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["type"], "FeatureCollection")
        self.assertEqual(len(body["features"]), 1)
        self.assertEqual(body["features"][0]["geometry"]["type"], "Polygon")

    def test_hexbin_points(self):
        response = self.client.post(
            "/hexbin/points",
            json={
                "f": 56,
                "points": [
                    {"lat": 0.0, "lon": 0.0, "value": 1.0, "label": "a"},
                    {"lat": 0.1, "lon": 0.1, "value": 3.0, "label": "b"},
                    {"lat": 0.2, "lon": 0.2, "value": 5.0, "label": "c"},
                ],
                "aggregate": "mean",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["points_total"], 3)
        self.assertEqual(body["cells_returned"], 1)
        self.assertEqual(body["cells"][0]["count"], 3)
        self.assertAlmostEqual(body["cells"][0]["value"], 3.0)

    def test_hexbin_points_geojson(self):
        response = self.client.post(
            "/hexbin/points",
            json={
                "f": 56,
                "points": [{"lat": 0.0, "lon": 0.0}],
                "geojson": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["type"], "FeatureCollection")

    def test_validation(self):
        self.assertEqual(
            self.client.get("/world/cells", params={"f": 999}).status_code, 422
        )
        self.assertEqual(
            self.client.get(
                "/world/cells", params={"f": 56, "bbox": "1,2,3"}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post("/hexbin/points", json={"f": 56, "points": []}).status_code,
            422,
        )


if __name__ == "__main__":
    unittest.main()
