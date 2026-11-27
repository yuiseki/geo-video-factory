"""silhouette_pose: a camera pulled onto a building's outline as SAM cut it out of the photo."""
import json
import math
import unittest
from pathlib import Path

import numpy as np

from support import import_pipeline

spz = import_pipeline("world_model.silhouette_pose")
sa = import_pipeline("world_model.surface_atlas")

TRUTH = Path(__file__).resolve().parents[1] / "camera_truth"


def box(x0, y0, x1, y1, z0, z1):
    p = [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]]
    f = [(0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7), (4, 5, 6), (4, 6, 7)]
    return np.array([[p[i] for i in t] for t in f], float)


def camera(eye, heading, pitch, fx=900, size=(1200, 900)):
    h, t = math.radians(heading), math.radians(pitch)
    f = np.array([math.sin(h) * math.cos(t), math.cos(h) * math.cos(t), math.sin(t)])
    r = np.cross(f, [0, 0, 1.0]); r /= np.linalg.norm(r)
    return {"eye": list(eye), "Rw": np.array([r, np.cross(f, r), f]).tolist(), "params": [fx, fx, size[0] / 2, size[1] / 2],
            "width": size[0], "height": size[1]}


# an L-shaped tower (a tall block on a lower wing) and a low neighbour in front of its foot
TARGET = np.concatenate([box(0, 0, 20, 15, 0, 40), box(20, 0, 32, 15, 0, 22)])
SCENE = np.concatenate([TARGET, box(-5, -30, 40, -25, 0, 6)])
TRUE = camera([-25, -70, 1.6], 25, 18)


def sam_like(cam):
    """The mask SAM would give: the target where it is in view, its foot hidden behind the low neighbour."""
    d = sa.depth_buffer(SCENE, cam, scale=1.0); t = sa.depth_buffer(TARGET, cam, scale=1.0)
    return np.isfinite(t) & (t <= d + 0.5)


def off(a, b):
    from scipy.spatial.transform import Rotation as Rot
    turn = math.degrees(np.linalg.norm(Rot.from_matrix(np.array(a["Rw"]) @ np.array(b["Rw"]).T).as_rotvec()))
    return float(np.linalg.norm(np.array(a["eye"]) - b["eye"])), turn


class Refine(unittest.TestCase):
    def test_a_camera_turned_and_moved_off_comes_back_onto_the_outline(self):
        mask = sam_like(TRUE)
        start = spz.moved(TRUE, [1.0, -1.5, 0.5, 3.0, -2.0, 1.0])
        got, miss = spz.refine(start, SCENE, TARGET, mask)
        place, turn = off(got, TRUE)
        self.assertLess(place, 0.5)
        self.assertLess(turn, 0.3)
        self.assertLess(miss, 1.5)

    def test_from_every_start_the_best_is_kept_and_a_failed_start_looks_failed(self):
        mask = sam_like(TRUE)
        best, runs = spz.solve(TRUE, SCENE, TARGET, [mask])
        self.assertEqual(len(runs), len(spz.STARTS))
        self.assertEqual(best["miss_px"], min(r["miss_px"] for r in runs))
        place, turn = off(best["camera"], TRUE)
        self.assertLess(place, 0.5)
        self.assertLess(turn, 0.3)

    def test_the_mask_kept_is_the_one_that_overlaps_the_model(self):
        mask = sam_like(TRUE)
        wrong = np.zeros_like(mask); wrong[:50, :50] = True
        self.assertEqual(spz.choose_mask([wrong, mask], TRUE, SCENE, TARGET), 1)


class Kept(unittest.TestCase):
    @unittest.skipUnless(spz.store_ready(), "no PLATEAU++ tile store here")
    def test_every_kept_silhouette_camera_is_what_its_mask_gives(self):
        for path in sorted(TRUTH.glob("*.json")):
            doc = json.loads(path.read_text())
            for photo in doc["photos"]:
                if "silhouette" not in photo:
                    continue
                with self.subTest(photo=photo["ref"]):
                    best = spz.solve_kept(doc, photo, path.parent)
                    place, turn = off(best["camera"], photo["silhouette"]["camera"])
                    self.assertLess(place, 0.05)
                    self.assertLess(turn, 0.05)


if __name__ == "__main__":
    unittest.main()
