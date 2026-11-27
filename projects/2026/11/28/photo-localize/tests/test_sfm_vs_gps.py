import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sfm_vs_gps as sg  # noqa: E402


class Frames(unittest.TestCase):
    def test_100_m_north_is_about_9_thousandths_of_a_minute_of_latitude(self):
        lon, lat = sg.enu_to_lonlat(0, 100, 139.77, 35.7)
        self.assertAlmostEqual(lon, 139.77)
        self.assertAlmostEqual((lat - 35.7) * 111_000, 100, delta=1)

    def test_identity_quaternion_is_the_identity_rotation(self):
        np.testing.assert_allclose(sg.quat_to_r(1, 0, 0, 0), np.eye(3))


class Cameras(unittest.TestCase):
    def test_a_camera_looking_east_from_10_m_east_of_the_origin(self):
        # world->camera: camera z (forward) = world east, camera x = world south, camera y = world down.
        r = np.array([[0, -1, 0], [0, 0, -1], [1, 0, 0]], dtype=float)
        c = np.array([10.0, 0, 0])
        t = -r @ c
        q = _quat(r)
        with tempfile.TemporaryDirectory() as d:
            Path(d, "enu_origin.txt").write_text("# lat lon alt\n35.7 139.77 0\n")
            Path(d, "images.txt").write_text(f"# h\n1 {q[0]} {q[1]} {q[2]} {q[3]} {t[0]} {t[1]} {t[2]} 1 a.jpg\n\n")
            cam = sg.cameras(Path(d))["a.jpg"]
        self.assertAlmostEqual(cam["heading"], 90, places=6)
        east = (cam["lonlat"][0] - 139.77) * math.pi / 180 * 6378137 * math.cos(math.radians(35.7))
        self.assertAlmostEqual(east, 10, places=3)


def _quat(r):
    w = math.sqrt(1 + r[0, 0] + r[1, 1] + r[2, 2]) / 2
    return w, (r[2, 1] - r[1, 2]) / (4 * w), (r[0, 2] - r[2, 0]) / (4 * w), (r[1, 0] - r[0, 1]) / (4 * w)


if __name__ == "__main__":
    unittest.main()
