"""DONKI client (NASA space weather).

Outage note: DONKI returned HTTP 503 (upstream failure) on 2026-10-15 and 2026-10-19.
The API key itself works (missing key returns 403 API_KEY_MISSING).
"""
from __future__ import annotations

from datetime import date, datetime
from urllib.parse import urlencode

from ..client import fetch
from ..config import get

BASE = "https://api.nasa.gov/DONKI"
VALID_KINDS = ("GST", "FLR", "CME", "IPS", "SEP", "MPC", "RBE", "HSS", "notifications")


class DonkiError(RuntimeError):
    pass


class DonkiUnavailable(DonkiError):
    pass


def _iso(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


class DonkiClient:
    def __init__(self, api_key: str | None = None, *, timeout: int = 60):
        self.api_key = api_key if api_key is not None else get("NASA_API_KEY")
        self.timeout = timeout

    def _get(self, kind: str, start: date | str, end: date | str) -> list | dict:
        if kind not in VALID_KINDS:
            raise ValueError(f"invalid kind: {kind}")
        params = {
            "startDate": _iso(start),
            "endDate": _iso(end),
            "api_key": self.api_key,
        }
        url = f"{BASE}/{kind}?{urlencode(params)}"
        response = fetch(url, timeout=self.timeout, retries=1)
        if response.status == 503:
            raise DonkiUnavailable(
                "DONKI no disponible: HTTP 503 upstream (servicio caído; reintentar más tarde)"
            )
        if response.status in (401, 403):
            raise DonkiError("Invalid or missing NASA API key (HTTP %s)" % response.status)
        if response.status != 200:
            raise DonkiError(f"DONKI HTTP {response.status}: {response.body[:160]!r}")
        return response.json()

    def gst(self, start: date | str, end: date | str):
        return self._get("GST", start, end)

    def flr(self, start: date | str, end: date | str):
        return self._get("FLR", start, end)

    def cme(self, start: date | str, end: date | str):
        return self._get("CME", start, end)
