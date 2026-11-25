import unittest

import fill_frames as ff


class Plan(unittest.TestCase):
    def test_a_gap_holds_the_previous_frame(self):
        self.assertEqual(ff.plan({0, 1, 3}, 4), [0, 1, 1, 3])

    def test_a_missing_start_takes_the_first_frame(self):
        self.assertEqual(ff.plan({2, 3}, 4), [2, 2, 2, 3])

    def test_step(self):
        self.assertEqual(ff.plan({0, 10, 30}, 40, step=10), [0, 10, 10, 30])


if __name__ == "__main__":
    unittest.main()
