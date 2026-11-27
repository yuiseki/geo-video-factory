"""sfm_to_world.gps_eyes: photos placed by where GPS says they were taken, at eye height above the city model's ground
there, in the scene's east/north metres around its origin."""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from world_model import sfm_to_world as sw  # noqa: E402

ORIGIN = (139.7671, 35.6812)


def ground_square(x, y, z, d=20.0):
    a, b, c, e = [x - d, y - d, z], [x + d, y - d, z], [x + d, y + d, z], [x - d, y + d, z]
    return [[a, b, c], [a, c, e]]


class GpsEyes(unittest.TestCase):
    def test_a_photo_stands_at_its_gps_place_eye_high_above_the_ground_there(self):
        east, north = 100.0, -50.0
        lon = ORIGIN[0] + east / (111_320 * math.cos(math.radians(ORIGIN[1])))
        lat = ORIGIN[1] + north / 110_950
        tris = np.array(ground_square(east, north, 4.0) + ground_square(east, north + 3, 30.0, d=2))   # a roof nearby
        eyes = sw.gps_eyes({"a.jpg": [lon, lat]}, ORIGIN, tris, eye=1.5)
        self.assertLess(abs(eyes["a.jpg"][0] - east), 0.5)
        self.assertLess(abs(eyes["a.jpg"][1] - north), 0.5)
        self.assertAlmostEqual(eyes["a.jpg"][2], 5.5, places=6)          # the ground, not the roof


if __name__ == "__main__":
    unittest.main()
