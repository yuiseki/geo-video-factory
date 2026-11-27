import unittest

import numpy as np

from world_model import tree_mask as tm

LABELS = {0: "wall", 2: "sky", 4: "tree", 9: "grass", 17: "plant, flora, plant life", 72: "palm, palm tree",
          66: "flower", 1: "building, edifice"}


class Veil(unittest.TestCase):
    def test_the_classes_that_stand_before_roofs_are_found_by_their_first_name(self):
        self.assertEqual(tm.veil_ids(LABELS), [4, 17, 72])

    def test_grass_and_flowers_lie_low_and_are_left_out(self):
        self.assertNotIn(9, tm.veil_ids(LABELS))
        self.assertNotIn(66, tm.veil_ids(LABELS))

    def test_labels_without_a_tree_are_an_error(self):
        with self.assertRaises(ValueError):
            tm.veil_ids({0: "wall", 1: "sky"})

    def test_the_mask_is_where_the_map_holds_those_classes(self):
        seg = np.array([[2, 2, 4], [1, 17, 4], [9, 9, 72]])
        np.testing.assert_array_equal(tm.veil(seg, LABELS), [[0, 0, 1], [0, 1, 1], [0, 0, 1]])


if __name__ == "__main__":
    unittest.main()
