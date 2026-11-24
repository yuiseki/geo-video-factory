import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from buildings import sign_replace as sr  # noqa: E402


class HomographyTests(unittest.TestCase):
    def test_maps_each_point_to_its_partner(self):
        src = [(0, 0), (100, 0), (100, 50), (0, 50)]
        dst = [(10, 20), (210, 40), (200, 160), (5, 140)]
        h = sr.homography(src, dst)
        for (x, y), (u, v) in zip(src, dst):
            got = sr.apply_homography(h, (x, y))
            self.assertAlmostEqual(got[0], u, places=6)
            self.assertAlmostEqual(got[1], v, places=6)


class ColourFieldTests(unittest.TestCase):
    def setUp(self):
        # A sign face: blue top half with white text-like bars, green bottom half.
        self.face = Image.new("RGB", (200, 120), (20, 60, 220))
        d = ImageDraw.Draw(self.face)
        d.rectangle([0, 60, 200, 120], fill=(30, 200, 60))
        for x in range(20, 180, 30):
            d.rectangle([x, 20, x + 12, 40], fill=(255, 255, 255))

    def test_field_keeps_block_means(self):
        field = sr.colour_field(self.face, (4, 2))
        self.assertEqual(field.shape, (2, 4, 3))
        a = np.asarray(self.face, np.float32)
        self.assertTrue(np.allclose(field[1, 0], a[60:, :50].reshape(-1, 3).mean(0), atol=0.5))

    def test_recoloured_art_keeps_the_colour_layout_and_drops_the_original_detail(self):
        rng = np.random.default_rng(3)
        art = sr.recolour(self.face, sr.pattern("stripes", self.face.size, rng), grid=(4, 2))
        a, b = np.asarray(self.face, np.float32), np.asarray(art, np.float32)
        # Overall colour is kept, and the blue-top / green-bottom layout survives the smoothing.
        self.assertLess(np.abs(b.reshape(-1, 3).mean(0) - a.reshape(-1, 3).mean(0)).max(), 8.0)
        self.assertGreater(b[:40, :, 2].mean(), b[:40, :, 1].mean())   # top stays blue
        self.assertGreater(b[80:, :, 1].mean(), b[80:, :, 2].mean())   # bottom stays green
        # The text bars are gone: the white bar column now matches its stripe pattern, not the original.
        self.assertGreater(np.abs(b[20:40, 20:32] - a[20:40, 20:32]).mean(), 20)

    def test_patterns_are_deterministic_and_mean_one(self):
        for kind in sr.PATTERNS:
            p1 = sr.pattern(kind, (120, 80), np.random.default_rng(7))
            p2 = sr.pattern(kind, (120, 80), np.random.default_rng(7))
            self.assertTrue(np.array_equal(p1, p2), kind)
            self.assertAlmostEqual(float(p1.mean()), 1.0, places=2)


class PasteTests(unittest.TestCase):
    def test_paste_fills_the_quad_and_leaves_the_rest(self):
        photo = Image.new("RGB", (300, 200), (0, 0, 0))
        art = Image.new("RGB", (100, 50), (255, 0, 0))
        quad = [(50, 40), (200, 60), (190, 150), (60, 140)]
        out = np.asarray(sr.paste_quad(photo, art, quad, feather=0))
        self.assertEqual(tuple(out[100, 125]), (255, 0, 0))  # inside
        self.assertEqual(tuple(out[10, 10]), (0, 0, 0))  # outside


if __name__ == "__main__":
    unittest.main()
