import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from photos import whip_pan as wp  # noqa: E402


class TimingTests(unittest.TestCase):
    def test_without_overlap_the_three_parts_follow_each_other(self):
        t = wp.Timing(fps=24, walk=8.0, pan=1.0, push=3.0)
        self.assertEqual((t.pan_start, t.pan_end, t.push_start, t.total), (8.0, 9.0, 9.0, 12.0))
        self.assertEqual(t.frames, 288)

    def test_overlap_starts_the_turn_before_the_walk_ends_and_the_push_before_the_turn_ends(self):
        t = wp.Timing(fps=24, walk=8.0, pan=1.0, push=3.0, overlap_in=0.5, overlap_out=0.25)
        self.assertEqual((t.pan_start, t.pan_end, t.push_start, t.total), (7.5, 8.5, 8.25, 11.25))
        self.assertEqual(t.frames, 270)

    def test_progress_is_clamped_outside_each_part(self):
        t = wp.Timing(fps=24, walk=8.0, pan=1.0, push=3.0, overlap_in=0.5, overlap_out=0.25)
        self.assertEqual(t.progress(0.0), (0.0, 0.0, 0.0))
        self.assertEqual(t.progress(7.5), (7.5 / 8.0, 0.0, 0.0))
        self.assertEqual(t.progress(8.25), (1.0, 0.75, 0.0))
        self.assertEqual(t.progress(11.25), (1.0, 1.0, 1.0))
        self.assertEqual(t.progress(99.0), (1.0, 1.0, 1.0))


class ScheduleTests(unittest.TestCase):
    def test_walk_renders_scene_a_once_and_push_renders_scene_b_once(self):
        t = wp.Timing(fps=24, walk=8.0, pan=1.0, push=3.0)
        frames = wp.schedule(t, sub=8)
        self.assertEqual(len(frames), 288)
        self.assertEqual([f["scene"] for f in frames[:192]], ["a"] * 192)
        self.assertEqual([f["scene"] for f in frames[192:216]], ["ab"] * 24)
        self.assertEqual([f["scene"] for f in frames[216:]], ["b"] * 72)
        self.assertEqual(frames[0]["times"], [0.0])
        self.assertEqual(frames[287]["times"], [287 / 24])

    def test_pan_frames_open_the_shutter_at_the_frame_time_and_fill_the_frame_interval(self):
        t = wp.Timing(fps=24, walk=8.0, pan=1.0, push=3.0)
        f = wp.schedule(t, sub=8)[192]
        self.assertEqual(len(f["times"]), 8)
        self.assertAlmostEqual(f["times"][0], 8.0)
        self.assertAlmostEqual(f["times"][1] - f["times"][0], 1 / 24 / 8)
        self.assertLess(f["times"][-1], 8.0 + 1 / 24)

    def test_overlapped_pan_still_covers_whole_frames(self):
        t = wp.Timing(fps=24, walk=8.0, pan=1.0, push=3.0, overlap_in=0.5, overlap_out=0.25)
        frames = wp.schedule(t, sub=4)
        self.assertEqual(sum(f["scene"] == "ab" for f in frames), 24)
        self.assertEqual(frames[180]["scene"], "ab")       # 7.5 s
        self.assertEqual(frames[179]["scene"], "a")
        self.assertEqual(frames[204]["scene"], "b")        # 8.5 s

    def test_shutter_keeps_the_first_part_of_the_samples(self):
        self.assertEqual(wp.shutter_count(8, 1.0), 8)
        self.assertEqual(wp.shutter_count(8, 0.5), 4)
        self.assertEqual(wp.shutter_count(8, 0.01), 1)
        self.assertEqual(wp.shutter_count(8, 3.0), 8)


class EaseTests(unittest.TestCase):
    def test_ease_and_push_eases_run_from_zero_to_one(self):
        for fn in (wp.ease, wp.push_out, wp.push_inout):
            self.assertAlmostEqual(fn(0.0), 0.0)
            self.assertAlmostEqual(fn(1.0), 1.0)
            self.assertAlmostEqual(fn(-1.0), 0.0)
            self.assertAlmostEqual(fn(2.0), 1.0)

    def test_push_out_starts_at_speed_and_push_inout_starts_from_rest(self):
        d = 1e-3
        self.assertGreater(wp.push_out(d) / d, 1.9)
        self.assertLess(wp.push_inout(d) / d, 0.01)
        # both settle gently
        self.assertLess((1 - wp.push_out(1 - d)) / d, 0.01)
        self.assertLess((1 - wp.push_inout(1 - d)) / d, 0.01)

    def test_lerp_angle_takes_the_short_way_round(self):
        self.assertAlmostEqual(wp.lerp_angle(350, 10, 0.5) % 360, 0.0)
        self.assertAlmostEqual(wp.lerp_angle(305, 261, 1.0), 261.0)
        self.assertEqual(wp.turn_direction(305, 261), -1)
        self.assertEqual(wp.turn_direction(350, 10), 1)


class PixelBearingTests(unittest.TestCase):
    def test_level_camera_offsets_follow_the_horizontal_field_of_view(self):
        off = wp.pixel_bearing_offsets(960, 640, 53.27, 0.0)
        self.assertEqual(off.shape, (640, 960))
        fy = 320 / math.tan(math.radians(53.27 / 2))
        self.assertAlmostEqual(off[100, 959], math.degrees(math.atan(479.5 / fy)), places=4)
        self.assertAlmostEqual(off[100, 0], -off[100, 959], places=4)
        np.testing.assert_allclose(off[0], off[639], atol=1e-4)      # level: the same on every row
        self.assertAlmostEqual(off[320, 480], -off[320, 479], places=6)

    def test_looking_up_spreads_the_top_rows_over_more_bearing(self):
        off = wp.pixel_bearing_offsets(960, 640, 53.27, 15.5)
        self.assertGreater(off[0, 959], off[320, 959])
        self.assertGreater(off[320, 959], off[639, 959])
        self.assertLess(abs(off[0, 480]), 0.1)


class WipeTests(unittest.TestCase):
    def setUp(self):
        self.off = wp.pixel_bearing_offsets(960, 640, 53.27, 15.5)

    def test_wipe_is_all_scene_a_at_the_start_and_all_scene_b_at_the_end(self):
        for direction in (-1, 1):
            self.assertEqual(float(wp.wipe_weight(self.off, 0.0, direction, 10.0).max()), 0.0)
            self.assertEqual(float(wp.wipe_weight(self.off, 1.0, direction, 10.0).min()), 1.0)

    def test_scene_b_enters_from_the_side_the_camera_turns_toward(self):
        left = wp.wipe_weight(self.off, 0.3, -1, 10.0)
        self.assertGreater(left[320, 0], 0.99)
        self.assertLess(left[320, 959], 0.01)
        right = wp.wipe_weight(self.off, 0.3, 1, 10.0)
        self.assertLess(right[320, 0], 0.01)
        self.assertGreater(right[320, 959], 0.99)

    def test_half_way_the_edge_is_at_the_centre_and_as_wide_as_the_soft_band(self):
        w = wp.wipe_weight(self.off, 0.5, -1, 10.0)
        row = w[400]
        self.assertAlmostEqual(float(row[479] + row[480]) / 2, 0.5, places=2)
        self.assertTrue(np.all(np.diff(row) <= 1e-9))             # monotone: B on the left, A on the right
        band = self.off[400][(row > 0.001) & (row < 0.999)]
        self.assertAlmostEqual(float(band.max() - band.min()), 10.0, delta=0.6)

    def test_wipe_progress_waits_for_its_window_and_eases_inside(self):
        self.assertEqual(wp.wipe_progress(0.1, 0.2, 0.8), 0.0)
        self.assertAlmostEqual(wp.wipe_progress(0.5, 0.2, 0.8), 0.5)
        self.assertEqual(wp.wipe_progress(0.9, 0.2, 0.8), 1.0)
        self.assertLess(wp.wipe_progress(0.3, 0.2, 0.8), (0.3 - 0.2) / 0.6)


class LinearLightTests(unittest.TestCase):
    def test_mean_of_black_and_white_is_brighter_than_the_mean_of_the_codes(self):
        a = np.zeros((2, 2, 3), np.float32)
        b = np.full((2, 2, 3), 255, np.float32)
        out = wp.mean_linear([a, b])
        self.assertAlmostEqual(float(out[0, 0, 0]), 255 * 0.5 ** (1 / 2.2), places=3)

    def test_mean_of_equal_images_is_the_image(self):
        a = np.full((2, 2, 3), 77, np.float32)
        np.testing.assert_allclose(wp.mean_linear([a, a, a]), a, atol=1e-3)

    def test_blend_returns_each_scene_at_the_ends_and_mixes_per_pixel(self):
        a = np.full((1, 2, 3), 40, np.float32)
        b = np.full((1, 2, 3), 200, np.float32)
        w = np.array([[0.0, 1.0]], np.float32)
        out = wp.blend_linear(a, b, w)
        np.testing.assert_allclose(out[0, 0], 40, atol=1e-3)
        np.testing.assert_allclose(out[0, 1], 200, atol=1e-3)
        mid = wp.blend_linear(a, b, np.full((1, 2), 0.5, np.float32))
        self.assertGreater(float(mid[0, 0, 0]), 120)             # above the 120 a code-space mix gives


if __name__ == "__main__":
    unittest.main()
