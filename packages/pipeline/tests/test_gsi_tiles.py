import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image

from support import import_pipeline

gsi_tiles = import_pipeline('geo.gsi_tiles')


def png_bytes(rgb: tuple[int, int, int], size: tuple[int, int] = (256, 256)) -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', size, rgb).save(buf, format='PNG')
    return buf.getvalue()


class GsiTilesTests(unittest.TestCase):
    def test_fractional_tile_and_bounds_round_trip(self):
        xf, yf = gsi_tiles.fractional_tile(135.50115, 34.66881, zoom=16)
        self.assertTrue(57400 < xf < 57500)
        self.assertTrue(26000 < yf < 26100)
        west, south, east, north = gsi_tiles.tile_bounds(int(xf), int(yf), width_tiles=2, height_tiles=2, zoom=16)
        self.assertLess(west, east)
        self.assertLess(south, north)
        self.assertGreaterEqual(135.50115, west)
        self.assertLessEqual(135.50115, east)

    def test_mask_dark_nodata_turns_near_black_pixels_transparent(self):
        img = Image.new('RGBA', (2, 1), (0, 0, 0, 255))
        img.putpixel((0, 0), (2, 3, 1, 255))
        img.putpixel((1, 0), (10, 20, 30, 255))
        masked = gsi_tiles.mask_dark_nodata(img, threshold=3)
        self.assertEqual(masked.getpixel((0, 0))[3], 0)
        self.assertEqual(masked.getpixel((1, 0)), (10, 20, 30, 255))

    def test_stitch_mosaic_counts_visible_pixels(self):
        tiles = {
            (0, 0): Image.new('RGBA', (256, 256), (100, 120, 140, 255)),
            (1, 0): Image.new('RGBA', (256, 256), (0, 0, 0, 0)),
        }
        canvas, visible, total = gsi_tiles.stitch_mosaic(tiles, 0, 0, width_tiles=2, height_tiles=2)
        self.assertEqual(canvas.size, (512, 512))
        self.assertEqual(total, 512 * 512)
        self.assertEqual(visible, 256 * 256)

    def test_collect_places_writes_mosaics_and_manifest(self):
        places = {
            'dotonbori': {
                'name': '道頓堀・戎橋周辺',
                'center': [135.50115, 34.66881],
                'layers': ['gazo1', 'std'],
            }
        }
        dark = png_bytes((1, 2, 1))
        bright = png_bytes((120, 160, 200))

        def fake_fetch(url: str) -> tuple[int, bytes]:
            return (200, dark if '/gazo1/' in url else bright)

        with TemporaryDirectory() as temp:
            out = Path(temp)
            manifest = gsi_tiles.collect_places(places, out, zoom=16, delay=0, fetcher=fake_fetch)
            self.assertTrue((out / 'manifest.json').is_file())
            saved = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['zoom'], 16)
            layers = manifest['places']['dotonbori']['layers']
            self.assertEqual(layers['gazo1']['visible_fraction'], 0.0)
            self.assertIsNone(layers['gazo1']['mosaic_file'])
            self.assertEqual(layers['std']['visible_fraction'], 1.0)
            self.assertEqual(layers['std']['mosaic_file'], 'dotonbori/std.png')
            self.assertTrue((out / 'dotonbori' / 'std.png').is_file())


if __name__ == '__main__':
    unittest.main()
