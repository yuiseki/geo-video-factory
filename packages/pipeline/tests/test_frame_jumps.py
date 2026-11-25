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


class Command(unittest.TestCase):
    def test_a_white_frame_is_found_and_moved_aside(self):
        import io
        import tempfile
        from contextlib import redirect_stdout
        from pathlib import Path

        from PIL import Image

        d = Path(tempfile.mkdtemp())
        for i in range(6):
            Image.new("RGB", (64, 36), (255, 255, 255) if i == 3 else (60, 60, 60)).save(d / f"f{i:04d}.jpg")
        out = io.StringIO()
        with redirect_stdout(out):
            fc.main([str(d), "--move"])
        self.assertIn("odd f0003.jpg", out.getvalue())
        self.assertTrue((d / "bad0_f0003.jpg").exists())
        self.assertFalse((d / "f0003.jpg").exists())


if __name__ == "__main__":
    unittest.main()
