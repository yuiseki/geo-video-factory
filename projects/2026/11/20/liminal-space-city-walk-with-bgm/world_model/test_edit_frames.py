import unittest

import edit_frames as ef


class Schedule(unittest.TestCase):
    def test_cuts_follow_each_other(self):
        self.assertEqual(ef.schedule([10, 5], [0, 0]), ([0, 10], 15))

    def test_a_crossfade_overlaps(self):
        self.assertEqual(ef.schedule([10, 5, 4], [0, 3, 0]), ([0, 7, 12], 16))

    def test_a_cross_on_the_first_clip_is_ignored(self):
        self.assertEqual(ef.schedule([10], [5]), ([0], 10))


if __name__ == "__main__":
    unittest.main()
