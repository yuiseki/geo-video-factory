"""corner_match: the vertical corners of the buildings, in the city model and in a photograph, by azimuth."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from geo import corner_match as cm  # noqa: E402
from geo import skyline_match as sm  # noqa: E402

BINS = 720


def box(x0, x1, y0, y1, z0, z1):
    c = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], float)
    quads = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]
    return np.array([[c[q[i]] for i in tri] for q in quads for tri in ((0, 1, 2), (0, 2, 3))])


def at(profile, azimuth):
    return profile[int(np.floor((azimuth % 360) / (360 / BINS))) % BINS]


def az(x, y):
    return np.degrees(np.arctan2(x, y)) % 360


def level_camera(heading, pitch=0.0):
    h, p = np.radians(heading), np.radians(pitch)
    z = np.array([np.sin(h) * np.cos(p), np.cos(h) * np.cos(p), np.sin(p)])
    x = np.array([np.cos(h), -np.sin(h), 0.0])
    return np.stack([x, np.cross(z, x), z])


class ModelCorners(unittest.TestCase):
    def setUp(self):
        self.prep = cm.prepare(box(-5, 5, 20, 30, 0, 20), height=4.6)

    def test_the_corners_of_the_near_face_show_and_those_behind_it_do_not(self):
        prof = cm.model_corners(self.prep, (0.0, 0.0), bins=BINS)
        self.assertEqual(at(prof, az(-5, 20)), 1.0)
        self.assertEqual(at(prof, az(5, 20)), 1.0)
        self.assertEqual(at(prof, az(-5, 30)), 0.0)          # behind the front face
        self.assertEqual(at(prof, az(5, 30)), 0.0)
        self.assertEqual(prof.sum(), 2.0)

    def test_from_the_side_the_corners_of_that_side_show(self):
        prof = cm.model_corners(self.prep, (20.0, 25.0), bins=BINS)
        self.assertEqual(at(prof, az(5 - 20, 20 - 25)), 1.0)
        self.assertEqual(at(prof, az(5 - 20, 30 - 25)), 1.0)
        self.assertEqual(at(prof, az(-5 - 20, 25 - 25)), 0.0)

    def test_a_low_wall_or_a_diagonal_is_not_a_corner(self):
        prep = cm.prepare(box(-5, 5, 20, 30, 0, 2), height=4.6)     # does not reach the height looked at
        self.assertEqual(cm.model_corners(prep, (0.0, 0.0), bins=BINS).sum(), 0.0)


class PhotoCorners(unittest.TestCase):
    def rays(self, heading=0.0, w=800, h=600, f=600.0):
        return sm.pixel_rays(w, h, f, w / 2, h / 2, 0.0, level_camera(heading, 10.0), step=1)

    def test_a_vertical_edge_peaks_at_its_azimuth(self):
        a, e = self.rays()
        gray = np.where(np.arange(800)[None, :] < 400, 40.0, 200.0) * np.ones((600, 1))
        prof = cm.photo_corners(a, e, gray, np.zeros((600, 800), bool), bins=BINS)
        self.assertEqual(int(np.nanargmax(prof)), int(np.floor(az(1e-9, 1) / 0.5)) % BINS)   # the centre column: north
        self.assertGreater(np.nanmax(prof), 0.5)
        self.assertTrue(np.isnan(at(prof, 180)))                 # not in the picture

    def test_a_level_edge_is_not_a_corner(self):
        a, e = self.rays()
        gray = np.where(np.arange(600)[:, None] < 300, 40.0, 200.0) * np.ones((1, 800))
        prof = cm.photo_corners(a, e, gray, np.zeros((600, 800), bool), bins=BINS)
        self.assertLess(np.nanmax(prof), 0.1)


class Cost(unittest.TestCase):
    def test_the_place_and_the_turn_are_found(self):
        tris = np.concatenate([box(-5, 5, 20, 30, 0, 20), box(8, 14, 25, 40, 0, 35), box(-30, -18, 5, 15, 0, 25)])
        prep = cm.prepare(tris, height=4.6)
        eyes = [(0.0, 0.0), (6.0, 0.0), (0.0, -8.0), (-6.0, 4.0)]
        model = np.stack([cm.model_corners(prep, e, bins=BINS) for e in eyes])
        photo = np.full(BINS, np.nan)
        seen = (np.arange(BINS) * 0.5 + 60) % 360 < 120           # the photo sees from 300 to 60 degrees
        photo[seen] = model[1][seen]
        cost = cm.corner_cost(photo, model)
        place, shift = np.unravel_index(np.nanargmin(cost), cost.shape)
        self.assertEqual(place, 1)
        self.assertIn(shift, (0, 1, BINS - 1))

    def test_a_photo_without_corners_says_nothing(self):
        model = np.zeros((3, BINS))
        model[:, 10] = 1
        photo = np.full(BINS, np.nan)
        photo[:100] = 0.0
        self.assertTrue(np.isnan(cm.corner_cost(photo, model)).all())


if __name__ == "__main__":
    unittest.main()
