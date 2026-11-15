"""Database foundation tests (no PostgreSQL required)."""
import unittest

from core import db
from core.models import Base


class DatabaseFoundationTest(unittest.TestCase):
    def test_health_without_database_url(self):
        if db.is_configured():
            self.skipTest("DATABASE_URL configurada en este entorno")
        self.assertEqual(db.health(), "not_configured")

    def test_expected_tables(self):
        expected = {
            "locations",
            "variables",
            "source_layers",
            "palettes",
            "observations",
            "events",
            "event_geometry",
            "analysis_cache",
            "ingest_runs",
            "ingest_checkpoints",
            "gibs_availability",
        }
        self.assertTrue(expected.issubset(Base.metadata.tables))


if __name__ == "__main__":
    unittest.main()
