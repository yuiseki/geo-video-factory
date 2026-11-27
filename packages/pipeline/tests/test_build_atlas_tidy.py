"""build_atlas.tidy: specks of seen texels are dropped and the seen texels grow a few texels into their own face, so
neither a speck of a grazing view nor a see-through rim draws a line along the edges of the painted buildings."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from world_model import build_atlas as ba  # noqa: E402


def setup():
    chart = np.full((20, 30), -1)
    chart[2:18, 2:14] = 0               # one face
    chart[2:18, 15:28] = 1              # its neighbour in the atlas, another face
    colour = np.zeros((20, 30, 3), np.float32)
    quality = np.zeros((20, 30), np.float32)
    colour[4:16, 4:12] = (200, 50, 50)
    quality[4:16, 4:12] = 1.0          # face 0 seen in its middle, a rim of two texels not
    colour[10, 20] = (250, 250, 250)
    quality[10, 20] = 1.0              # a speck on face 1
    return colour, quality, chart


class Tidy(unittest.TestCase):
    def test_a_speck_is_dropped(self):
        colour, quality, chart = setup()
        c, q = ba.tidy(colour, quality, chart, min_island=4, grow=0)
        self.assertEqual(q[10, 20], 0.0)
        self.assertEqual(q[8, 8], 1.0)

    def test_seen_texels_grow_into_their_own_face_only(self):
        colour, quality, chart = setup()
        c, q = ba.tidy(colour, quality, chart, min_island=4, grow=2)
        self.assertTrue((q[2:18, 4:12] > 0).all() and (q[4:16, 2:14] > 0).all())   # the rim of face 0 is filled
        self.assertTrue(np.allclose(c[2, 6], (200, 50, 50)))
        self.assertTrue((q[:, 15:] == 0).all())                    # nothing crossed into face 1
        self.assertTrue((q[chart < 0] == 0).all())                 # nor into the margin of the atlas


if __name__ == "__main__":
    unittest.main()
