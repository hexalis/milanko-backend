"""EONET v3 client and parsers."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from ..client import Response, cached_fetch, fetch
from ..config import CACHE_DIR
from ..models import Event, EventFeature, EventGeometry

BASE = "https://eonet.gsfc.nasa.gov/api/v3"
VALID_STATUS = ("open", "closed", "all")


class EonetApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class EonetClient:
    def __init__(
        self,
        *,
        cache_dir: Path = CACHE_DIR,
        use_cache: bool = True,
        timeout: int = 60,
    ):
        self.cache_dir = cache_dir
        self.use_cache = use_cache
        self.timeout = timeout

    # ---------------------------------------------------------------- HTTP
    def _get_json(self, url: str, max_age_s: int = 30 * 60) -> dict:
        response: Response = (
            cached_fetch(url, cache_dir=self.cache_dir, max_age_s=max_age_s, timeout=self.timeout)
            if self.use_cache
            else fetch(url, timeout=self.timeout)
        )
        if response.status != 200:
            self.raise_for_status(response.status, response.body, response.url)
        return response.json()

    @staticmethod
    def raise_for_status(status: int | None, body: bytes, url: str = "") -> None:
        detail = body[:200].decode("utf-8", "replace")
        raise EonetApiError(f"HTTP {status} from {url or 'EONET'}: {detail!r}", status=status)

    def categories(self) -> dict:
        return self._get_json(f"{BASE}/categories", max_age_s=7 * 24 * 3600)

    def sources(self) -> dict:
        return self._get_json(f"{BASE}/sources", max_age_s=7 * 24 * 3600)

    def magnitudes(self) -> dict:
        return self._get_json(f"{BASE}/magnitudes", max_age_s=7 * 24 * 3600)

    def layers(self) -> dict:
        return self._get_json(f"{BASE}/layers", max_age_s=7 * 24 * 3600)

    def events(
        self,
        *,
        status: str = "open",
        category: str | list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        days: int | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        limit: int | None = None,
        mag_id: str | None = None,
        mag_min: float | None = None,
        geojson: bool = False,
    ) -> dict:
        if status not in VALID_STATUS:
            raise ValueError(f"status must be one of {VALID_STATUS}")
        params: dict[str, str] = {"status": status}
        if category:
            params["category"] = ",".join(category) if isinstance(category, (list, tuple)) else category
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if days is not None:
            params["days"] = str(int(days))
        if bbox is not None:
            # EONET: minLon,maxLat,maxLon,minLat
            params["bbox"] = ",".join(f"{v:g}" for v in bbox)
        if limit is not None:
            params["limit"] = str(int(limit))
        if mag_id:
            params["magID"] = mag_id
        if mag_min is not None:
            params["magMin"] = f"{mag_min:g}"
        path = "events/geojson" if geojson else "events"
        return self._get_json(f"{BASE}/{path}?{urlencode(params)}")

    def event(self, event_id: str) -> dict:
        return self._get_json(f"{BASE}/events/{event_id}", max_age_s=30 * 60)

    # -------------------------------------------------------------- parsers
    @staticmethod
    def parse_events(payload: dict) -> list[Event]:
        if "events" not in payload:
            raise EonetApiError("EONET response has no 'events' key")
        events: list[Event] = []
        for raw in payload.get("events") or []:
            geometry = [
                EventGeometry(
                    date=_dt(item.get("date")),
                    geometry_type=item.get("type", "Point"),
                    coordinates=list(item.get("coordinates") or []),
                    magnitude_value=item.get("magnitudeValue"),
                    magnitude_unit=item.get("magnitudeUnit"),
                )
                for item in raw.get("geometry") or []
                if item.get("date")
            ]
            events.append(
                Event(
                    id=raw.get("id", ""),
                    title=raw.get("title", ""),
                    description=raw.get("description"),
                    link=raw.get("link", ""),
                    closed=_dt(raw.get("closed")),
                    categories=[c.get("id", "") for c in raw.get("categories") or []],
                    sources=list(raw.get("sources") or []),
                    geometry=geometry,
                )
            )
        return events

    @staticmethod
    def parse_geojson(payload: dict) -> list[EventFeature]:
        if payload.get("type") != "FeatureCollection":
            raise EonetApiError("EONET response is not a FeatureCollection")
        features: list[EventFeature] = []
        for feature in payload.get("features") or []:
            props = feature.get("properties") or {}
            geom = feature.get("geometry") or {}
            features.append(
                EventFeature(
                    event_id=props.get("id", ""),
                    title=props.get("title", ""),
                    date=_dt(props.get("date")),
                    geometry_type=geom.get("type", "Point"),
                    coordinates=list(geom.get("coordinates") or []),
                    magnitude_value=props.get("magnitudeValue"),
                    magnitude_unit=props.get("magnitudeUnit"),
                    categories=[c.get("id", "") for c in props.get("categories") or []],
                )
            )
        return features
