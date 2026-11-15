"""FIRMS client and parsers (fire hotspots, CSV).

Validated constraints (2026-10-15):
  - area/csv accepts DAY_RANGE 1..5
  - country/csv is disabled by NASA
  - a keyless global 24h CSV exists
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date as date_cls, datetime, timezone
from pathlib import Path

from ..client import Response, cached_fetch, fetch
from ..config import CACHE_DIR, get

BASE = "https://firms.modaps.eosdis.nasa.gov"


class FirmsApiError(RuntimeError):
    pass


@dataclass(slots=True)
class FireDetection:
    lat: float
    lon: float
    acq_time: datetime
    satellite: str | None = None
    instrument: str | None = None
    confidence: str | None = None
    bright_ti4: float | None = None
    bright_ti5: float | None = None
    frp: float | None = None
    daynight: str | None = None
    version: str | None = None


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class FirmsClient:
    def __init__(
        self,
        map_key: str | None = None,
        *,
        cache_dir: Path = CACHE_DIR,
        use_cache: bool = True,
        timeout: int = 120,
    ):
        self.map_key = map_key if map_key is not None else get("FIRMS_MAP_KEY")
        self.cache_dir = cache_dir
        self.use_cache = use_cache
        self.timeout = timeout

    def _get_text(self, url: str, max_age_s: int = 3600) -> str:
        response: Response = (
            cached_fetch(url, cache_dir=self.cache_dir, max_age_s=max_age_s, timeout=self.timeout)
            if self.use_cache
            else fetch(url, timeout=self.timeout)
        )
        if response.status != 200:
            raise FirmsApiError(
                f"HTTP {response.status}: {response.body[:160].decode('utf-8', 'replace')!r}"
            )
        return response.body.decode("utf-8")

    def area_csv(
        self,
        source: str = "VIIRS_SNPP_NRT",
        *,
        area: str | tuple[float, float, float, float] = "world",
        day_range: int = 1,
        date: str | None = None,
    ) -> str:
        if not 1 <= int(day_range) <= 5:
            raise ValueError("day_range must be between 1 and 5")
        if not self.map_key:
            raise FirmsApiError("FIRMS_MAP_KEY is not configured")
        date = date or date_cls.today().isoformat()
        if isinstance(area, (tuple, list)):
            # west,south,east,north
            area = ",".join(f"{value:g}" for value in area)
        url = f"{BASE}/api/area/csv/{self.map_key}/{source}/{area}/{day_range}/{date}"
        return self._get_text(url)

    def static_global_csv(self, sensor: str = "suomi-npp-viirs-c2") -> str:
        url = f"{BASE}/data/active_fire/{sensor}/csv/SUOMI_VIIRS_C2_Global_24h.csv"
        return self._get_text(url, max_age_s=1800)

    @staticmethod
    def parse_csv(text: str) -> list[FireDetection]:
        detections: list[FireDetection] = []
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or "latitude" not in reader.fieldnames:
            raise FirmsApiError("FIRMS CSV is missing expected columns")
        for row in reader:
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
                acq_date = (row.get("acq_date") or "").strip()
                acq_time = (row.get("acq_time") or "").strip().zfill(4)
                stamp = datetime.strptime(f"{acq_date} {acq_time}", "%Y-%m-%d %H%M").replace(
                    tzinfo=timezone.utc
                )
            except (KeyError, TypeError, ValueError):
                continue
            detections.append(
                FireDetection(
                    lat=lat,
                    lon=lon,
                    acq_time=stamp,
                    satellite=(row.get("satellite") or "").strip() or None,
                    instrument=(row.get("instrument") or "").strip() or None,
                    confidence=(row.get("confidence") or "").strip() or None,
                    bright_ti4=_num(row.get("bright_ti4")),
                    bright_ti5=_num(row.get("bright_ti5")),
                    frp=_num(row.get("frp")),
                    daynight=(row.get("daynight") or "").strip() or None,
                    version=(row.get("version") or "").strip() or None,
                )
            )
        return detections
