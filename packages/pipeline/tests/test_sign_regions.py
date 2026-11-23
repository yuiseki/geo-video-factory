import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sign_regions as sr  # noqa: E402


def polygon_mask(w, h, corners):
    """Filled convex polygon (corners in order) as a 0/255 array."""
    yy, xx = np.mgrid[0:h, 0:w]
    inside = np.ones((h, w), bool)
    n = len(corners)
    for k in range(n):
        (x0, y0), (x1, y1) = corners[k], corners[(k + 1) % n]
        inside &= (x1 - x0) * (yy - y0) - (y1 - y0) * (xx - x0) >= 0
    return (inside * 255).astype(np.uint8)


class SignQuadTests(unittest.TestCase):
    def test_a_rectangle_gives_its_four_corners_clockwise_from_top_left(self):
        m = np.zeros((100, 200), np.uint8)
        m[20:60, 30:130] = 255
        (q,) = sr.sign_quads(m)
        np.testing.assert_allclose(q["corners"], [[30, 20], [129, 20], [129, 59], [30, 59]], atol=1)

    def test_a_sign_seen_at_an_angle_gives_its_skewed_corners(self):
        corners = [(40, 20), (160, 40), (160, 90), (40, 80)]  # top-left, top-right, bottom-right, bottom-left
        m = polygon_mask(200, 120, corners)
        (q,) = sr.sign_quads(m)
        np.testing.assert_allclose(q["corners"], corners, atol=2)
        self.assertGreater(q["fill"], 0.95)

    def test_small_regions_are_dropped_and_the_rest_sorted_by_area(self):
        m = np.zeros((100, 200), np.uint8)
        m[10:20, 10:20] = 255  # 100 px
        m[40:90, 100:190] = 255  # 4500 px
        m[50:52, 20:22] = 255  # 4 px: noise
        qs = sr.sign_quads(m, min_area=0.002)
        self.assertEqual([q["area"] for q in qs], [4500, 100])

    def test_an_irregular_region_has_a_low_fill(self):
        m = np.zeros((100, 100), np.uint8)
        m[10:90, 10:20] = 255
        m[80:90, 10:90] = 255  # an L shape: not a sign face
        (q,) = sr.sign_quads(m)
        self.assertLess(q["fill"], 0.5)

    def test_a_triangle_has_no_four_corners_and_gets_zero_fill(self):
        m = polygon_mask(100, 100, [(10, 10), (90, 10), (10, 90)])  # two extreme points coincide
        (q,) = sr.sign_quads(m)
        self.assertEqual(q["fill"], 0.0)

    def test_soft_masks_are_thresholded(self):
        m = np.zeros((50, 50), np.uint8)
        m[10:40, 10:40] = 100
        self.assertEqual(sr.sign_quads(m), [])


class ReplaceJsonTests(unittest.TestCase):
    def test_flat_faces_go_to_signs_and_irregular_ones_to_skipped(self):
        quads = [{"corners": [[0, 0], [9, 0], [9, 9], [0, 9]], "area": 100, "fill": 0.98, "bbox": [0, 0, 10, 10]},
                 {"corners": [[0, 0], [9, 0], [9, 9], [0, 9]], "area": 40, "fill": 0.4, "bbox": [0, 0, 10, 10]}]
        doc = sr.replace_json("212", quads, (300, 200), min_fill=0.8)
        self.assertEqual([s["name"] for s in doc["signs"]], ["212_00"])
        self.assertEqual([s["name"] for s in doc["skipped"]], ["212_01"])
        self.assertEqual((doc["width"], doc["height"]), (300, 200))
        self.assertEqual(doc["signs"][0]["corners"], quads[0]["corners"])


class QuadAreaTests(unittest.TestCase):
    def test_shoelace_area(self):
        self.assertAlmostEqual(sr.quad_area([[0, 0], [10, 0], [10, 5], [0, 5]]), 50)


if __name__ == "__main__":
    unittest.main()
