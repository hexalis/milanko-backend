"""FastAPI dependencies (shared, cached clients)."""
from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException

from core.nasa_events import EonetClient, GibsClient, PowerClient

from core import db


@lru_cache(maxsize=1)
def get_power_client() -> PowerClient:
    return PowerClient(use_cache=True)


@lru_cache(maxsize=1)
def get_eonet_client() -> EonetClient:
    return EonetClient(use_cache=True)


@lru_cache(maxsize=1)
def get_gibs_client() -> GibsClient:
    return GibsClient(use_cache=True)


def get_db_session():
    if not db.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Persistencia no configurada (DATABASE_URL ausente)",
        )
    yield from db.get_db()
