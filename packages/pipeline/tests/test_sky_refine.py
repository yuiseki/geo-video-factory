"""sky_refine: an SfM model already near its place, moved as a whole (turn, shift, scale) until the line between the
buildings and the sky in every photo lies on the city model's roofline."""
import math
import unittest

import numpy as np

from support import import_pipeline

sr = import_pipeline("world_model.sky_refine")
sa = import_pipeline("world_model.surface_atlas")


def box(x0, y0, x1, y1, h):
    p = [[x0, y0, 0], [x1, y0, 0], [x1, y1, 0], [x0, y1, 0], [x0, y0, h], [x1, y0, h], [x1, y1, h], [x0, y1, h]]
    faces = [(0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7), (4, 5, 6), (4, 6, 7)]
    return [[p[i] for i in f] for f in faces]


GROUND = [[[-500, -500, 0], [500, -500, 0], [500, 500, 0]], [[-500, -500, 0], [500, 500, 0], [-500, 500, 0]]]
TRIS = np.array(box(20, -15, 40, 15, 30) + box(-30, 30, -10, 50, 45) + box(-45, -40, -25, -20, 20) + GROUND, float)


def camera(x, y, yaw):
    """Level camera at eye height looking towards yaw (clockwise from north): R world -> camera (x right, y down)."""
    t = math.radians(yaw)
    fwd = np.array([math.sin(t), math.cos(t), 0.0])
    right = np.array([math.cos(t), -math.sin(t), 0.0])
    down = np.array([0.0, 0.0, -1.0])
    return {"eye": [x, y, 1.6], "Rw": np.array([right, down, fwd]).tolist(), "width": 256, "height": 192,
            "params": [140.0, 140.0, 128.0, 96.0], "distortion": [0.0]}


CAMS = {"a": camera(0, 0, 90), "b": camera(5, -5, 20), "c": camera(-5, 5, 300), "d": camera(2, 8, 210)}


def mask(cam):
    return ~np.isfinite(sa.depth_buffer(TRIS, cam, scale=1.0))


class SkyMask(unittest.TestCase):
    def test_the_sky_is_the_blue_reaching_down_from_the_top(self):
        img = np.full((40, 60, 3), 120, np.uint8)
        img[:15] = (70, 140, 230)                  # sky
        img[30:35, 10:20] = (60, 130, 220)          # a blue car below the buildings: not sky
        m = sr.sky_mask(img)
        self.assertTrue(m[:15].all())
        self.assertFalse(m[15:].any())


class Delta(unittest.TestCase):
    def test_no_delta_changes_nothing_and_a_shift_moves_every_eye(self):
        same = sr.apply_delta(CAMS, np.zeros(7))
        for k in CAMS:
            self.assertTrue(np.allclose(same[k]["eye"], CAMS[k]["eye"]))
            self.assertTrue(np.allclose(same[k]["Rw"], CAMS[k]["Rw"]))
        moved = sr.apply_delta(CAMS, np.array([0, 0, 0, 3.0, -2.0, 0.0, 0.0]))
        self.assertTrue(np.allclose(np.array(moved["a"]["eye"]) - CAMS["a"]["eye"], [3.0, -2.0, 0.0]))


class Refine(unittest.TestCase):
    def test_a_model_turned_and_shifted_off_its_place_is_brought_back(self):
        masks = {k: mask(c) for k, c in CAMS.items()}
        off = sr.apply_delta(CAMS, np.array([4.0, 0.0, 0.0, 3.0, -2.0, 0.0, 0.0]))
        before = sr.cost(off, masks, TRIS)
        fixed, report = sr.refine(off, masks, TRIS)
        self.assertLess(report["after"], before / 3)
        for k in CAMS:
            self.assertLess(np.linalg.norm(np.array(fixed[k]["eye"]) - CAMS[k]["eye"]), 1.5)


if __name__ == "__main__":
    unittest.main()
