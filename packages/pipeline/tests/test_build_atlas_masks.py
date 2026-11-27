"""build_atlas.people_mask: the pixels of a photo that hold people or cars (photos/people_removal.py's grown mask)."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from world_model import build_atlas as ba  # noqa: E402

CAM = {"width": 8, "height": 6}


class PeopleMask(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_none_without_a_mask_for_the_photo(self):
        self.assertIsNone(ba.people_mask(self.dir, "278_crossing", CAM))

    def test_set_where_the_mask_is_bright(self):
        m = np.zeros((6, 8), np.uint8)
        m[1, 2], m[4, 5], m[0, 0] = 255, 128, 20       # 20: the soft edge of the grown mask, below the cut
        Image.fromarray(m).save(self.dir / "278_crossing.png")
        got = ba.people_mask(self.dir, "278_crossing", CAM)
        self.assertEqual(got.shape, (6, 8))
        self.assertEqual(got.dtype, bool)
        self.assertEqual(sorted(zip(*np.nonzero(got))), [(1, 2), (4, 5)])

    def test_a_mask_made_smaller_than_the_photo_is_stretched_to_it(self):
        m = np.zeros((3, 4), np.uint8)
        m[0, 0] = 255
        Image.fromarray(m).save(self.dir / "068_night.png")
        got = ba.people_mask(self.dir, "068_night", CAM)
        self.assertEqual(got.shape, (6, 8))
        self.assertTrue(got[:2, :2].all())
        self.assertEqual(int(got.sum()), 4)

    def test_a_mask_of_another_shape_is_refused(self):
        Image.fromarray(np.zeros((8, 6), np.uint8)).save(self.dir / "199_tall.png")
        with self.assertRaises(SystemExit):
            ba.people_mask(self.dir, "199_tall", CAM)


if __name__ == "__main__":
    unittest.main()
