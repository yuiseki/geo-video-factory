import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from video import camera_path as cp  # noqa: E402


def cam(bearing=0.0, pitch=0.0, eye=(10.0, 20.0, 1.6)):
    """A cams.json entry looking along `bearing` (degrees from north, clockwise) and up by `pitch`."""
    b, p = math.radians(bearing), math.radians(pitch)
    forward = [math.sin(b) * math.cos(p), math.cos(b) * math.cos(p), math.sin(p)]
    return {"eye": list(eye), "Rw": [[1, 0, 0], [0, 1, 0], forward]}


class PhotoPoseTests(unittest.TestCase):
    def test_bearing_and_pitch_are_read_from_the_forward_row(self):
        eye, bearing, pitch = cp.photo_pose(cam(bearing=120.0, pitch=7.0))
        self.assertEqual(list(eye), [10.0, 20.0, 1.6])
        self.assertAlmostEqual(bearing, 120.0)
        self.assertAlmostEqual(pitch, 7.0)

    def test_a_westward_photo_has_a_negative_bearing_not_a_wrapped_one(self):
        self.assertAlmostEqual(cp.photo_pose(cam(bearing=-90.0))[1], -90.0)


class KeyframeTests(unittest.TestCase):
    def test_keyframes_are_rows_of_six_numbers(self):
        k = cp.parse_keyframes("0:0:0:0:-3:-6;14:0.3:0:0:2.5:6")
        self.assertEqual(k.shape, (2, 6))
        self.assertEqual(list(k[1]), [14, 0.3, 0, 0, 2.5, 6])

    def test_a_short_keyframe_is_refused(self):
        with self.assertRaisesRegex(ValueError, "t:forward:right:up:dbearing:dpitch"):
            cp.parse_keyframes("0:0:0;14:1:0")

    def test_one_keyframe_is_not_a_path(self):
        with self.assertRaisesRegex(ValueError, "two keyframes"):
            cp.parse_keyframes("0:0:0:0:0:0")

    def test_times_must_increase(self):
        with self.assertRaisesRegex(ValueError, "increase"):
            cp.parse_keyframes("0:0:0:0:0:0;5:1:0:0:0:0;5:2:0:0:0:0")


class PathFramesTests(unittest.TestCase):
    def test_the_frame_count_is_the_length_times_the_rate(self):
        frames = cp.path_frames(cam(), cp.parse_keyframes("0:0:0:0:0:0;14:1:0:0:0:0"), fps=24)
        self.assertEqual(len(frames), 336)

    def test_the_path_starts_and_ends_on_the_keyframes(self):
        frames = cp.path_frames(cam(bearing=90.0, pitch=2.0), cp.parse_keyframes("0:0:0:0:-3:-6;2:4:1:0.5:2.5:6"), fps=10)
        first, last = frames[0], frames[-1]
        self.assertAlmostEqual(first["x"], 10.0)
        self.assertAlmostEqual(first["bearing"], 87.0)
        self.assertAlmostEqual(first["pitch"], -4.0)
        # looking east: forward is +x, right is south (-y)
        self.assertAlmostEqual(last["x"], 14.0)
        self.assertAlmostEqual(last["y"], 19.0)
        self.assertAlmostEqual(last["z"], 2.1)
        self.assertAlmostEqual(last["bearing"], 92.5)
        self.assertAlmostEqual(last["pitch"], 8.0)

    def test_forward_is_level_even_when_the_photo_looks_up(self):
        frames = cp.path_frames(cam(bearing=0.0, pitch=30.0), cp.parse_keyframes("0:0:0:0:0:0;1:5:0:0:0:0"), fps=10)
        self.assertAlmostEqual(frames[-1]["y"], 25.0)
        self.assertAlmostEqual(frames[-1]["z"], 1.6)

    def test_the_camera_is_at_rest_at_both_ends(self):
        frames = cp.path_frames(cam(), cp.parse_keyframes("0:0:0:0:0:0;10:10:0:0:0:0"), fps=24)
        y = np.array([f["y"] for f in frames])
        steps = np.diff(y)
        self.assertLess(steps[0], steps.max() / 20)
        self.assertLess(steps[-1], steps.max() / 20)
        self.assertTrue((steps >= 0).all())

    def test_frames_name_their_png_when_a_directory_is_given(self):
        frames = cp.path_frames(cam(), cp.parse_keyframes("0:0:0:0:0:0;1:1:0:0:0:0"), fps=4, frames_dir=Path("w") / "f")
        self.assertEqual([Path(f["out"]).name for f in frames], ["0000.png", "0001.png", "0002.png", "0003.png"])
        self.assertEqual(Path(frames[0]["out"]).parent, Path("w") / "f")


class CliTests(unittest.TestCase):
    def test_main_writes_frames_json_and_the_frames_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "cams.json").write_text(json.dumps({"157": cam(bearing=4.0)}))
            work = tmp / "scene"
            cp.main([str(tmp / "cams.json"), "157", str(work), "0:0:0:0:0:0;2:1:0:0:0:0", "--fps=12"])
            frames = json.loads((work / "frames.json").read_text())
            self.assertEqual(len(frames), 24)
            self.assertTrue((work / "f").is_dir())
            self.assertEqual(frames[5]["out"], str(work / "f" / "0005.png"))

    def test_an_unknown_photo_key_names_the_keys_that_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "cams.json").write_text(json.dumps({"157": cam()}))
            with self.assertRaisesRegex(SystemExit, "157"):
                cp.main([str(tmp / "cams.json"), "999", str(tmp / "scene"), "0:0:0:0:0:0;2:1:0:0:0:0"])


if __name__ == "__main__":
    unittest.main()
