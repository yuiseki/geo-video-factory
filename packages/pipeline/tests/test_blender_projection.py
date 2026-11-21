import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import blender_geo as bg  # noqa: E402

W, H = 1280, 720


class ProjectionTests(unittest.TestCase):
    def test_point_straight_ahead_lands_on_the_image_center(self):
        camera = {"location": (0, 0, 1.6), "tilt": 90, "bearing": 30, "fov": 60, "shift_px": 0}
        b = math.radians(30)
        u, v = bg.project_point(camera, (math.sin(b) * 50, math.cos(b) * 50, 1.6), W, H)
        self.assertAlmostEqual(u, W / 2, places=6)
        self.assertAlmostEqual(v, H / 2, places=6)

    def test_right_is_right_up_is_up_and_shift_moves_the_frame(self):
        camera = {"location": (0, 0, 1.6), "tilt": 90, "bearing": 0, "fov": 60, "shift_px": 0}
        u, v = bg.project_point(camera, (5, 50, 1.6 + 5), W, H)
        f = (H / 2) / math.tan(math.radians(30))
        self.assertAlmostEqual(u, W / 2 + f * 5 / 50, places=6)
        self.assertAlmostEqual(v, H / 2 - f * 5 / 50, places=6)
        shifted = dict(camera, shift_px=100)
        self.assertAlmostEqual(bg.project_point(shifted, (5, 50, 6.6), W, H)[1], v + 100, places=6)

    def test_matches_the_maplibre_camera_of_a_shot_key(self):
        cam = bg.maplibre_camera(center=[139.70, 35.66], zoom=20, pitch=70, bearing=-40,
                                 fov=50, height_px=H, origin=[139.70, 35.66])
        camera = {"location": cam["location"], "tilt": 70, "bearing": -40, "fov": 50, "shift_px": 0}
        u, v = bg.project_point(camera, (0, 0, 0), W, H)
        self.assertAlmostEqual(u, W / 2, places=6)
        self.assertAlmostEqual(v, H / 2, places=6)

    def test_eye_camera_places_a_blender_camera_at_eye_height(self):
        cam = bg.eye_camera(eye=[139.701, 35.661, 1.6], bearing=-45, tilt=92, fov=58, origin=[139.700, 35.660])
        x, y = bg.local_meters([139.701, 35.661], [139.700, 35.660])
        self.assertEqual(cam["location"], (x, y, 1.6))
        self.assertAlmostEqual(cam["rotation_euler"][0], math.radians(92))
        self.assertAlmostEqual(cam["rotation_euler"][2], math.radians(45))
        self.assertAlmostEqual(cam["fov_vertical"], math.radians(58))


if __name__ == "__main__":
    unittest.main()
