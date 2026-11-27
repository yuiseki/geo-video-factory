"""build_atlas.silhouette_blocked: a photo's pixels near the outline of the city model (where the depth jumps) are not
trusted: a pose or a shape off by a little puts the sky or the building behind on the edge of a wall there."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from world_model import build_atlas as ba  # noqa: E402


class Silhouette(unittest.TestCase):
    def test_pixels_within_the_margin_of_a_depth_jump_are_blocked(self):
        depth = np.full((40, 60), np.inf, np.float32)
        depth[10:30, 20:40] = 50.0                      # a wall against the sky
        depth[10:30, 40:50] = 80.0                      # and a farther one beside it
        m = ba.silhouette_blocked(depth, (40, 60), margin=2)
        self.assertEqual(m.shape, (40, 60))
        self.assertTrue(m[20, 19] and m[20, 20] and m[20, 21])            # the outline against the sky
        self.assertTrue(m[20, 39] and m[20, 40])                          # where the near wall meets the far one
        self.assertFalse(m[20, 30])                                       # the middle of the wall
        self.assertFalse(m[2, 2])                                         # open sky is not an outline

    def test_a_depth_buffer_smaller_than_the_photo_is_scaled_up(self):
        depth = np.full((10, 15), np.inf, np.float32)
        depth[3:7, 5:10] = 50.0
        m = ba.silhouette_blocked(depth, (40, 60), margin=2)
        self.assertEqual(m.shape, (40, 60))
        self.assertTrue(m[12, 20 + 10])                                   # the top outline, at photo resolution
        self.assertFalse(m[20, 30])

    def test_no_margin_blocks_nothing(self):
        depth = np.full((10, 15), np.inf, np.float32)
        depth[3:7, 5:10] = 50.0
        self.assertFalse(ba.silhouette_blocked(depth, (40, 60), margin=0).any())


if __name__ == "__main__":
    unittest.main()
