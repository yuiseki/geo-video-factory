"""vanishing: which way the level lines of a photograph run, against the walls of the city model."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from geo import vanishing as vp  # noqa: E402
from geo import skyline_match as sm  # noqa: E402


def camera(heading, pitch=8.0):
    h, p = np.radians(heading), np.radians(pitch)
    z = np.array([np.sin(h) * np.cos(p), np.cos(h) * np.cos(p), np.sin(p)])
    x = np.array([np.cos(h), -np.sin(h), 0.0])
    return np.stack([x, np.cross(z, x), z])


def wall_photo(heading, wall_normal_az, stripes="level", w=640, h=480, f=500.0):
    """A camera at the origin, 1.6 m up, before a wall 15 m away in the direction wall_normal_az (its normal)."""
    R = camera(heading)
    a, e = sm.pixel_rays(w, h, f, w / 2, h / 2, 0.0, R, step=1)
    ray = vp.ray_vectors(a, e)
    m = np.array([np.sin(np.radians(wall_normal_az)), np.cos(np.radians(wall_normal_az)), 0.0])
    t = 15.0 / np.maximum(ray @ m, 1e-6)
    p = ray * t[..., None] + np.array([0, 0, 1.6])
    along = p @ np.array([m[1], -m[0], 0.0])
    gray = (np.sin(p[..., 2] * 2.0) if stripes == "level" else np.sin(along * 2.0)) * 100 + 128
    return a, e, gray


class PhotoLines(unittest.TestCase):
    def test_level_lines_on_a_wall_run_across_its_normal(self):
        a, e, gray = wall_photo(heading=30.0, wall_normal_az=40.0)
        hist = vp.photo_azimuths(a, e, gray)
        self.assertEqual(len(hist), 180)
        peak = int(np.argmax(hist))
        self.assertLessEqual(min(abs(peak - 130) % 180, 180 - abs(peak - 130) % 180), 2)

    def test_upright_lines_cast_no_vote(self):
        _, _, level = wall_photo(heading=30.0, wall_normal_az=40.0)
        a, e, upright = wall_photo(heading=30.0, wall_normal_az=40.0, stripes="upright")
        self.assertLess(vp.photo_azimuths(a, e, upright).sum(), 0.2 * vp.photo_azimuths(a, e, level).sum())


class ModelWalls(unittest.TestCase):
    def test_a_box_runs_along_its_sides(self):
        c = np.array([[x, y, z] for x in (-5, 5) for y in (20, 40) for z in (0, 20)], float)
        quads = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6)]
        tris = np.array([[c[q[i]] for i in t] for q in quads for t in ((0, 1, 2), (0, 2, 3))])
        hist = vp.model_azimuths(tris, (0.0, 0.0), radius=100)
        self.assertEqual(set(np.flatnonzero(hist > 0.1 * hist.max())), {0, 90})


class Turn(unittest.TestCase):
    def test_the_turn_lays_the_photo_on_the_model(self):
        model = np.zeros(180)
        model[[10, 100]] = 1.0
        photo = np.roll(model, 7)          # the photo thinks the walls run 7 degrees further clockwise
        cost = vp.turn_cost(photo, model)
        self.assertEqual(len(cost), 180)
        self.assertIn(int(np.argmin(cost)) % 90, (90 - 7,))


if __name__ == "__main__":
    unittest.main()
