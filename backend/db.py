"""Database helpers for the Milanko API."""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DATABASE_URL = os.getenv("DATABASE_URL")

engine: Engine | None = (
    create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=2,
        pool_recycle=1800,
    )
    if DATABASE_URL
    else None
)


def database_status() -> str:
    """Return ``ok``, ``error`` or ``not_configured`` for the health endpoint."""

    if engine is None:
        return "not_configured"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"
