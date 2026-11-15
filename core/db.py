"""Database engine and session helpers for the persistence phase."""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None

if DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=1800,
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def is_configured() -> bool:
    return engine is not None


def get_db() -> Iterator[Session]:
    """FastAPI dependency. Yields a session when DATABASE_URL is configured."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager for scripts and ingestion jobs."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def health() -> str:
    if engine is None:
        return "not_configured"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"
