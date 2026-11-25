import unittest

import numpy as np

from world_model import ground_from_above as ga


class Pieces(unittest.TestCase):
    def test_only_high_cameras(self):
        cams = {"street": {"eye": [0, 0, 54.5]}, "roof": {"eye": [0, 0, 120.0]}}
        self.assertEqual(list(ga.high(cams, ground=52.8, above=40)), ["roof"])

    def test_affine_fit_recovers_a_map(self):
        rng = np.random.default_rng(0)
        src = rng.uniform(-300, 300, (20, 2))
        dst = src @ np.array([[2.0, 0.1], [-0.1, -2.0]]) + [500, 400]
        fit = ga.affine(src, dst)
        np.testing.assert_allclose(ga.apply_affine(fit, src), dst, atol=1e-6)

    def test_base_takes_the_tone_of_what_was_seen(self):
        base = np.full((4, 4, 3), 100.0)
        seen = np.full((4, 4, 3), np.nan)
        seen[:2] = 50.0
        out = ga.lay_over(base, seen)
        np.testing.assert_allclose(out[:2], 50.0)       # observed texels are kept
        np.testing.assert_allclose(out[2:], 50.0)       # the rest is the base, brought to the same tone

    def test_base_alone_when_nothing_was_seen(self):
        base = np.full((2, 2, 3), 80.0)
        np.testing.assert_allclose(ga.lay_over(base, np.full((2, 2, 3), np.nan)), 80.0)

    def test_register_finds_a_shift(self):
        import cv2
        rng = np.random.default_rng(1)
        fixed = np.zeros((300, 300), np.uint8)
        for _ in range(120):                                    # scattered boxes: corners to match
            x, y, w, h = rng.integers(10, 270), rng.integers(10, 270), rng.integers(4, 20), rng.integers(4, 20)
            cv2.rectangle(fixed, (int(x), int(y)), (int(x + w), int(y + h)), int(rng.integers(60, 255)), -1)
        moving = np.roll(fixed, (3, -5), axis=(0, 1))           # content moved 3 rows down, 5 columns left
        warp, inliers = ga.register(moving, fixed)
        self.assertGreater(inliers, 20)
        # warp maps fixed pixel (x, y) to where the same thing is in moving
        np.testing.assert_allclose(warp @ [100, 100, 1], [95, 103], atol=0.5)
        far, scale = ga.slid(warp, fixed.shape)
        self.assertAlmostEqual(far, np.hypot(3, 5), delta=0.5)
        self.assertAlmostEqual(scale, 1.0, delta=0.01)

    def test_register_finds_a_tilt(self):
        # a camera placed a little wrong lays the ground down under a homography, not a slide
        import cv2
        rng = np.random.default_rng(3)
        fixed = cv2.GaussianBlur((rng.random((400, 400)) * 255).astype(np.uint8), (0, 0), 2)
        fixed = cv2.normalize(fixed, None, 0, 255, cv2.NORM_MINMAX)
        true = np.array([[1.02, 0.03, 6.0], [-0.02, 0.97, -4.0], [6e-5, -4e-5, 1.0]])
        moving = cv2.warpPerspective(fixed, true, (400, 400))
        warp, inliers = ga.register(moving, fixed, model="homography")
        self.assertEqual(warp.shape, (3, 3))
        corners = np.array([[50, 50, 1], [350, 50, 1], [350, 350, 1], [50, 350, 1.0]])
        got, want = corners @ warp.T, corners @ true.T
        err = np.abs(got[:, :2] / got[:, 2:] - want[:, :2] / want[:, 2:]).max()
        self.assertLess(err, 1.0)
        self.assertLess(abs(ga.moved(warp, corners[:, :2]) - np.hypot(*(want[:, :2] / want[:, 2:] - corners[:, :2]).T).mean()), 1.0)

    def test_register_gives_up_on_noise(self):
        rng = np.random.default_rng(2)
        a = rng.integers(0, 255, (160, 160)).astype(np.uint8)
        b = rng.integers(0, 255, (160, 160)).astype(np.uint8)
        self.assertIsNone(ga.register(a, b)[0])


if __name__ == "__main__":
    unittest.main()
