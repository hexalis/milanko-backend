"""Materialized-view refresh helpers shared by the ingestion workers."""

from __future__ import annotations

from sqlalchemy import text

from core import db


def refresh_coverage() -> None:
    """Refresh the coverage view without blocking concurrent API reads."""
    if db.engine is None:
        raise RuntimeError("DATABASE_URL is not configured")
    with db.engine.connect() as connection:
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")
        connection.execute(
            text("REFRESH MATERIALIZED VIEW CONCURRENTLY variable_coverage")
        )


def refresh_analytics() -> None:
    """Refresh the monthly aggregates used by maps, trends and anomalies."""
    if db.engine is None:
        raise RuntimeError("DATABASE_URL is not configured")
    with db.engine.connect() as connection:
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")
        connection.execute(
            text("REFRESH MATERIALIZED VIEW CONCURRENTLY region_monthly")
        )
