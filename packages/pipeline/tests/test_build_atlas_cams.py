"""build_atlas.pick_cams: which placed photos may paint a building."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from world_model import build_atlas as ba  # noqa: E402

CAMS = {"016_train": {}, "171_Tokyo_Japan": {}, "278_The_front_of_Shibuya_Station_Crossing_01": {}}


class PickCams(unittest.TestCase):
    def test_every_camera_by_default(self):
        self.assertEqual(sorted(ba.pick_cams(CAMS)), sorted(CAMS))

    def test_only_keeps_the_cameras_whose_key_holds_a_word(self):
        self.assertEqual(sorted(ba.pick_cams(CAMS, only="171,016")), ["016_train", "171_Tokyo_Japan"])

    def test_skip_leaves_out_the_cameras_whose_key_holds_a_word(self):
        self.assertEqual(sorted(ba.pick_cams(CAMS, skip="278_")), ["016_train", "171_Tokyo_Japan"])

    def test_skip_wins_over_only(self):
        self.assertEqual(sorted(ba.pick_cams(CAMS, only="171,278", skip="278")), ["171_Tokyo_Japan"])


if __name__ == "__main__":
    unittest.main()
