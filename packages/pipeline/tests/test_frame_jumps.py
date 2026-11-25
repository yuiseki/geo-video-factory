import unittest

from world_model import frame_jumps as fc


class FrameCheck(unittest.TestCase):
    def test_a_black_frame_and_a_dim_run_stand_out(self):
        means = [100, 101, 103, 0, 104, 106, 107, 60, 61, 109, 110, 111, 112]
        self.assertEqual(fc.odd_frames(means), [3, 7, 8])

    def test_a_slow_change_is_not_odd(self):
        self.assertEqual(fc.odd_frames([50 + 3 * i for i in range(30)]), [])

    def test_first_and_last_are_checked(self):
        self.assertEqual(fc.odd_frames([0, 100, 100, 100, 100, 5]), [0, 5])


if __name__ == "__main__":
    unittest.main()
