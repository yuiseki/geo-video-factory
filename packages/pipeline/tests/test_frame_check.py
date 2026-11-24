import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import frame_check as fc  # noqa: E402


def write_frames(folder, levels):
    for i, level in enumerate(levels):
        Image.new("RGB", (64, 36), (level, level, level)).save(Path(folder) / f"{i:04d}.png")


class DarkFramesTests(unittest.TestCase):
    def test_frames_below_the_limit_are_named_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_frames(tmp, [120, 3, 90, 0, 24])
            total, dark = fc.dark_frames(tmp, limit=25.0)
            self.assertEqual(total, 5)
            self.assertEqual(dark, ["0001", "0003", "0004"])

    def test_a_night_limit_lets_dim_frames_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_frames(tmp, [10, 5])
            self.assertEqual(fc.dark_frames(tmp, limit=6.0), (2, ["0001"]))

    def test_an_empty_directory_is_an_error_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(FileNotFoundError, "no frames"):
                fc.dark_frames(tmp)


class CliTests(unittest.TestCase):
    def test_exit_code_is_one_when_a_frame_is_dark(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_frames(tmp, [120, 2])
            self.assertEqual(fc.main([tmp]), 1)
            self.assertEqual(fc.main([tmp, "1"]), 0)


if __name__ == "__main__":
    unittest.main()
