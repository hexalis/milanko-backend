"""Unit tests for GIBS capabilities parsing and palette decoding (PoC fixtures)."""
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "tests" / "fixtures"

from core.nasa_events.palettes import FIRE_RGBA, FLOOD_RGBA  # noqa: E402
from core.nasa_events.sources.gibs import GibsClient, parse_capabilities, time_dimension  # noqa: E402

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:  # pragma: no cover - depends on environment
    HAS_PIL = False


class GibsCapabilitiesTest(unittest.TestCase):
    def test_parse_capabilities(self):
        xml_path = SAMPLES / "gibs" / "WMTSCapabilities.xml"
        if not xml_path.exists():
            self.skipTest("fixture de capabilities no disponible")
        summary = parse_capabilities(xml_path)
        self.assertGreater(len(summary), 1000)
        layer = summary["MODIS_Terra_CorrectedReflectance_TrueColor"]
        self.assertIn("image/jpeg", layer["formats"])
        self.assertIn("250m", layer["tms"])

    def test_time_dimension(self):
        info = {"dimensions": {"Time": {"default": "2026-10-10"}}}
        self.assertEqual(time_dimension(info)["default"], "2026-10-10")
        self.assertEqual(time_dimension({}), {})


@unittest.skipUnless(HAS_PIL, "Pillow no disponible en este intérprete")
class GibsDecodeTest(unittest.TestCase):
    def test_fire_palette(self):
        png = (SAMPLES / "gibs" / "wms" / "poc_termico_africa.png").read_bytes()
        counts = GibsClient.decode_palette(png, FIRE_RGBA)
        self.assertGreater(counts["fire"], 0)
        self.assertFalse(GibsClient.is_blank(png))
        palette = GibsClient.palette_counts(png, top=5)
        self.assertGreater(len(palette), 0)

    def test_flood_palette(self):
        png = (SAMPLES / "gibs" / "wms" / "poc_inundacion_bangladesh.png").read_bytes()
        counts = GibsClient.decode_palette(png, FLOOD_RGBA)
        self.assertGreater(counts["flood_water"], 0)
        self.assertGreater(counts["reference"], 0)

    def test_blank_detection(self):
        blank = (SAMPLES / "gibs" / "wms" / "poc_hielo_marino_antartico.png").read_bytes()
        self.assertTrue(GibsClient.is_blank(blank))
        image = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        self.assertTrue(GibsClient.is_blank(buffer.getvalue()))
        filled = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
        buffer2 = io.BytesIO()
        filled.save(buffer2, "PNG")
        self.assertFalse(GibsClient.is_blank(buffer2.getvalue()))

    def test_wms_bbox_validation(self):
        client = GibsClient(use_cache=False)
        with self.assertRaises(ValueError):
            client.wms_getmap(
                "MODIS_Terra_CorrectedReflectance_TrueColor",
                "2026-10-10",
                lat_min=-33.0,
                lat_max=-34.0,
                lon_min=-71.0,
                lon_max=-70.0,
            )


if __name__ == "__main__":
    unittest.main()
