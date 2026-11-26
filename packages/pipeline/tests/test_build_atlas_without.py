"""build_atlas.drop_shared: a group atlas leaves out the triangles that a building's own atlas paints."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from world_model import build_atlas as ba  # noqa: E402


def tri(x):
    return np.array([[x, 0, 0], [x + 1, 0, 0], [x, 0, 1]], float)


class DropShared(unittest.TestCase):
    def test_the_triangles_another_atlas_holds_are_dropped(self):
        group = np.stack([tri(0), tri(5), tri(10)])
        own = np.stack([tri(5)])
        self.assertEqual(ba.drop_shared(group, [own]).tolist(), np.stack([tri(0), tri(10)]).tolist())

    def test_a_triangle_a_little_off_is_still_the_same_one(self):
        group = np.stack([tri(0), tri(5) + 0.01])
        self.assertEqual(len(ba.drop_shared(group, [np.stack([tri(5)])])), 1)

    def test_a_neighbour_is_kept(self):
        group = np.stack([tri(0), tri(5.5)])
        self.assertEqual(len(ba.drop_shared(group, [np.stack([tri(5)])])), 2)

    def test_nothing_to_drop(self):
        group = np.stack([tri(0)])
        self.assertEqual(len(ba.drop_shared(group, [])), 1)


if __name__ == "__main__":
    unittest.main()
