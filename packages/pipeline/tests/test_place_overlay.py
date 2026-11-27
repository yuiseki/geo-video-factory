"""place_overlay: the model drawn on the photo, the far buildings fainter so the near ones can be read."""
import unittest

import numpy as np
from PIL import Image

from support import import_pipeline

po = import_pipeline("geo.place_overlay")

LOOKING_NORTH = np.array([[1.0, 0, 0], [0, 0, -1], [0, 1, 0]])        # x right, y down, z forward


class Fade(unittest.TestCase):
    def test_near_edges_are_solid_and_far_ones_fade_but_never_vanish(self):
        a = po.fade(np.array([5.0, po.NEAR, 2 * po.NEAR, 4 * po.NEAR, 5000.0]))
        self.assertEqual(list(a[:2]), [1.0, 1.0])
        self.assertAlmostEqual(a[2], 0.5)
        self.assertTrue(np.all(np.diff(a) <= 0))
        self.assertEqual(a[-1], po.FAINTEST)


class Overlay(unittest.TestCase):
    def test_a_far_edge_is_drawn_fainter_than_a_near_one_and_the_near_one_on_top(self):
        full = Image.new("RGB", (400, 300), (0, 0, 0))
        best = {"east": 0.0, "north": 0.0, "up": 0.0, "hfov": 90.0}
        # a near vertical edge left of centre, a far one right of centre, and a far horizontal one crossing the near
        a = np.array([[-10.0, 40, -10], [200.0, 800, -200], [-400.0, 800, 0]])
        b = np.array([[-10.0, 40, 10], [200.0, 800, 200], [400.0, 800, 0]])
        got = np.asarray(po.overlay(full, (a, b), best, LOOKING_NORTH, bins=72, dots=False, width=400)).astype(int)
        near, far, crossing = got[150, 150], got[120, 250], got[150, 150]
        self.assertGreater(near[0], 240)
        self.assertLess(far[0], 0.5 * near[0])
        self.assertGreater(far[0], 20)
        self.assertGreater(crossing[0], 240)                  # the far line did not dim the near one where they cross


class Hidden(unittest.TestCase):
    def test_an_edge_behind_a_wall_is_faint_where_the_wall_hides_it_and_plain_beside_it(self):
        sa = import_pipeline("world_model.surface_atlas")
        full = Image.new("RGB", (400, 300), (0, 0, 0))
        best = {"east": 0.0, "north": 0.0, "up": 0.0, "hfov": 90.0}
        c = [[-20.0, 40, -20], [20.0, 40, -20], [20.0, 40, 20], [-20.0, 40, 20]]
        wall = np.array([[c[0], c[1], c[2]], [c[0], c[2], c[3]]])
        cam = {"eye": [0, 0, 0], "Rw": LOOKING_NORTH.tolist(), "params": [200, 200, 200, 150], "width": 400, "height": 300}
        depth = sa.depth_buffer(wall, cam, scale=1.0)
        a = np.array([[-90.0, 100, 0], [-20.0, 40, -15]])      # a far edge running behind the wall, the wall's own
        b = np.array([[90.0, 100, 0], [-20.0, 40, 15]])
        got = np.asarray(po.overlay(full, (a, b), best, LOOKING_NORTH, dots=False, width=400, depth=depth)).astype(int)
        behind, beside, own = got[150, 200, 0], got[150, 50, 0], got[140, 98:102, 0].max()
        self.assertGreater(beside, 4 * behind)                # far, but in the open: plainly there
        self.assertGreater(own, 240)                          # an edge of the wall itself is not hidden by the wall
        self.assertLess(behind, 60)
        self.assertGreater(behind, 10)                        # still there, faintly


if __name__ == "__main__":
    unittest.main()
