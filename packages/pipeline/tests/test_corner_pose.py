"""corner_pose: a camera from building corners and edges picked in a photo, and the camera truths kept in the repo."""
import json
import math
import unittest
from pathlib import Path

import numpy as np

from support import import_pipeline

cp = import_pipeline("world_model.corner_pose")

TRUTH = Path(__file__).resolve().parents[1] / "camera_truth"


def camera(eye, heading, pitch, fx, size=(2000, 1500)):
    h, t = math.radians(heading), math.radians(pitch)
    f = np.array([math.sin(h) * math.cos(t), math.cos(h) * math.cos(t), math.sin(t)])
    r = np.cross(f, [0, 0, 1.0]); r /= np.linalg.norm(r)
    return {"eye": list(eye), "Rw": np.array([r, np.cross(f, r), f]).tolist(),
            "params": [fx, fx, size[0] / 2, size[1] / 2], "width": size[0], "height": size[1]}


BOX = [[0, 0], [20, 0], [20, 15], [0, 15]]


def picks(cam, top=40.0, ground=0.0):
    """Roof corners as points and the vertical edges as lines, seen by `cam`."""
    pts = [[[x, y, top], cp.project(cam, [[x, y, top]])[0].tolist()] for x, y in BOX]
    lines = [[[[x, y, top], [x, y, ground]], cp.project(cam, [[x, y, (top + ground) / 2]])[0].tolist()] for x, y in BOX]
    return pts, lines


class Solve(unittest.TestCase):
    def test_a_camera_is_recovered_from_its_corners_with_the_focal_length_known(self):
        truth = camera([-30, -25, 1.6], 40, 15, 1800)
        pts, lines = picks(truth)
        got, res = cp.solve({"width": 2000, "height": 1500, "fx": 1800, "points": pts, "lines": lines,
                             "guess_eye": [-20, -40, 1.6]})
        self.assertLess(np.linalg.norm(np.array(got["eye"]) - truth["eye"]), 0.05)
        self.assertLess(np.abs(np.array(got["Rw"]) - truth["Rw"]).max(), 1e-3)
        self.assertLess(np.abs(res).max(), 0.1)

    def test_with_the_focal_length_free_the_eye_height_pins_the_distance(self):
        truth = camera([-30, -25, 1.6], 40, 15, 1800)
        pts, lines = picks(truth)
        got, _ = cp.solve({"width": 2000, "height": 1500, "fx": None, "eye_z": 1.6, "points": pts[:2], "lines": lines,
                           "guess_eye": [-20, -40, 1.6]})
        self.assertAlmostEqual(got["params"][0], 1800, delta=5)
        self.assertLess(np.linalg.norm(np.array(got["eye"]) - truth["eye"]), 0.2)


class Truth(unittest.TestCase):
    def test_every_kept_camera_is_what_its_picks_give(self):
        files = sorted(TRUTH.glob("*.json"))
        self.assertTrue(files)
        for path in files:
            doc = json.loads(path.read_text())
            for photo in doc["photos"]:
                with self.subTest(photo=photo["ref"]):
                    self.assertIn(photo["license"], ("CC0", "Public domain"))
                    got, res = cp.solve(dict(photo, guess_eye=photo["camera"]["eye"]))
                    self.assertLess(np.linalg.norm(np.array(got["eye"]) - photo["camera"]["eye"]), 0.05)
                    self.assertLessEqual(np.abs(res).max(), photo["residual_px_max"] + 0.5)

    def test_every_kept_photo_is_the_one_its_pixels_were_picked_in(self):
        import hashlib
        from PIL import Image
        for path in sorted(TRUTH.glob("*.json")):
            for photo in json.loads(path.read_text())["photos"]:
                with self.subTest(photo=photo["ref"]):
                    f = path.parent / photo["file"]
                    self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(), photo["sha256"])
                    self.assertEqual(Image.open(f).size, (photo["width"], photo["height"]))


if __name__ == "__main__":
    unittest.main()
