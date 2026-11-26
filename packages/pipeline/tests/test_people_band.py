"""surface_atlas.people_band: the low strip of wall that a photo from the street sees past people and cars."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from world_model import surface_atlas as sa  # noqa: E402

PTS = np.array([[0, 10, 50.5], [0, 10, 52.9], [0, 10, 60.0]])   # ground 50: 0.5 m, 2.9 m and 10 m up


class PeopleBand(unittest.TestCase):
    def test_a_street_photo_does_not_paint_the_wall_below_the_band(self):
        cam = {"eye": [0, 0, 51.6]}
        self.assertEqual(sa.people_band(PTS, cam, ground=50.0, band=2.2).tolist(), [True, False, False])

    def test_a_photo_from_above_paints_the_wall_down_to_the_ground(self):
        cam = {"eye": [0, 0, 80.0]}                       # from a window or a deck: nothing stands in between
        self.assertEqual(sa.people_band(PTS, cam, ground=50.0, band=2.2).tolist(), [False, False, False])

    def test_no_band_blocks_nothing(self):
        cam = {"eye": [0, 0, 51.6]}
        self.assertFalse(sa.people_band(PTS, cam, ground=50.0, band=0).any())

    def test_the_wall_right_in_front_of_the_camera_is_still_painted(self):
        cam = {"eye": [0, 9, 51.6]}                       # 1 m away: nobody fits between
        self.assertFalse(sa.people_band(PTS, cam, ground=50.0, band=2.2, near=2.0).any())


if __name__ == "__main__":
    unittest.main()
