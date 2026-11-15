"""Precomputed pixel-to-region mask for GIBS global images.

The mask maps every pixel of a 2048x1024 EPSG:4326 image to one of the 162
geodesic regions used by the POC. It also stores cos(latitude) so a regional
mean can be area-weighted.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

from .config import CACHE_DIR
from .hexgrid import region_centres

GRID_VERSION = "poc-hex-162-2048x1024-v1"
REGION_COUNT = 162
DEFAULT_WIDTH = 2048
DEFAULT_HEIGHT = 1024


def _cache_path(cache_dir: Path, width: int, height: int) -> Path:
    return cache_dir / "grids" / f"{GRID_VERSION}-{width}x{height}.npz"


def build_region_map(
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    *,
    cache_dir: Path = CACHE_DIR,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (region_id int16[h,w], area_weight float32[h,w])."""
    path = _cache_path(cache_dir, width, height)
    if path.exists():
        with np.load(path) as data:
            return data["region_id"], data["weight"]

    centres = np.asarray(region_centres(), dtype=np.float32)  # (162, 3)
    if centres.shape != (REGION_COUNT, 3):
        raise RuntimeError(f"expected {REGION_COUNT} regions, got {centres.shape[0]}")

    region_id = np.empty((height, width), dtype=np.int16)
    weight = np.empty((height, width), dtype=np.float32)

    # Process rows in chunks: the full (2M, 162) dot product would be too large.
    chunk = 64
    for y0 in range(0, height, chunk):
        y1 = min(height, y0 + chunk)
        lat = 90.0 - (np.arange(y0, y1, dtype=np.float32) + 0.5) * 180.0 / height
        lon = -180.0 + (np.arange(width, dtype=np.float32) + 0.5) * 360.0 / width
        lat_grid, lon_grid = np.meshgrid(np.radians(lat), np.radians(lon), indexing="ij")
        vectors = np.stack(
            (
                np.cos(lat_grid) * np.sin(lon_grid),
                np.sin(lat_grid),
                np.cos(lat_grid) * np.cos(lon_grid),
            ),
            axis=-1,
        ).reshape(-1, 3)
        dots = vectors @ centres.T
        region_id[y0:y1] = np.argmax(dots, axis=1).reshape(y1 - y0, width)
        weight[y0:y1] = np.broadcast_to(
            np.cos(np.radians(lat))[:, None], (y1 - y0, width)
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, region_id=region_id, weight=weight)
    return region_id, weight


@lru_cache(maxsize=4)
def get_region_map(
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    cache_dir: str = str(CACHE_DIR),
) -> tuple[np.ndarray, np.ndarray]:
    return build_region_map(width, height, cache_dir=Path(cache_dir))
