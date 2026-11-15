"""Shared world-base readers used by the API and the ingestion processor."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from core.nasa_events.hexgrid import get_grid
from core.nasa_events.worldbase import read_world_file, region_map

WORLD_DIR = Path(__file__).resolve().parent / "static" / "world"
ALLOWED_F = (56, 80)
FINE_F = 288


@lru_cache(maxsize=1)
def world_meta() -> dict:
    return json.loads((WORLD_DIR / "meta.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def world_base(f: int):
    if f not in ALLOWED_F:
        raise ValueError(f"unsupported world base frequency: {f} (use {ALLOWED_F})")
    header, records = read_world_file(WORLD_DIR / f"base-{f}.bin")
    regions = region_map(header, records)
    grid = get_grid(f, regions)
    return header, records, grid
