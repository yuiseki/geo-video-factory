import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from photos import photo_push as pp  # noqa: E402


class CoverWindowTests(unittest.TestCase):
    def test_a_wide_photo_is_cropped_at_the_sides_and_centred(self):
        x, y, w, h = pp.cover_window((4000, 1500), (1280, 720), 0.5)
        self.assertAlmostEqual(h, 1500)
        self.assertAlmostEqual(w, 1500 * 1280 / 720)
        self.assertAlmostEqual(x, (4000 - w) / 2)
        self.assertEqual(y, 0)

    def test_a_tall_photo_puts_the_window_at_the_focus_and_stays_inside(self):
        x, y, w, h = pp.cover_window((1600, 2400), (1280, 720), 0.62)
        self.assertEqual((x, w), (0, 1600))
        self.assertAlmostEqual(h, 900)
        self.assertAlmostEqual(y, 2400 * 0.62 - 450)
        _, y_top, _, _ = pp.cover_window((1600, 2400), (1280, 720), 0.0)
        _, y_bot, _, _ = pp.cover_window((1600, 2400), (1280, 720), 1.0)
        self.assertEqual(y_top, 0)
        self.assertAlmostEqual(y_bot, 2400 - 900)


class AffineTests(unittest.TestCase):
    def test_the_first_frame_shows_the_whole_window(self):
        s, _, cx, _, s2, cy = pp.affine_at((100.0, 50.0, 1280.0, 720.0), (1280, 720), 0.08, 0.0)
        self.assertEqual((s, s2, cx, cy), (1.0, 1.0, 100.0, 50.0))

    def test_the_view_narrows_toward_the_window_centre(self):
        win = (0.0, 0.0, 1280.0, 720.0)
        s, _, cx, _, _, cy = pp.affine_at(win, (1280, 720), 0.08, 1.0)
        self.assertAlmostEqual(s, 1 / 1.08)
        # the centre of the output still maps to the centre of the window
        self.assertAlmostEqual(cx + s * 640, 640)
        self.assertAlmostEqual(cy + s * 360, 360)

    def test_positions_are_not_rounded_to_whole_pixels(self):
        steps = [pp.affine_at((0.0, 0.0, 1280.0, 720.0), (1280, 720), 0.08, i / 132)[2] for i in range(5)]
        self.assertTrue(any(abs(v - round(v)) > 1e-3 for v in steps[1:]))


class PanTests(unittest.TestCase):
    WIN = (0.0, 0.0, 1280.0, 720.0)

    def edges(self, t, pan):
        s, _, cx, _, _, cy = pp.affine_at(self.WIN, (1280, 720), 0.08, t, pan)
        return cx, cx + s * 1280, cy, cy + s * 720

    def test_the_view_stays_inside_the_window_while_panning(self):
        for pan in (0.15, -0.15):
            for t in (0.0, 0.5, 1.0):
                left, right, top, bottom = self.edges(t, pan)
                self.assertGreaterEqual(left, -1e-9)
                self.assertLessEqual(right, 1280 + 1e-9)
                self.assertGreaterEqual(top, -1e-9)
                self.assertLessEqual(bottom, 720 + 1e-9)

    def test_a_positive_pan_moves_right_and_a_negative_one_left(self):
        def centre(t, pan):
            left, right, _, _ = self.edges(t, pan)
            return (left + right) / 2
        self.assertLess(centre(0.0, 0.15), centre(1.0, 0.15))
        self.assertGreater(centre(0.0, -0.15), centre(1.0, -0.15))
        self.assertAlmostEqual(centre(0.5, 0.15), 640)

    def test_no_pan_is_the_plain_push_in(self):
        self.assertEqual(pp.affine_at(self.WIN, (1280, 720), 0.08, 0.3, 0.0),
                         pp.affine_at(self.WIN, (1280, 720), 0.08, 0.3))


class FramesTests(unittest.TestCase):
    def test_frames_have_the_output_size_and_count(self):
        img = Image.fromarray((np.indices((90, 160)).sum(0) % 255).astype(np.uint8)).convert("RGB")
        frames = list(pp.push_in_frames(img, (64, 36), 0.5, 0.08, 5))
        self.assertEqual(len(frames), 5)
        self.assertEqual(frames[0].size, (64, 36))


class RoughnessTests(unittest.TestCase):
    def test_still_and_steadily_moving_frames_are_smooth(self):
        still = np.full((6, 4, 4), 100.0)
        ramp = np.stack([np.full((4, 4), 10.0 * i) for i in range(6)])
        self.assertEqual(pp.temporal_roughness(still), 0.0)
        self.assertAlmostEqual(pp.temporal_roughness(ramp), 0.0)

    def test_back_and_forth_steps_are_rough(self):
        judder = np.stack([np.full((4, 4), 10.0 * (i % 2)) for i in range(6)])
        self.assertAlmostEqual(pp.temporal_roughness(judder), 20.0)


if __name__ == "__main__":
    unittest.main()
