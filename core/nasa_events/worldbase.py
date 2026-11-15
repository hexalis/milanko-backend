"""Reader for the POC's ETDW world-base binaries (planet appearance layer).

Format (from portal/world3d/grid.js + scripts/build_world.mjs):
  Header (16 bytes, little-endian):
    magic "ETDW", version, level, f (u16), count (u32), region (u16), region_count (u16)
  Base level (level=0): region offsets (region_count+1 u32) then `count` records
  Fine level (level=1): no offsets (one region per file) then `count` records
  Record (13 bytes, little-endian):
    code (u32), biome (u8), flags (u8), elevation (i16),
    rgb (3 × u8), lake_frac (u8), lake_pos (u8)
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from .hexgrid import BIOMES, FLAG


@dataclass(slots=True)
class WorldHeader:
    version: int
    level: int
    f: int
    count: int
    region: int
    region_count: int
    offsets: tuple[int, ...] | None = None


@dataclass(slots=True)
class WorldCellRecord:
    code: int
    biome: int
    flags: int
    elevation: int | None
    r: int
    g: int
    b: int
    lake_frac: float
    lake_pos: int

    @property
    def biome_name(self) -> str:
        return BIOMES[self.biome] if 0 <= self.biome < len(BIOMES) else "unknown"

    @property
    def flag_names(self) -> list[str]:
        return [name for name, bit in FLAG.items() if self.flags & bit]

    @property
    def rgb_hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    @property
    def water(self) -> bool:
        return bool(self.flags & FLAG["water"])


def read_world(data: bytes) -> tuple[WorldHeader, list[WorldCellRecord]]:
    if len(data) < 16:
        raise ValueError("world base file too short")
    magic, version, level, f, count, region, region_count = struct.unpack_from(
        "<4sBBHIHH", data, 0
    )
    if magic != b"ETDW":
        raise ValueError(f"invalid signature: {magic!r} (expected ETDW)")
    offset = 16
    offsets: tuple[int, ...] | None = None
    if level == 0:
        offsets = struct.unpack_from(f"<{region_count + 1}I", data, offset)
        offset += 4 * (region_count + 1)
    records: list[WorldCellRecord] = []
    for _ in range(count):
        if offset + 13 > len(data):
            raise ValueError("world base file truncated")
        cell, biome, flags, elev_raw, r, g, b, lake_frac, lake_pos = struct.unpack_from(
            "<IBBhBBBBB", data, offset
        )
        offset += 13
        records.append(
            WorldCellRecord(
                code=cell,
                biome=biome,
                flags=flags,
                elevation=elev_raw if flags & FLAG["elev"] else None,
                r=r,
                g=g,
                b=b,
                lake_frac=(lake_frac / 255.0) if flags & FLAG["lake"] else 0.0,
                lake_pos=lake_pos,
            )
        )
    return (
        WorldHeader(
            version=version,
            level=level,
            f=f,
            count=count,
            region=region,
            region_count=region_count,
            offsets=offsets,
        ),
        records,
    )


def read_world_file(path: Path) -> tuple[WorldHeader, list[WorldCellRecord]]:
    return read_world(Path(path).read_bytes())


def region_map(header: WorldHeader, records: list[WorldCellRecord]) -> dict[int, int]:
    """code -> region index, using the base file's region offsets."""
    mapping: dict[int, int] = {}
    if not header.offsets:
        return mapping
    offsets = header.offsets
    for region in range(header.region_count):
        start, end = offsets[region], offsets[region + 1]
        for record in records[start:end]:
            mapping[record.code] = region
    return mapping
