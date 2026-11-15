"""NASA POWER client and parsers.

Known POWER API constraints (validated 2026-10-15, see docs/00-recon/limits-and-rates.md):
  - max 20 parameter codes per request
  - regional: exactly 1 parameter and a bbox between 2 and 10 degrees per axis
  - 'PSC' requires &site-elevation=<meters>
  - monthly endpoints use years 'YYYY' for start/end (responses are keyed YYYYMM)
  - time standard is LST (solar local time), not UTC
"""
from __future__ import annotations

import re
from pathlib import Path

from ..client import Response, cached_fetch, fetch
from ..config import CACHE_DIR
from ..models import Observation
from ..normalize import clean_value, parse_date_key

BASE = "https://power.larc.nasa.gov/api"
VALID_COMMUNITIES = ("RE", "AG", "SB")
MAX_PARAMS = 20
MIN_REGION_DEG = 2.0
MAX_REGION_DEG = 10.0


class PowerApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, payload: dict | None = None):
        super().__init__(message)
        self.status = status
        self.payload = payload or {}


def chunked(items: list[str], size: int = MAX_PARAMS) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


class PowerClient:
    def __init__(
        self,
        community: str = "RE",
        *,
        cache_dir: Path = CACHE_DIR,
        use_cache: bool = True,
        timeout: int = 120,
        site_elevation: float | None = None,
    ):
        if community.upper() not in VALID_COMMUNITIES:
            raise ValueError(f"invalid community: {community} (use {VALID_COMMUNITIES})")
        self.community = community.upper()
        self.cache_dir = cache_dir
        self.use_cache = use_cache
        self.timeout = timeout
        self.site_elevation = site_elevation

    # ------------------------------------------------------------------ HTTP
    def _get_json(self, url: str, max_age_s: int | None) -> dict:
        response = (
            cached_fetch(url, cache_dir=self.cache_dir, max_age_s=max_age_s, timeout=self.timeout)
            if self.use_cache
            else fetch(url, timeout=self.timeout)
        )
        return self._payload(response)

    def _payload(self, response: Response) -> dict:
        if response.status != 200:
            try:
                payload = response.json()
            except Exception:
                raise PowerApiError(
                    f"HTTP {response.status}: {response.body[:200]!r}", status=response.status
                ) from None
            self.raise_for_error(payload, status=response.status)
        payload = response.json()
        if payload.get("errors"):
            self.raise_for_error(payload, status=response.status)
        return payload

    # -------------------------------------------------------------- catalogs
    def catalog(self, community: str | None = None, temporal: str = "DAILY") -> dict:
        community = (community or self.community).upper()
        temporal = temporal.upper()
        url = (
            f"{BASE}/system/manager/parameters?community={community}"
            f"&temporal={temporal}&format=JSON"
        )
        return self._get_json(url, max_age_s=7 * 24 * 3600)

    # ---------------------------------------------------------------- points
    def point_payloads(
        self,
        codes: list[str],
        lat: float,
        lon: float,
        start: str,
        end: str,
        *,
        temporal: str = "daily",
        community: str | None = None,
        site_elevation: float | None = None,
        fmt: str = "JSON",
    ) -> list[dict]:
        temporal = temporal.lower()
        self.validate_dates(temporal, start, end)
        if not codes:
            raise ValueError("codes cannot be empty")
        if "PSC" in codes:
            elevation = site_elevation if site_elevation is not None else self.site_elevation
            if elevation is None:
                raise ValueError("PSC requires site_elevation (meters)")
        else:
            elevation = site_elevation if site_elevation is not None else self.site_elevation
        community = (community or self.community).upper()
        payloads = []
        for chunk in chunked(list(dict.fromkeys(codes))):
            url = self._point_url(
                temporal, chunk, lat, lon, start, end, community, elevation, fmt
            )
            payloads.append(self._get_json(url, max_age_s=6 * 3600))
        return payloads

    def point(self, codes: list[str], lat: float, lon: float, start: str, end: str, **kwargs) -> list[Observation]:
        temporal = kwargs.get("temporal", "daily")
        granularity = "monthly" if temporal == "monthly" else ("hourly" if temporal == "hourly" else "daily")
        observations: list[Observation] = []
        seen: set[tuple[str, object]] = set()
        for payload in self.point_payloads(codes, lat, lon, start, end, **kwargs):
            for observation in self.parse_point_payload(payload, granularity):
                # POWER can repeat a parameter (notably PSC) across chunks; keep one.
                key = (observation.code, observation.time)
                if key in seen:
                    continue
                seen.add(key)
                observations.append(observation)
        return observations

    def climatology_payload(
        self,
        codes: list[str],
        lat: float,
        lon: float,
        *,
        community: str | None = None,
        site_elevation: float | None = None,
    ) -> dict:
        if "PSC" in codes:
            elevation = site_elevation if site_elevation is not None else self.site_elevation
            if elevation is None:
                raise ValueError("PSC requires site_elevation (meters)")
        else:
            elevation = site_elevation if site_elevation is not None else self.site_elevation
        community = (community or self.community).upper()
        url = (
            f"{BASE}/temporal/climatology/point?parameters={','.join(codes)}"
            f"&community={community}&latitude={lat}&longitude={lon}"
        )
        if elevation is not None:
            url += f"&site-elevation={elevation}"
        url += "&format=JSON"
        return self._get_json(url, max_age_s=30 * 24 * 3600)

    def climatology(self, codes: list[str], lat: float, lon: float, **kwargs) -> list[Observation]:
        payload = self.climatology_payload(codes, lat, lon, **kwargs)
        return self.parse_point_payload(payload, "climatology")

    # -------------------------------------------------------------- regional
    def regional(
        self,
        code: str,
        *,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
        start: str,
        end: str,
        temporal: str = "daily",
        community: str | None = None,
    ) -> list[Observation]:
        temporal = temporal.lower()
        self.validate_dates(temporal, start, end)
        if not code or "," in code:
            raise ValueError("regional accepts exactly 1 parameter")
        lat_span = lat_max - lat_min
        lon_span = lon_max - lon_min
        if not (MIN_REGION_DEG <= lat_span <= MAX_REGION_DEG):
            raise ValueError(f"lat span must be between {MIN_REGION_DEG} and {MAX_REGION_DEG} degrees")
        if not (MIN_REGION_DEG <= lon_span <= MAX_REGION_DEG):
            raise ValueError(f"lon span must be between {MIN_REGION_DEG} and {MAX_REGION_DEG} degrees")
        community = (community or self.community).upper()
        url = (
            f"{BASE}/temporal/{temporal}/regional?parameters={code}&community={community}"
            f"&latitude-min={lat_min}&latitude-max={lat_max}"
            f"&longitude-min={lon_min}&longitude-max={lon_max}"
            f"&start={start}&end={end}&format=JSON"
        )
        payload = self._get_json(url, max_age_s=6 * 3600)
        granularity = "monthly" if temporal == "monthly" else "daily"
        return self.parse_regional_payload(payload, granularity)

    # ----------------------------------------------------------------- utils
    @staticmethod
    def validate_dates(temporal: str, start: str, end: str) -> None:
        if temporal == "monthly":
            if not (re.fullmatch(r"\d{4}", start) and re.fullmatch(r"\d{4}", end)):
                raise ValueError("monthly start/end must be 'YYYY' years")
        else:
            if not (re.fullmatch(r"\d{8}", start) and re.fullmatch(r"\d{8}", end)):
                raise ValueError(f"{temporal} start/end must be 'YYYYMMDD'")

    def _point_url(
        self,
        temporal: str,
        codes: list[str],
        lat: float,
        lon: float,
        start: str,
        end: str,
        community: str,
        site_elevation: float | None,
        fmt: str,
    ) -> str:
        url = (
            f"{BASE}/temporal/{temporal}/point?parameters={','.join(codes)}"
            f"&community={community}&latitude={lat}&longitude={lon}"
        )
        if site_elevation is not None:
            url += f"&site-elevation={site_elevation}"
        return url + f"&start={start}&end={end}&format={fmt}"

    @staticmethod
    def raise_for_error(payload: dict, status: int | None = None) -> None:
        messages = payload.get("messages") or []
        errors = payload.get("errors") or []
        detail = "; ".join(str(m) for m in [*messages, *errors]) or "error desconocido"
        raise PowerApiError(detail, status=status, payload=payload)

    # ---------------------------------------------------------------- parsers
    @staticmethod
    def parse_point_payload(payload: dict, granularity: str = "daily") -> list[Observation]:
        series_by_code = (payload.get("properties") or {}).get("parameter")
        if not series_by_code:
            PowerClient.raise_for_error(payload, status=200)
            raise PowerApiError("POWER response has no properties.parameter", status=200)
        meta = payload.get("parameters") or {}
        header = payload.get("header") or {}
        fill = header.get("fill_value", -999.0)
        standard = header.get("time_standard", "LST")
        coords = (payload.get("geometry") or {}).get("coordinates") or []
        lon = coords[0] if len(coords) > 0 else None
        lat = coords[1] if len(coords) > 1 else None
        elevation = coords[2] if len(coords) > 2 else None
        observations: list[Observation] = []
        for code, series in series_by_code.items():
            unit = (meta.get(code) or {}).get("units")
            for label, raw in (series or {}).items():
                # POWER's monthly point payload adds a 13th month with the annual
                # aggregate; the API series is monthly, so the aggregate is skipped.
                if granularity == "monthly" and label.strip().endswith("13"):
                    continue
                value, quality = clean_value(raw, fill)
                observations.append(
                    Observation(
                        source="POWER",
                        code=code,
                        value=value,
                        unit=unit,
                        time=parse_date_key(label, granularity),
                        time_label=label,
                        time_standard=standard,
                        lat=lat,
                        lon=lon,
                        granularity=granularity,
                        quality=quality,
                        meta={"elevation": elevation},
                    )
                )
        return observations

    @staticmethod
    def parse_regional_payload(payload: dict, granularity: str = "daily") -> list[Observation]:
        features = payload.get("features") or []
        meta = payload.get("parameters") or {}
        header = payload.get("header") or {}
        fill = header.get("fill_value", -999.0)
        standard = header.get("time_standard", "LST")
        observations: list[Observation] = []
        for feature in features:
            coords = (feature.get("geometry") or {}).get("coordinates") or []
            lon = coords[0] if len(coords) > 0 else None
            lat = coords[1] if len(coords) > 1 else None
            elevation = coords[2] if len(coords) > 2 else None
            series_by_code = (feature.get("properties") or {}).get("parameter") or {}
            for code, series in series_by_code.items():
                unit = (meta.get(code) or {}).get("units")
                for label, raw in (series or {}).items():
                    if granularity == "monthly" and label.strip().endswith("13"):
                        continue
                    value, quality = clean_value(raw, fill)
                    observations.append(
                        Observation(
                            source="POWER",
                            code=code,
                            value=value,
                            unit=unit,
                            time=parse_date_key(label, granularity),
                            time_label=label,
                            time_standard=standard,
                            lat=lat,
                            lon=lon,
                            granularity=granularity,
                            quality=quality,
                            meta={"elevation": elevation},
                        )
                    )
        return observations
