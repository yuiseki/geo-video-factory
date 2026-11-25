import unittest

from world_model import edit_frames as ef


class Schedule(unittest.TestCase):
    def test_cuts_follow_each_other(self):
        self.assertEqual(ef.schedule([10, 5], [0, 0]), ([0, 10], 15))

    def test_a_crossfade_overlaps(self):
        self.assertEqual(ef.schedule([10, 5, 4], [0, 3, 0]), ([0, 7, 12], 16))

    def test_a_cross_on_the_first_clip_is_ignored(self):
        self.assertEqual(ef.schedule([10], [5]), ([0], 10))


class Black(unittest.TestCase):
    def test_a_black_clip_is_that_many_empty_frames(self):
        self.assertEqual(ef.frames_of({"black": 3}), [None, None, None])


if __name__ == "__main__":
    unittest.main()
