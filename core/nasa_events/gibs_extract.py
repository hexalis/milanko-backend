"""GIBS global-image extraction and regional aggregation.

The extractor takes one global WMS image per layer/date, maps rendered colors
to values using curated palettes, and aggregates the 162 POC regions with
area weights. It is deliberately independent from FastAPI and PostgreSQL.
"""
from __future__ import annotations

import io
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .gibs_regions import REGION_COUNT
from .sources.gibs import GibsClient

PALETTES_PATH = Path(__file__).with_name("gibs_palettes.json")
DEFAULT_WIDTH = 2048
DEFAULT_HEIGHT = 1024


@dataclass(frozen=True)
class LayerSpec:
    variable: str
    layer: str
    time_format: str  # "day" or "month"
    unit: str
    scale: float = 1.0
    offset: float = 0.0

    def convert(self, value: float) -> float:
        return value * self.scale + self.offset


LAYERS: dict[str, LayerSpec] = {
    "LST_DAY": LayerSpec(
        "LST_DAY",
        "MODIS_Terra_L3_Land_Surface_Temp_Daily_Day_TES",
        "day",
        "C",
        offset=-273.15,
    ),
    "SST": LayerSpec(
        "SST", "GHRSST_L4_MUR_Sea_Surface_Temperature", "day", "C"
    ),
    "SST_ANOM": LayerSpec(
        "SST_ANOM",
        "GHRSST_L4_MUR_Sea_Surface_Temperature_Anomalies",
        "day",
        "C",
    ),
    "NDVI": LayerSpec("NDVI", "MODIS_Terra_L3_NDVI_Monthly", "month", "index"),
    "SNOW_COVER": LayerSpec(
        "SNOW_COVER", "MODIS_Terra_NDSI_Snow_Cover", "day", "index"
    ),
    "SEA_ICE": LayerSpec(
        "SEA_ICE", "AMSRU2_Sea_Ice_Concentration_25km", "day", "%"
    ),
    "CHLOR_A": LayerSpec(
        "CHLOR_A", "MODIS_Aqua_L2_Chlorophyll_A", "day", "mg/m3"
    ),
    "PRECIP": LayerSpec("PRECIP", "IMERG_Precipitation_Rate", "day", "mm/hr"),
    "SOIL_MOISTURE": LayerSpec(
        "SOIL_MOISTURE",
        "SMAP_L4_Analyzed_Root_Zone_Soil_Moisture",
        "day",
        "m3/m3",
    ),
    "NO2": LayerSpec(
        "NO2", "OMI_Nitrogen_Dioxide_Tropo_Column", "day", "mol/m2"
    ),
}


@lru_cache(maxsize=1)
def load_palettes() -> dict[str, Any]:
    with PALETTES_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def palette_for(variable: str) -> dict[str, float]:
    layers = load_palettes()["layers"]
    if variable not in layers:
        raise KeyError(f"no palette for {variable}")
    return layers[variable]["entries"]


def _aggregate(
    region_id: np.ndarray,
    weight: np.ndarray,
    values: np.ndarray,
    valid: np.ndarray,
    *,
    spec: LayerSpec,
) -> list[dict[str, Any]]:
    flat_region = region_id.ravel()
    flat_weight = weight.ravel()
    flat_valid = valid.ravel()
    flat_values = values.ravel()

    total_weight = np.bincount(
        flat_region, weights=flat_weight, minlength=REGION_COUNT
    )
    valid_weight = np.bincount(
        flat_region,
        weights=np.where(flat_valid, flat_weight, 0.0),
        minlength=REGION_COUNT,
    )
    weighted_sum = np.bincount(
        flat_region,
        weights=np.where(flat_valid, flat_weight * flat_values, 0.0),
        minlength=REGION_COUNT,
    )

    # min/max per region without a Python loop over pixels
    min_value = np.full(REGION_COUNT, np.inf, dtype=np.float64)
    max_value = np.full(REGION_COUNT, -np.inf, dtype=np.float64)
    np.minimum.at(min_value, flat_region[flat_valid], flat_values[flat_valid])
    np.maximum.at(max_value, flat_region[flat_valid], flat_values[flat_valid])

    rows: list[dict[str, Any]] = []
    for index in range(REGION_COUNT):
        total = float(total_weight[index])
        valid_total = float(valid_weight[index])
        if total <= 0:
            continue
        valid_fraction = valid_total / total
        if valid_total <= 0:
            rows.append(
                {
                    "region_code": index,
                    "value": None,
                    "valid_fraction": round(valid_fraction, 6),
                    "quality": "no_data",
                    "metrics": {"min": None, "max": None},
                }
            )
            continue
        raw_mean = float(weighted_sum[index] / valid_total)
        rows.append(
            {
                "region_code": index,
                "value": round(spec.convert(raw_mean), 6),
                "valid_fraction": round(valid_fraction, 6),
                "quality": "ok" if valid_fraction >= 0.05 else "partial",
                "metrics": {
                    "raw_mean": round(raw_mean, 6),
                    "min": round(spec.convert(float(min_value[index])), 6),
                    "max": round(spec.convert(float(max_value[index])), 6),
                },
            }
        )
    return rows


def extract_png(
    png: bytes,
    spec: LayerSpec,
    region_id: np.ndarray,
    weight: np.ndarray,
    *,
    valid_fraction_threshold: float = 0.95,
) -> list[dict[str, Any]]:
    """Extract 162 regional rows from one global GIBS PNG."""
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    if image.size != (region_id.shape[1], region_id.shape[0]):
        raise ValueError(
            f"image size {image.size} differs from mask "
            f"{region_id.shape[::-1]}"
        )
    pixels = np.asarray(image)
    rgb = pixels[..., :3]
    alpha = pixels[..., 3]

    palette = palette_for(spec.variable)
    # Pack RGB into uint32 before np.unique: axis=0 unique on a 2M x 3 array is
    # ~40x slower than unique on the packed channel.
    packed = (
        (rgb[..., 0].astype(np.uint32) << 16)
        | (rgb[..., 1].astype(np.uint32) << 8)
        | rgb[..., 2].astype(np.uint32)
    )
    unique, inverse = np.unique(packed.ravel(), return_inverse=True)
    palette_packed = {
        (int(key.split(",")[0]) << 16)
        | (int(key.split(",")[1]) << 8)
        | int(key.split(",")[2]): value
        for key, value in palette.items()
    }
    mapped = np.full(len(unique), np.nan, dtype=np.float64)
    for index, color in enumerate(unique):
        value = palette_packed.get(int(color))
        if value is not None:
            mapped[index] = value

    values = mapped[inverse].reshape(alpha.shape)
    known = ~np.isnan(values)
    valid = (alpha > 0) & known
    unknown = (alpha > 0) & ~known
    unknown_fraction = float(unknown.sum()) / max(1, int((alpha > 0).sum()))

    rows = _aggregate(region_id, weight, values, valid, spec=spec)
    for row in rows:
        row["unknown_color_fraction"] = round(unknown_fraction, 6)
        if unknown_fraction > (1.0 - valid_fraction_threshold):
            row["quality"] = "error"
    return rows


def fetch_global_png(
    client: GibsClient,
    spec: LayerSpec,
    date: str,
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> bytes:
    return client.wms_getmap(
        spec.layer,
        date,
        lat_min=-90,
        lon_min=-180,
        lat_max=90,
        lon_max=180,
        width=width,
        height=height,
    )


def extract_layer(
    client: GibsClient,
    spec: LayerSpec,
    date: str,
    region_id: np.ndarray,
    weight: np.ndarray,
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> list[dict[str, Any]]:
    png = fetch_global_png(client, spec, date, width=width, height=height)
    return extract_png(png, spec, region_id, weight)
