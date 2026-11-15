"""World base (planet appearance) and hexagonal binning services."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from statistics import mean

from core.nasa_events import EonetClient, GibsClient
from core.nasa_events.hexgrid import (
    BIOMES,
    EARTH_AREA_KM2,
    FLAG,
    cell_area_km2,
    cell_ref,
    to_lat_lon,
    point,
    decode,
)
from core.world import WORLD_DIR, world_base, world_meta

TRUE_COLOR_LAYER = "MODIS_Terra_CorrectedReflectance_TrueColor"


# --------------------------------------------------------------------- helpers
def _cell_size(cells_count: int) -> tuple[float, float]:
    area = EARTH_AREA_KM2 / cells_count
    side = math.sqrt(2.0 * area / (3.0 * math.sqrt(3.0)))
    return area, 2.0 * side


def grid_meta() -> dict:
    meta = world_meta()
    frequencies = {}
    for f, key in ((56, "base-56"), (80, "base-80"), (288, "fine-288")):
        entry = meta.get("grids", {}).get(key, {})
        count = entry.get("cells")
        if not count:
            continue
        area, across = _cell_size(count)
        frequencies[str(f)] = {
            "cells": count,
            "area_km2": round(area, 1),
            "across_km": round(across, 1),
            "level": entry.get("level"),
            "file": entry.get("file") or entry.get("dir"),
        }
    return {
        "source": "Milanko world3d grid.js (Goldberg geodesic grid)",
        "regions": meta.get("regions"),
        "region_frequency": meta.get("regionFrequency"),
        "codec": "code = face*262144 + i*512 + j (decode inverse)",
        "frequencies": frequencies,
        "biomes": meta.get("biomes", BIOMES),
        "flags": FLAG,
        "record_bytes": meta.get("record"),
        "base_layers": meta.get("layers"),
    }


def config() -> dict:
    meta = world_meta()
    return {
        "description": (
            "Data to render the planet as in the Milanko globe: hexagonal base world "
            "(biome, elevation, color, water) + GIBS imagery."
        ),
        "world_base_url": "/world/",
        "meta_url": "/world/meta.json",
        "base_urls": {
            "56": "/world/base-56.bin",
            "80": "/world/base-80.bin",
        },
        "fine_url_template": "/world/fine-288/r{region:03d}.bin",
        "cells_url": "/world/cells?f={f}&limit={limit}",
        "hexgrid_meta_url": "/hexgrid/meta",
        "hexbin_events_url": "/hexbin/events?f={f}&category=wildfires&status=all",
        "snapshot_url": "/world/snapshot?lat={lat}&lon={lon}&date={date}&km=220",
        "grid": grid_meta(),
        "base_layers": meta.get("layers"),
        "meta_generated": meta.get("generated"),
        "provenance": meta.get("source"),
        "format": {
            "header": "16 bytes: 'ETDW', version, level, f(u16), count(u32), region(u16), regionCount(u16)",
            "record": "13 bytes: code(u32), biome(u8), flags(u8), elevation(i16), rgb(3u8), lakeFrac(u8), lakePos(u8)",
            "note": "Same binary format as the Milanko world3d assets.",
        },
    }


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    """Parse 'west,south,east,north' (standard geographic order)."""
    if not value:
        return None
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must have 4 values: west,south,east,north")
    try:
        west, south, east, north = (float(part) for part in parts)
    except ValueError as exc:
        raise ValueError("bbox contains non-numeric values") from exc
    if south >= north:
        raise ValueError("bbox: south must be less than north")
    return west, south, east, north


def _inside_bbox(lon: float, lat: float, bbox: tuple[float, float, float, float]) -> bool:
    west, south, east, north = bbox
    if not (south <= lat <= north):
        return False
    if west <= east:
        return west <= lon <= east
    return lon >= west or lon <= east  # cruza el antimeridiano


# ------------------------------------------------------------------ world base
def world_cells(
    f: int = 80,
    *,
    biome: str | None = None,
    water: bool | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    limit: int = 2000,
    offset: int = 0,
) -> dict:
    header, records, grid = world_base(f)
    biome_index = None
    if biome:
        if biome not in BIOMES:
            raise ValueError(f"invalid biome: {biome} (options: {', '.join(BIOMES)})")
        biome_index = BIOMES.index(biome)
    matched: list[dict] = []
    for record in records:
        if biome_index is not None and record.biome != biome_index:
            continue
        if water is not None and record.water != water:
            continue
        face, i, j = decode(record.code)
        p = point(face, i, j, f)
        lat, lon = to_lat_lon(p)
        if bbox and not _inside_bbox(lon, lat, bbox):
            continue
        matched.append(
            {
                "code": record.code,
                "face": face,
                "i": i,
                "j": j,
                "region": grid.region_for_cell(record.code),
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "biome": record.biome_name,
                "biome_index": record.biome,
                "flags": record.flag_names,
                "elevation_m": record.elevation,
                "rgb": record.rgb_hex,
                "lake_fraction": round(record.lake_frac, 3),
                "water": record.water,
                "area_km2": round(cell_area_km2(f), 1),
            }
        )
    selected = matched[offset : offset + limit]
    return {
        "f": f,
        "total_cells": header.count,
        "matched": len(matched),
        "returned": len(selected),
        "offset": offset,
        "cells": selected,
    }


# --------------------------------------------------------------------- hexbin
def _hexbin_cell_payload(cell_row: dict, grid, include_geometry: bool) -> dict:
    content = {
        "code": cell_row["code"],
        "face": cell_row["face"],
        "i": cell_row["i"],
        "j": cell_row["j"],
        "region": cell_row["region"],
        "centroid": {"lat": round(cell_row["lat"], 6), "lon": round(cell_row["lon"], 6)},
        "count": cell_row["count"],
        "value": cell_row["value"],
    }
    if include_geometry:
        content["geometry"] = {
            "type": "Polygon",
            "coordinates": [grid.polygon_lonlat(cell_row["code"])],
        }
    return content


def hexbin_events(
    eonet: EonetClient,
    *,
    f: int = 80,
    categories: list[str] | None = None,
    status: str = "all",
    start: str | None = None,
    end: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    limit: int = 500,
    include_geometry: bool = False,
    geojson: bool = False,
) -> dict:
    _header, _records, grid = world_base(f)
    payload = eonet.events(
        status=status,
        category=categories,
        start=start,
        end=end,
        bbox=bbox,
        limit=limit,
    )
    events = EonetClient.parse_events(payload)
    items: list[dict] = []
    for event in events:
        if not event.geometry:
            continue
        geometry = min(event.geometry, key=lambda g: g.date)
        if len(geometry.coordinates) < 2:
            continue
        lon, lat = float(geometry.coordinates[0]), float(geometry.coordinates[1])
        items.append(
            {
                "lat": lat,
                "lon": lon,
                "id": event.id,
                "title": event.title,
                "date": geometry.date.isoformat() if geometry.date else None,
                "categories": event.categories,
                "magnitude_value": geometry.magnitude_value,
                "magnitude_unit": geometry.magnitude_unit,
            }
        )
    rows = grid.bin_items(items, aggregate="count")
    cells = []
    features = []
    for row in rows:
        cell = _hexbin_cell_payload(row, grid, include_geometry)
        events_list = row["items"]
        cell["events"] = events_list
        magnitude_totals: dict[str, float] = {}
        for item in events_list:
            unit = item.get("magnitude_unit")
            value = item.get("magnitude_value")
            if unit and value is not None:
                magnitude_totals[unit] = magnitude_totals.get(unit, 0.0) + float(value)
        cell["magnitude_totals"] = magnitude_totals or None
        cells.append(cell)
        geometry = cell.get("geometry") or {
            "type": "Point",
            "coordinates": [cell["centroid"]["lon"], cell["centroid"]["lat"]],
        }
        properties = {key: value for key, value in cell.items() if key != "geometry"}
        features.append(
            {"type": "Feature", "geometry": geometry, "properties": properties}
        )
    if geojson:
        return {
            "type": "FeatureCollection",
            "features": features,
            "properties": {"f": f, "events_total": len(events)},
        }
    return {"f": f, "events_total": len(events), "cells_returned": len(cells), "cells": cells}


def hexbin_points(
    body,
    *,
    f: int = 80,
    include_geometry: bool = False,
    geojson: bool = False,
) -> dict:
    _header, _records, grid = world_base(f)
    points = [
        {
            "lat": pt.lat,
            "lon": pt.lon,
            "value": pt.value,
            "label": pt.label,
        }
        for pt in body.points
    ]
    rows = grid.bin_items(points, aggregate=body.aggregate)
    cells = []
    features = []
    for row in rows:
        cell = _hexbin_cell_payload(row, grid, include_geometry)
        cell["n_values"] = row["n_values"]
        labels = [item.get("label") for item in row["items"] if item.get("label")]
        cell["labels"] = labels[:20]
        cells.append(cell)
        geometry = cell.get("geometry") or {
            "type": "Point",
            "coordinates": [cell["centroid"]["lon"], cell["centroid"]["lat"]],
        }
        properties = {key: value for key, value in cell.items() if key != "geometry"}
        features.append(
            {"type": "Feature", "geometry": geometry, "properties": properties}
        )
    if geojson:
        return {
            "type": "FeatureCollection",
            "features": features,
            "properties": {"f": f, "aggregation": body.aggregate},
        }
    return {
        "f": f,
        "aggregation": body.aggregate,
        "points_total": len(points),
        "cells_returned": len(cells),
        "cells": cells,
    }


# ------------------------------------------------------------------ planet view
def snapshot(
    gibs: GibsClient,
    *,
    lat: float,
    lon: float,
    date_str: str | None = None,
    km: float = 220.0,
    px: int = 480,
    layer: str = TRUE_COLOR_LAYER,
) -> bytes:
    if date_str:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("date must use YYYY-MM-DD format") from exc
        target = date_str
    else:
        target = (date.today() - timedelta(days=3)).isoformat()
    lat_span = km / 111.32
    lon_span = km / (111.32 * max(0.15, math.cos(math.radians(lat))))
    lat_min = max(-90.0, lat - lat_span / 2)
    lat_max = min(90.0, lat + lat_span / 2)
    lon_min = lon - lon_span / 2
    lon_max = lon + lon_span / 2
    if lon_min < -180:
        lon_min += 360
    if lon_max > 180:
        lon_max -= 360
    return gibs.wms_getmap(
        layer,
        target,
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
        width=px,
        height=px,
    )
