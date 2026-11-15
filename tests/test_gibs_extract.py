"""Tests for the GIBS palette/extraction foundation."""
import io
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from core.nasa_events.gibs_extract import LAYERS, extract_png, load_palettes, palette_for
from core.nasa_events.gibs_regions import REGION_COUNT, build_region_map


class GibsPaletteTest(unittest.TestCase):
    def test_all_layers_have_palettes(self):
        palettes = load_palettes()["layers"]
        self.assertEqual(set(LAYERS), set(palettes))
        for variable in LAYERS:
            self.assertGreater(len(palette_for(variable)), 10, variable)

    def test_palette_values_are_finite(self):
        for variable in LAYERS:
            values = list(palette_for(variable).values())
            self.assertTrue(all(np.isfinite(values)), variable)


class GibsRegionMapTest(unittest.TestCase):
    def test_region_map_shape_and_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            region_id, weight = build_region_map(8, 4, cache_dir=Path(tmp))
        self.assertEqual(region_id.shape, (4, 8))
        self.assertEqual(weight.shape, (4, 8))
        self.assertTrue(np.issubdtype(region_id.dtype, np.integer))
        self.assertGreaterEqual(region_id.min(), 0)
        self.assertLess(region_id.max(), REGION_COUNT)
        self.assertTrue(np.all(weight > 0))


class GibsExtractionTest(unittest.TestCase):
    def _png(self, color, count=1):
        pixels = np.zeros((2, 2, 4), dtype=np.uint8)
        pixels.reshape(-1, 4)[:count] = (*color, 255)
        buffer = io.BytesIO()
        Image.fromarray(pixels, "RGBA").save(buffer, "PNG")
        return buffer.getvalue()

    def test_extracts_known_color(self):
        variable = "SST"
        rgb_text = next(iter(palette_for(variable)))
        color = tuple(int(part) for part in rgb_text.split(","))
        expected = palette_for(variable)[rgb_text]
        region_id = np.zeros((2, 2), dtype=np.int16)
        weight = np.ones((2, 2), dtype=np.float32)
        rows = extract_png(
            self._png(color, count=2),
            LAYERS[variable],
            region_id,
            weight,
        )
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["value"], expected, places=5)
        self.assertAlmostEqual(rows[0]["valid_fraction"], 0.5, places=5)
        self.assertEqual(rows[0]["quality"], "ok")

    def test_unknown_color_is_reported(self):
        region_id = np.zeros((2, 2), dtype=np.int16)
        weight = np.ones((2, 2), dtype=np.float32)
        rows = extract_png(
            self._png((1, 2, 3)),
            LAYERS["SST"],
            region_id,
            weight,
        )
        self.assertEqual(rows[0]["quality"], "error")
        self.assertGreater(rows[0]["unknown_color_fraction"], 0)


if __name__ == "__main__":
    unittest.main()
