"""Tests for the geodesic hex grid and the ETDW world-base reader."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from core.nasa_events.hexgrid import (  # noqa: E402
    cell_geometry,
    cells,
    code,
    decode,
    get_grid,
)
from core.nasa_events.worldbase import read_world_file, region_map  # noqa: E402

WORLD_DIR = ROOT / "core" / "static" / "world"


class HexGridTest(unittest.TestCase):
    def test_cell_counts_match_grid(self):
        self.assertEqual(len(cells(4)), 162)  # regions
        self.assertEqual(len(cells(56)), 31362)
        self.assertEqual(len(cells(80)), 64002)

    def test_codec_roundtrip(self):
        for face, i, j in ((0, 0, 0), (7, 3, 4), (19, 80, 0)):
            self.assertEqual(decode(code(face, i, j)), (face, i, j))

    def test_cell_geometry(self):
        _center, corners = cell_geometry(cells(4)[0], 4)
        self.assertIn(len(corners), (5, 6))

    def test_world_base_reader(self):
        header, records = read_world_file(WORLD_DIR / "base-56.bin")
        self.assertEqual(header.f, 56)
        self.assertEqual(header.count, 31362)
        self.assertEqual(header.region_count, 162)
        self.assertEqual(len(records), 31362)
        mapping = region_map(header, records)
        self.assertEqual(len(mapping), 31362)
        self.assertTrue(all(0 <= region < 162 for region in mapping.values()))

    def test_binning_and_polygon(self):
        header, records = read_world_file(WORLD_DIR / "base-80.bin")
        grid = get_grid(80, region_map(header, records))
        santiago = grid.cell_for_point(-33.45, -70.66)
        self.assertEqual(grid.cell_for_point(-33.45, -70.66), santiago)
        self.assertNotEqual(grid.cell_for_point(40.0, -3.0), santiago)
        rows = grid.bin_items(
            [
                {"lat": -33.45, "lon": -70.66, "value": 1.0},
                {"lat": -33.44, "lon": -70.65, "value": 3.0},
            ],
            aggregate="mean",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["count"], 2)
        self.assertAlmostEqual(rows[0]["value"], 2.0)
        ring = grid.polygon_lonlat(santiago)
        self.assertGreaterEqual(len(ring), 6)
        self.assertEqual(ring[0], ring[-1])


if __name__ == "__main__":
    unittest.main()
