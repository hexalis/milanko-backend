#!/usr/bin/env python3
"""Preflight validation for the GIBS layers in the persistence plan.

It requests one global WMS image per layer/date and reports whether the layer
responds, how many bytes it returns, how many colors it contains, and how much
of the image is valid (alpha > 0). It does not need the database.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/validate_gibs_layers.py
    PYTHONPATH=. .venv/bin/python scripts/validate_gibs_layers.py --out /tmp/gibs.json
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from dataclasses import dataclass
from typing import Any

from PIL import Image

from core.nasa_events.sources.gibs import GibsClient

WIDTH = 2048
HEIGHT = 1024
GLOBAL_BBOX = {"lat_min": -90, "lon_min": -180, "lat_max": 90, "lon_max": 180}

SAMPLE_DATES = ["2006-01-01", "2010-01-01", "2015-06-15", "2020-06-15", "2026-10-15"]


@dataclass(frozen=True)
class LayerSpec:
    variable: str
    layer: str
    time_format: str  # "day" or "month"
    dates: tuple[str, ...] = tuple(SAMPLE_DATES)


LAYERS = (
    LayerSpec("LST_DAY", "MODIS_Terra_L3_Land_Surface_Temp_Daily_Day_TES", "day"),
    LayerSpec("SST", "GHRSST_L4_MUR_Sea_Surface_Temperature", "day"),
    LayerSpec("SST_ANOM", "GHRSST_L4_MUR_Sea_Surface_Temperature_Anomalies", "day"),
    LayerSpec(
        "NDVI",
        "MODIS_Terra_L3_NDVI_Monthly",
        "month",
        ("2006-01-01", "2010-01-01", "2015-06-01", "2020-06-01", "2026-10-01"),
    ),
    LayerSpec("SNOW_COVER", "MODIS_Terra_NDSI_Snow_Cover", "day"),
    LayerSpec("SEA_ICE", "AMSRU2_Sea_Ice_Concentration_25km", "day"),
    LayerSpec("CHLOR_A", "MODIS_Aqua_L2_Chlorophyll_A", "day"),
    LayerSpec("PRECIP", "IMERG_Precipitation_Rate", "day"),
    LayerSpec("SOIL_MOISTURE", "SMAP_L4_Analyzed_Root_Zone_Soil_Moisture", "day"),
    LayerSpec("NO2", "OMI_Nitrogen_Dioxide_Tropo_Column", "day"),
)


def analyze_png(png: bytes) -> dict[str, Any]:
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    width, height = image.size
    colors = image.getcolors(maxcolors=5_000_000) or []
    valid_pixels = sum(count for count, (r, g, b, a) in colors if a > 0)
    total = width * height
    top = sorted(colors, reverse=True)[:8]
    return {
        "width": width,
        "height": height,
        "unique_colors": len(colors),
        "valid_fraction": round(valid_pixels / total, 6) if total else 0,
        "top_colors": [
            {"rgba": list(color), "count": count}
            for count, color in top
        ],
    }


def validate_layer(client: GibsClient, spec: LayerSpec) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for date in spec.dates:
        started = time.monotonic()
        entry: dict[str, Any] = {
            "variable": spec.variable,
            "layer": spec.layer,
            "date": date,
            "width": WIDTH,
            "height": HEIGHT,
        }
        try:
            png = client.wms_getmap(
                spec.layer,
                date,
                **GLOBAL_BBOX,
                width=WIDTH,
                height=HEIGHT,
            )
            entry["bytes"] = len(png)
            entry.update(analyze_png(png))
            entry["status"] = "ok"
        except Exception as exc:  # report failures instead of stopping the whole validation
            entry.update(
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
        entry["seconds"] = round(time.monotonic() - started, 2)
        results.append(entry)
        print(
            f"{spec.variable:14} {date} {entry['status']:5} "
            f"{entry.get('bytes', 0):>8} B "
            f"valid={entry.get('valid_fraction', 0):.3f} "
            f"colors={entry.get('unique_colors', 0):>4} "
            f"{entry['seconds']:>5.2f}s",
            file=sys.stderr,
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=str, default="")
    args = parser.parse_args()

    client = GibsClient(use_cache=True, timeout=120)
    report: dict[str, Any] = {
        "width": WIDTH,
        "height": HEIGHT,
        "bbox": GLOBAL_BBOX,
        "layers": {},
    }
    for spec in LAYERS:
        report["layers"][spec.variable] = validate_layer(client, spec)

    failures = sum(
        1
        for rows in report["layers"].values()
        for row in rows
        if row["status"] != "ok"
    )
    report["summary"] = {
        "layers": len(LAYERS),
        "samples": sum(len(rows) for rows in report["layers"].values()),
        "failures": failures,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    else:
        print(text)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
