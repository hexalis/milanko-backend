"""GIBS client: capabilities, WMS extraction and palette decoding.

Notes from Fase 0 (see docs/00-recon/gibs-quantifiability.md):
  - WMS GetMap is the quantitative path (small bbox crops, 0.3-2 KB typically)
  - WMS returns HTTP 200 with a fully transparent image when there is no data
  - WMTS tiles use 40x20 matrices at level 5 in epsg4326; thermal layers are MVT
  - GetLegendGraphic is generic (not usable per layer): palettes must be curated
"""
from __future__ import annotations

import io
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode

from ..client import Response, cached_fetch, fetch
from ..config import CACHE_DIR

WMTS_BASE = "https://gibs.earthdata.nasa.gov/wmts/epsg4326/best"
WMS_URL = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
CAPABILITIES_URL = f"{WMTS_BASE}/1.0.0/WMTSCapabilities.xml"

WMTS_NS = "http://www.opengis.net/wmts/1.0"
OWS_NS = "http://www.opengis.net/ows/1.1"

T_LAYER = f"{{{WMTS_NS}}}Layer"
T_FORMAT = f"{{{WMTS_NS}}}Format"
T_DIMENSION = f"{{{WMTS_NS}}}Dimension"
T_DEFAULT = f"{{{WMTS_NS}}}Default"
T_VALUE = f"{{{WMTS_NS}}}Value"
T_TMS_LINK = f"{{{WMTS_NS}}}TileMatrixSetLink"
T_TMS = f"{{{WMTS_NS}}}TileMatrixSet"
T_STYLE = f"{{{WMTS_NS}}}Style"
T_RESURL = f"{{{WMTS_NS}}}ResourceURL"
T_OWS_ID = f"{{{OWS_NS}}}Identifier"
T_OWS_TITLE = f"{{{OWS_NS}}}Title"


class GibsError(RuntimeError):
    pass


def _pil():
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise GibsError(
            "Pillow es necesario para decodificar imágenes GIBS (usar el venv del proyecto)"
        ) from exc
    return Image


def parse_capabilities(xml_path: Path) -> dict[str, dict]:
    """Parse WMTSCapabilities.xml into {layer_id: {title, formats, tms, dimensions, legends}}."""
    summary: dict[str, dict] = {}
    for _event, elem in ET.iterparse(str(xml_path), events=("end",)):
        if elem.tag != T_LAYER:
            continue
        info: dict = {"formats": [], "tms": [], "dimensions": {}, "legends": [], "resources": []}
        for child in elem:
            if child.tag == T_OWS_ID:
                info["id"] = (child.text or "").strip()
            elif child.tag == T_OWS_TITLE:
                info["title"] = (child.text or "").strip()
            elif child.tag == T_FORMAT:
                info["formats"].append((child.text or "").strip())
            elif child.tag == T_DIMENSION:
                ident, default, values = "", None, []
                for sub in child:
                    if sub.tag == T_OWS_ID:
                        ident = (sub.text or "").strip()
                    elif sub.tag == T_DEFAULT:
                        default = (sub.text or "").strip()
                    elif sub.tag == T_VALUE:
                        values.append((sub.text or "").strip())
                info["dimensions"][ident] = {
                    "default": default,
                    "count": len(values),
                    "first": values[0] if values else None,
                    "last": values[-1] if values else None,
                }
            elif child.tag == T_TMS_LINK:
                for sub in child:
                    if sub.tag == T_TMS:
                        info["tms"].append((sub.text or "").strip())
            elif child.tag == T_STYLE:
                for sub in child.iter():
                    if sub.tag.endswith("LegendURL"):
                        href = sub.get("href") or sub.get("{http://www.w3.org/1999/xlink}href")
                        if href:
                            info["legends"].append(href)
            elif child.tag == T_RESURL:
                info["resources"].append(
                    {
                        "template": child.get("template"),
                        "resourceType": child.get("resourceType"),
                        "format": child.get("format"),
                    }
                )
        if info.get("id"):
            summary[info["id"]] = info
        elem.clear()
    return summary


def time_dimension(info: dict) -> dict:
    for key, value in (info.get("dimensions") or {}).items():
        if key.lower() == "time":
            return value or {}
    return {}


class GibsClient:
    def __init__(
        self,
        *,
        cache_dir: Path = CACHE_DIR,
        use_cache: bool = True,
        timeout: int = 120,
    ):
        self.cache_dir = cache_dir
        self.use_cache = use_cache
        self.timeout = timeout

    def capabilities(self, refresh: bool = False) -> dict:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        summary_path = self.cache_dir / "gibs_capabilities_summary.json"
        if not refresh and summary_path.exists():
            return json.loads(summary_path.read_text(encoding="utf-8"))
        xml_path = self.cache_dir / "WMTSCapabilities.xml"
        if refresh or not xml_path.exists():
            response = fetch(CAPABILITIES_URL, timeout=600, retries=1)
            if response.status != 200:
                raise GibsError(f"capabilities HTTP {response.status}")
            xml_path.write_bytes(response.body)
        summary = parse_capabilities(xml_path)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
        return summary

    def wms_getmap(
        self,
        layer: str,
        date: str,
        *,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
        width: int = 256,
        height: int = 256,
        fmt: str = "image/png",
        transparent: bool = True,
        max_age_s: int | None = 24 * 3600,
    ) -> bytes:
        if not (lat_min < lat_max and lon_min < lon_max):
            raise ValueError("invalid bbox")
        params = {
            "SERVICE": "WMS",
            "REQUEST": "GetMap",
            "VERSION": "1.3.0",
            "LAYERS": layer,
            "STYLES": "",
            "FORMAT": fmt,
            "TRANSPARENT": "TRUE" if transparent else "FALSE",
            "CRS": "EPSG:4326",
            "BBOX": f"{lat_min},{lon_min},{lat_max},{lon_max}",
            "WIDTH": str(int(width)),
            "HEIGHT": str(int(height)),
            "TIME": date,
        }
        url = f"{WMS_URL}?{urlencode(params, safe=',')}"
        response: Response = (
            cached_fetch(url, cache_dir=self.cache_dir, max_age_s=max_age_s, timeout=self.timeout)
            if self.use_cache
            else fetch(url, timeout=self.timeout)
        )
        if response.status != 200:
            raise GibsError(f"WMS HTTP {response.status}: {response.body[:160]!r}")
        return response.body

    # ------------------------------------------------------------- decoding
    @staticmethod
    def is_blank(png: bytes) -> bool:
        Image = _pil()
        image = Image.open(io.BytesIO(png)).convert("RGBA")
        return image.getchannel("A").getextrema() == (0, 0)

    @staticmethod
    def palette_counts(
        png: bytes, top: int = 20
    ) -> list[tuple[tuple[int, int, int, int], int]]:
        Image = _pil()
        image = Image.open(io.BytesIO(png)).convert("RGBA")
        colors = image.getcolors(maxcolors=5_000_000) or []
        colors.sort(reverse=True)
        return [(tuple(color), count) for count, color in colors[:top]]

    @staticmethod
    def decode_palette(
        png: bytes, mapping: dict[tuple[int, int, int, int], str]
    ) -> dict[str, int]:
        Image = _pil()
        image = Image.open(io.BytesIO(png)).convert("RGBA")
        counts = {tuple(color): count for count, color in (image.getcolors(maxcolors=5_000_000) or [])}
        result: dict[str, int] = {}
        for color, label in mapping.items():
            result[label] = result.get(label, 0) + counts.get(tuple(color), 0)
        return result
