"""Health, ping and API-key documentation tests."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api.app import app


class PingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_ping(self) -> None:
        response = self.client.get("/ping")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["pong"])

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.json())

    def test_openapi_documents_api_key(self) -> None:
        schema = self.client.get("/openapi.json").json()
        scheme = schema["components"]["securitySchemes"]["ApiKeyAuth"]
        self.assertEqual(scheme["type"], "apiKey")
        self.assertEqual(scheme["in"], "header")
        self.assertEqual(scheme["name"], "X-API-Key")
        self.assertEqual(schema["paths"]["/health"]["get"]["security"], [])
        self.assertEqual(schema["servers"], [{"url": "/api/v1", "description": "Canonical version"}])


if __name__ == "__main__":
    unittest.main()
