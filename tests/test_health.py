"""Scaffold tests: health, protected ping and API key documentation."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

import backend.db as db
from backend.app import app


class HealthTest(unittest.TestCase):
    def setUp(self) -> None:
        # Keep tests deterministic: never connect to a real database from unit tests.
        db.engine = None
        self.client = TestClient(app)

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["database"], "not_configured")

    def test_ping(self) -> None:
        response = self.client.get("/ping")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["pong"])

    def test_openapi_documents_api_key(self) -> None:
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        scheme = schema["components"]["securitySchemes"]["ApiKeyAuth"]
        self.assertEqual(scheme["type"], "apiKey")
        self.assertEqual(scheme["in"], "header")
        self.assertEqual(scheme["name"], "X-API-Key")
        self.assertEqual(schema["paths"]["/health"]["get"]["security"], [])


if __name__ == "__main__":
    unittest.main()
