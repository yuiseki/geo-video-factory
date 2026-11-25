import unittest

import numpy as np

from world_model import time_blend as tb


class Weight(unittest.TestCase):
    def test_both_ends_are_one_pure_layer(self):
        for mode in ("fade", "wipe", "rise"):
            self.assertEqual(tb.weight(0.0, (4, 6), mode).max(), 0)
            self.assertEqual(tb.weight(1.0, (4, 6), mode).min(), 1)
            self.assertEqual(tb.weight(0.3, (4, 6), mode).max(), 0)
            self.assertEqual(tb.weight(0.7, (4, 6), mode).min(), 1)

    def test_wipe_comes_from_the_left(self):
        w = tb.weight(0.5, (2, 9), "wipe")
        self.assertGreater(w[0, 0], w[0, -1])
        self.assertTrue((np.diff(w[0]) <= 0).all())

    def test_rise_comes_from_the_bottom(self):
        w = tb.weight(0.5, (9, 2), "rise")
        self.assertGreater(w[-1, 0], w[0, 0])

    def test_fade_is_half_way_in_the_middle(self):
        self.assertAlmostEqual(float(tb.weight(0.5, (1, 1))[0, 0]), 0.5)

    def test_mix(self):
        a, b = np.zeros((1, 2, 3), np.uint8), np.full((1, 2, 3), 200, np.uint8)
        out = tb.mix(a, b, np.array([[0.0, 0.5]], np.float32))
        self.assertEqual(out[0, 0, 0], 0)
        self.assertEqual(out[0, 1, 0], 100)


if __name__ == "__main__":
    unittest.main()
