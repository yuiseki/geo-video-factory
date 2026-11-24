import unittest

import numpy as np

import camera_path as cp


class Sample(unittest.TestCase):
    keys = [{"eye": [0, 0, 0], "target": [0, 10, 0], "lens": 10},
            {"eye": [10, 0, 0], "target": [0, 10, 0], "lens": 20, "roll": 90},
            {"eye": [10, 10, 5], "target": [0, 10, 0], "lens": 30, "roll": 180}]

    def test_passes_through_the_keys(self):
        p = cp.sample(self.keys, 101, ease=False)
        np.testing.assert_allclose(p[0], [0, 0, 0, 0, 10, 0, 10, 0], atol=1e-9)
        np.testing.assert_allclose(p[50], [10, 0, 0, 0, 10, 0, 20, 90], atol=1e-9)
        np.testing.assert_allclose(p[100], [10, 10, 5, 0, 10, 0, 30, 180], atol=1e-9)

    def test_ease_starts_and_ends_slowly(self):
        p = cp.sample(self.keys[:2], 61)
        step = np.linalg.norm(np.diff(p[:, :3], axis=0), axis=1)
        self.assertLess(step[0], 0.2 * step[30])
        self.assertLess(step[-1], 0.2 * step[30])

    def test_key_times_are_honoured(self):
        keys = [dict(self.keys[0], t=0.0), dict(self.keys[1], t=0.2), dict(self.keys[2], t=1.0)]
        p = cp.sample(keys, 101, ease=False)
        np.testing.assert_allclose(p[20, :3], [10, 0, 0], atol=1e-9)

    def test_two_keys_are_a_straight_line(self):
        p = cp.sample(self.keys[:2], 11, ease=False)
        np.testing.assert_allclose(p[5, :3], [5, 0, 0], atol=1e-9)
        np.testing.assert_allclose(p[5, 6], 15, atol=1e-9)


class Look(unittest.TestCase):
    def test_looks_at_the_target_with_up_up(self):
        m = cp.look_matrix([0, 0, 0], [0, 5, 0])
        np.testing.assert_allclose(-m[:3, 2], [0, 1, 0], atol=1e-9)
        np.testing.assert_allclose(m[:3, 1], [0, 0, 1], atol=1e-9)
        np.testing.assert_allclose(m[:3, 0], [1, 0, 0], atol=1e-9)

    def test_roll_turns_the_world_over(self):
        m = cp.look_matrix([1, 2, 3], [1, 7, 3], roll=180)
        np.testing.assert_allclose(m[:3, 1], [0, 0, -1], atol=1e-9)
        np.testing.assert_allclose(m[:3, 3], [1, 2, 3])

    def test_straight_down_is_defined(self):
        m = cp.look_matrix([0, 0, 10], [0, 0, 0])
        self.assertTrue(np.isfinite(m).all())
        np.testing.assert_allclose(-m[:3, 2], [0, 0, -1], atol=1e-9)
        np.testing.assert_allclose(np.linalg.det(m[:3, :3]), 1, atol=1e-9)


class Helpers(unittest.TestCase):
    def test_circle_starts_north(self):
        pts = cp.circle((1, 2), 10, 5, 0, 90, n=3)
        np.testing.assert_allclose(pts[0], [1, 12, 5], atol=1e-9)
        np.testing.assert_allclose(pts[2], [11, 2, 5], atol=1e-9)

    def test_clearance(self):
        d = cp.clearance(np.array([[0, 0, 0], [0, 0, 5.0]]), np.array([[0, 0, 1.0], [9, 9, 9]]))
        np.testing.assert_allclose(d, [1, 4])


if __name__ == "__main__":
    unittest.main()
