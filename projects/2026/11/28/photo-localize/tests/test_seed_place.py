import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import seed_place as sp  # noqa: E402


class Seeded(unittest.TestCase):
    def test_the_camera_moves_to_the_photos_origin_and_its_lens_to_the_photos_size(self):
        cam = {"eye": [10.0, 20.0, 99.0], "Rw": [[1, 0, 0], [0, 0, -1], [0, 1, 0]], "width": 518, "height": 390,
               "params": [437.5, 437.5, 259.0, 195.0]}
        a, b = (139.7905, 35.7287), (139.7906, 35.7286)          # the photo's own origin, a little south-east
        s = sp.seeded(cam, a, b, 4080, 3072, 38.0)
        kx = 111320 * math.cos(math.radians(b[1]))
        self.assertAlmostEqual(s["eye"][0], 10.0 + (a[0] - b[0]) * kx)
        self.assertAlmostEqual(s["eye"][1], 20.0 + (a[1] - b[1]) * 110950)
        self.assertEqual(s["eye"][2], 38.0 + sp.EYE_HEIGHT)
        self.assertAlmostEqual(s["params"][0], 437.5 * 4080 / 518)
        self.assertEqual(s["params"][2:], [2040.0, 1536.0])

    def test_a_level_camera_looking_north(self):
        h, p, r = sp.heading_pitch_roll([[1, 0, 0], [0, 0, -1], [0, 1, 0]])
        self.assertAlmostEqual(h, 0.0)
        self.assertAlmostEqual(p, 0.0)
        self.assertAlmostEqual(r, 0.0)


if __name__ == "__main__":
    unittest.main()
