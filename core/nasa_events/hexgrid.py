"""Geodesic hexagonal grid (Goldberg polyhedron) and hex binning.

Python port of the Milanko `world3d/grid.js`, so cell codes match the
globe/3D world exactly (same cells, same regions, same geometry).

Grid facts
----------
- 20 icosahedron faces; each face is split into f x f triangles.
- Every lattice point is a hexagon (or one of the 12 pentagons at icosahedron corners).
- Cell code: ``face * 262144 + i * 512 + j`` (decode is the inverse).
- 162 regions = cells(f=4); base levels: f=56 (31.362 cells), f=80 (64.002 cells),
  fine level: f=288 (829.442 cells).
- Cell records in ``data/world/*.bin`` are 13 bytes: see ``nasa_events.worldbase``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

PHI = (1 + math.sqrt(5)) / 2
REGION_F = 4
RECORD = 13
FLAG = {
    "water": 1,
    "lakeBody": 2,
    "coast": 4,
    "elev": 8,
    "ridge1": 16,
    "ridge2": 32,
    "lake": 64,
}
BIOMES = [
    "deep",
    "sea",
    "shelf",
    "lake",
    "desert",
    "shrub",
    "grass",
    "crop",
    "savanna",
    "rainforest",
    "forest",
    "conifer",
    "wetland",
    "tundra",
    "ice",
    "mountain",
    "urban",
]
OFFSETS = ((1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1))


def _norm(x: float, y: float, z: float) -> tuple[float, float, float]:
    length = math.hypot(x, y, z)
    return (x / length, y / length, z / length)


ICO_V = [
    _norm(*vector)
    for vector in (
        (-1, PHI, 0),
        (1, PHI, 0),
        (-1, -PHI, 0),
        (1, -PHI, 0),
        (0, -1, PHI),
        (0, 1, PHI),
        (0, -1, -PHI),
        (0, 1, -PHI),
        (PHI, 0, -1),
        (PHI, 0, 1),
        (-PHI, 0, -1),
        (-PHI, 0, 1),
    )
]
ICO_F = [
    (0, 11, 5),
    (0, 5, 1),
    (0, 1, 7),
    (0, 7, 10),
    (0, 10, 11),
    (1, 5, 9),
    (5, 11, 4),
    (11, 10, 2),
    (10, 7, 6),
    (7, 1, 8),
    (3, 9, 4),
    (3, 4, 2),
    (3, 2, 6),
    (3, 6, 8),
    (3, 8, 9),
    (4, 9, 5),
    (2, 4, 11),
    (6, 2, 10),
    (8, 6, 7),
    (9, 8, 1),
]

# ACROSS[face][k] = far corner of the neighbouring face across the edge opposite k
ACROSS: list[list[int]] = []
for _face in ICO_F:
    _row = []
    for _k in range(3):
        _y, _z = _face[(_k + 1) % 3], _face[(_k + 2) % 3]
        _other = next(face for face in ICO_F if face != _face and _y in face and _z in face)
        _row.append(next(vertex for vertex in _other if vertex not in (_y, _z)))
    ACROSS.append(_row)


def _js_round(value: float) -> int:
    return math.floor(value + 0.5)


def code(face: int, i: int, j: int) -> int:
    return face * 262144 + i * 512 + j


def decode(cell: int) -> tuple[int, int, int]:
    return cell // 262144, (cell // 512) % 512, cell % 512


def point(face: int, i: int, j: int, f: int) -> tuple[float, float, float]:
    a, b, c = ICO_F[face]
    A, B, C = ICO_V[a], ICO_V[b], ICO_V[c]
    u, v = i / f, j / f
    w = 1 - u - v
    return _norm(
        A[0] * w + B[0] * u + C[0] * v,
        A[1] * w + B[1] * u + C[1] * v,
        A[2] * w + B[2] * u + C[2] * v,
    )


def _point_near(face: int, i: int, j: int, f: int) -> tuple[float, float, float]:
    face_vertices = ICO_F[face]
    weights = [f - i - j, i, j]
    k = next((index for index, weight in enumerate(weights) if weight < 0), -1)
    if k < 0:
        return point(face, i, j, f)
    y, z = (k + 1) % 3, (k + 2) % 3
    parts = (
        (face_vertices[y], weights[y] + weights[k]),
        (face_vertices[z], weights[z] + weights[k]),
        (ACROSS[face][k], -weights[k]),
    )
    x = yy = zz = 0.0
    for vertex, weight in parts:
        V = ICO_V[vertex]
        x += V[0] * weight
        yy += V[1] * weight
        zz += V[2] * weight
    return _norm(x, yy, zz)


def basis(p: tuple[float, float, float]) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    up = (0.0, 1.0, 0.0) if abs(p[1]) < 0.9 else (1.0, 0.0, 0.0)
    e1 = _norm(
        p[1] * up[2] - p[2] * up[1],
        p[2] * up[0] - p[0] * up[2],
        p[0] * up[1] - p[1] * up[0],
    )
    e2 = (
        p[1] * e1[2] - p[2] * e1[1],
        p[2] * e1[0] - p[0] * e1[2],
        p[0] * e1[1] - p[1] * e1[0],
    )
    return e1, e2


def to_lat_lon(p: tuple[float, float, float]) -> tuple[float, float]:
    return (
        math.degrees(math.asin(max(-1.0, min(1.0, p[1])))),
        math.degrees(math.atan2(p[0], p[2])),
    )


def to_vec(lat: float, lon: float) -> tuple[float, float, float]:
    a, b = math.radians(lat), math.radians(lon)
    return (math.cos(a) * math.sin(b), math.sin(a), math.cos(a) * math.cos(b))


@lru_cache(maxsize=None)
def cells(f: int) -> tuple[int, ...]:
    """Every cell of the grid once (edge points belong to the first face that has them)."""
    seen: set[tuple[int, int, int]] = set()
    result: list[int] = []
    for face in range(20):
        for i in range(f + 1):
            for j in range(f - i + 1):
                p = point(face, i, j, f)
                key = (
                    _js_round(p[0] * 1e6),
                    _js_round(p[1] * 1e6),
                    _js_round(p[2] * 1e6),
                )
                if key in seen:
                    continue
                seen.add(key)
                result.append(code(face, i, j))
    return tuple(result)


def _pentagon_neighbours(vertex: int, f: int) -> list[tuple[float, float, float]]:
    points: list[tuple[float, float, float]] = []
    seen: set[tuple[int, int, int]] = set()
    for face, face_vertices in enumerate(ICO_F):
        if vertex not in face_vertices:
            continue
        at = face_vertices.index(vertex)
        if at == 0:
            pairs = ((1, 0), (0, 1))
        elif at == 1:
            pairs = ((f - 1, 0), (f - 1, 1))
        else:
            pairs = ((0, f - 1), (1, f - 1))
        for i, j in pairs:
            p = point(face, i, j, f)
            key = (_js_round(p[0] * 1e6), _js_round(p[1] * 1e6), _js_round(p[2] * 1e6))
            if key in seen:
                continue
            seen.add(key)
            points.append(p)
    return points


def _corner_of(face: int, i: int, j: int, f: int) -> int:
    if j == 0 and i == 0:
        return ICO_F[face][0]
    if j == 0 and i == f:
        return ICO_F[face][1]
    if i == 0 and j == f:
        return ICO_F[face][2]
    return -1


def cell_geometry(
    cell: int, f: int
) -> tuple[tuple[float, float, float], list[tuple[float, float, float]]]:
    """Return (center, corners) in unit-sphere coordinates."""
    face, i, j = decode(cell)
    center = point(face, i, j, f)
    vertex = _corner_of(face, i, j, f)
    if vertex >= 0:
        neighbours = _pentagon_neighbours(vertex, f)
    else:
        neighbours = [_point_near(face, i + di, j + dj, f) for di, dj in OFFSETS]
    e1, e2 = basis(center)
    angles = [
        math.atan2(
            n[0] * e2[0] + n[1] * e2[1] + n[2] * e2[2],
            n[0] * e1[0] + n[1] * e1[1] + n[2] * e1[2],
        )
        for n in neighbours
    ]
    order = sorted(range(len(neighbours)), key=lambda index: angles[index])
    ordered = [neighbours[index] for index in order]
    corners = []
    for t, n in enumerate(ordered):
        m = ordered[(t + 1) % len(ordered)]
        corners.append(
            _norm(center[0] + n[0] + m[0], center[1] + n[1] + m[1], center[2] + n[2] + m[2])
        )
    return center, corners


@lru_cache(maxsize=1)
def region_centres() -> tuple[tuple[float, float, float], ...]:
    return tuple(point(*decode(cell), REGION_F) for cell in cells(REGION_F))


def region_of(p: tuple[float, float, float]) -> int:
    centres = region_centres()
    best, best_dot = 0, -2.0
    for index, c in enumerate(centres):
        dot = c[0] * p[0] + c[1] * p[1] + c[2] * p[2]
        if dot > best_dot:
            best_dot, best = dot, index
    return best


@dataclass(slots=True, frozen=True)
class CellRef:
    code: int
    face: int
    i: int
    j: int
    region: int
    lat: float
    lon: float


def cell_ref(cell: int, f: int) -> CellRef:
    face, i, j = decode(cell)
    p = point(face, i, j, f)
    lat, lon = to_lat_lon(p)
    return CellRef(
        code=cell,
        face=face,
        i=i,
        j=j,
        region=region_of(p),
        lat=lat,
        lon=lon,
    )


EARTH_AREA_KM2 = 510_072_000.0


def cell_area_km2(f: int) -> float:
    return EARTH_AREA_KM2 / len(cells(f))


def cell_across_km(f: int) -> float:
    """Approximate corner-to-corner width of a regular hexagon with that mean area."""
    area = cell_area_km2(f)
    side = math.sqrt(2.0 * area / (3.0 * math.sqrt(3.0)))
    return 2.0 * side


class HexGrid:
    """Binning helper on top of the geodesic grid (cell lookup by nearest centre)."""

    def __init__(self, f: int, cell_regions: dict[int, int] | None = None):
        self.f = int(f)
        self.codes = cells(self.f)
        self._centres = {cell: point(*decode(cell), self.f) for cell in self.codes}
        self._provided_regions = cell_regions
        self._groups: dict[int, list[int]] | None = None

    def _region_groups(self) -> dict[int, list[int]]:
        if self._groups is None:
            if self._provided_regions:
                groups: dict[int, list[int]] = {}
                for cell, region in self._provided_regions.items():
                    groups.setdefault(region, []).append(cell)
                self._groups = groups
            else:
                groups = {}
                for cell in self.codes:
                    region = region_of(self._centres[cell])
                    groups.setdefault(region, []).append(cell)
                self._groups = groups
        return self._groups

    def cell_for_point(self, lat: float, lon: float) -> int:
        p = to_vec(lat, lon)
        centres = region_centres()
        scored = sorted(
            (
                (c[0] * p[0] + c[1] * p[1] + c[2] * p[2], index)
                for index, c in enumerate(centres)
            ),
            reverse=True,
        )
        groups = self._region_groups()
        best_cell = -1
        best_dot = -2.0
        for _score, region in scored[:6]:
            for cell in groups.get(region, ()):
                q = self._centres[cell]
                dot = q[0] * p[0] + q[1] * p[1] + q[2] * p[2]
                if dot > best_dot:
                    best_dot, best_cell = dot, cell
        if best_cell < 0:
            raise ValueError("No cell found for the point")
        return best_cell

    def region_for_cell(self, cell: int) -> int:
        if self._provided_regions and cell in self._provided_regions:
            return self._provided_regions[cell]
        return region_of(self._centres[cell])

    def ref(self, cell: int) -> CellRef:
        face, i, j = decode(cell)
        lat, lon = to_lat_lon(self._centres[cell])
        return CellRef(
            code=cell,
            face=face,
            i=i,
            j=j,
            region=self.region_for_cell(cell),
            lat=lat,
            lon=lon,
        )

    def polygon_lonlat(self, cell: int, closed: bool = True) -> list[list[float]]:
        _center, corners = cell_geometry(cell, self.f)
        ring = [[lon, lat] for lat, lon in (to_lat_lon(corner) for corner in corners)]
        if closed and ring:
            ring.append(ring[0])
        return ring

    def bin_items(
        self,
        items: list[dict],
        *,
        aggregate: str = "count",
        value_key: str = "value",
        keep_items: bool = True,
    ) -> list[dict]:
        if aggregate not in ("count", "sum", "mean", "max"):
            raise ValueError("aggregate must be count, sum, mean or max")
        buckets: dict[int, dict] = {}
        for item in items:
            cell = self.cell_for_point(float(item["lat"]), float(item["lon"]))
            bucket = buckets.setdefault(cell, {"count": 0, "values": [], "items": []})
            bucket["count"] += 1
            value = item.get(value_key)
            if value is not None:
                try:
                    bucket["values"].append(float(value))
                except (TypeError, ValueError):
                    pass
            if keep_items:
                bucket["items"].append(
                    {key: value for key, value in item.items() if key not in ("lat", "lon")}
                )
        results: list[dict] = []
        for cell, bucket in buckets.items():
            values = bucket["values"]
            if aggregate == "count":
                value = float(bucket["count"])
            elif not values:
                value = None
            elif aggregate == "sum":
                value = sum(values)
            elif aggregate == "mean":
                value = sum(values) / len(values)
            else:
                value = max(values)
            ref = self.ref(cell)
            results.append(
                {
                    "code": ref.code,
                    "face": ref.face,
                    "i": ref.i,
                    "j": ref.j,
                    "region": ref.region,
                    "lat": ref.lat,
                    "lon": ref.lon,
                    "count": bucket["count"],
                    "value": value,
                    "n_values": len(values),
                    "items": bucket["items"],
                }
            )
        results.sort(key=lambda row: row["count"], reverse=True)
        return results


_GRIDS: dict[int, HexGrid] = {}


def get_grid(f: int, cell_regions: dict[int, int] | None = None) -> HexGrid:
    """Cached HexGrid per frequency (optionally seeded with code→region from a base file)."""
    if f not in _GRIDS:
        _GRIDS[f] = HexGrid(f, cell_regions=cell_regions)
    return _GRIDS[f]
