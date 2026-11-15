#!/usr/bin/env python3
"""Build the GIBS palette JSON from official GIBS colormap XML files.

The rendered WMS image contains discrete colors. This script converts each
official colormap entry into a color -> numeric value mapping. The generated
file is consumed by the extractor and is versioned in the repo.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = "https://gibs.earthdata.nasa.gov/colormaps/v1.3"
OUT = Path(__file__).resolve().parents[1] / "core" / "nasa_events" / "gibs_palettes.json"

# variable -> (GIBS colormap name, unit)
LAYERS = {
    "LST_DAY": ("MODIS_Land_Surface_Temp", "K"),
    "SST": ("GHRSST_Sea_Surface_Temperature", "C"),
    "SST_ANOM": ("GHRSST_Sea_Surface_Temperature_Anomalies", "C"),
    "NDVI": ("MODIS_L3_NDVI", "index"),
    "SNOW_COVER": ("MODIS_NDSI_Snow_Cover", "index"),
    "SEA_ICE": ("AMSR_Sea_Ice_Concentration", "%"),
    "CHLOR_A": ("MODIS_Chlorophyll", "mg/m3"),
    "PRECIP": ("GPM_Precipitation_Rate", "mm/hr"),
    "SOIL_MOISTURE": ("SMAP_Analyzed_Soil_Moisture", "m3/m3"),
    "NO2": ("OMI_Nitrogen_Dioxide_Tropo_Column", "mol/m2"),
}

RANGE_RE = re.compile(r"^[\[\(]([^,]+),([^\)\]]+)[\]\)]$")
SINGLE_RE = re.compile(r"^[\[\(]([^,]+)[\]\)]$")


def _num(text: str) -> float | None:
    text = text.strip()
    if text in {"INF", "+INF", "inf"}:
        return None
    if text in {"-INF", "-inf"}:
        return None
    return float(text)


def parse_value(text: str | None) -> tuple[float | None, float | None, float | None]:
    """Return (low, high, representative) for a GIBS value expression."""
    if not text:
        return None, None, None
    text = text.strip()
    # Some class/percent layers use a bare number ("1", "0", ...).
    try:
        value = float(text)
        return value, value, value
    except ValueError:
        pass
    single = SINGLE_RE.match(text)
    if single:
        value = _num(single.group(1))
        return value, value, value
    match = RANGE_RE.match(text)
    if not match:
        raise ValueError(f"valor de paleta no reconocido: {text!r}")
    low, high = _num(match.group(1)), _num(match.group(2))
    if low is not None and high is not None:
        representative = (low + high) / 2
    elif high is not None:
        representative = high
    elif low is not None:
        representative = low
    else:
        representative = None
    return low, high, representative


def parse_colormap(xml_bytes: bytes) -> tuple[dict[str, float], list[dict]]:
    root = ET.fromstring(xml_bytes)
    entries: dict[str, float] = {}
    details: list[dict] = []
    for entry in root.findall(".//ColorMapEntry"):
        if entry.attrib.get("transparent") == "true":
            continue
        if entry.attrib.get("nodata") == "true":
            continue
        rgb = entry.attrib.get("rgb")
        if not rgb:
            continue
        low, high, value = parse_value(entry.attrib.get("value"))
        if value is None or not math.isfinite(value):
            continue
        entries[rgb] = value
        details.append(
            {
                "rgb": rgb,
                "low": low,
                "high": high,
                "value": value,
            }
        )
    return entries, details


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    output: dict = {
        "source": BASE,
        "version": "gibs-colormaps-2026-11-05",
        "layers": {},
    }
    for variable, (name, unit) in LAYERS.items():
        url = f"{BASE}/{name}.xml"
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        entries, details = parse_colormap(data)
        if not entries:
            raise SystemExit(f"{variable}: paleta vacía ({url})")
        values = [item["value"] for item in details]
        output["layers"][variable] = {
            "colormap": name,
            "url": url,
            "unit": unit,
            "entries": entries,
            "min": min(values),
            "max": max(values),
            "count": len(entries),
        }
        print(
            f"{variable:14} {name:48} {len(entries):3d} colores "
            f"rango=[{min(values):.4g}, {max(values):.4g}] {unit}",
            flush=True,
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"escrito {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
