"""photo_solve: the gates a camera found from the photo alone must pass before it is given as the answer."""
import unittest
from pathlib import Path

import numpy as np

from support import import_pipeline

ps = import_pipeline("geo.photo_solve")

R = np.eye(3).tolist()


def run(eye, miss, Rw=R):
    return {"camera": {"eye": eye, "Rw": Rw, "params": [1, 1, 0, 0]}, "miss_px": miss}


class Judge(unittest.TestCase):
    def test_three_starts_reaching_one_camera_close_to_the_fix_is_solved(self):
        best = run([10, 5, 41.6], 2.0)
        runs = [best, run([10.3, 5, 41.6], 2.2), run([10, 5.4, 41.6], 2.1), run([40, 9, 50], 90.0), run([3, 3, 41], 2.5)]
        verdict, gates = ps.judge(True, best, runs, 80.0)
        self.assertEqual(verdict, "solved")
        self.assertEqual(gates["starts_agreeing"][0], 3)

    def test_each_gate_refuses_on_its_own(self):
        best = run([10, 5, 41.6], 2.0)
        agreeing = [best, run([10.3, 5, 41.6], 2.2), run([10, 5.4, 41.6], 2.1)]
        self.assertEqual(ps.judge(False, best, agreeing, 80.0)[0], "refused: alone")
        self.assertEqual(ps.judge(True, run([10, 5, 41.6], 6.0), [run([10, 5, 41.6], 6.0)] * 3, 80.0)[0],
                         "refused: miss_px")
        self.assertEqual(ps.judge(True, best, [best, run([20, 5, 41.6], 2.1), run([3, 9, 41.6], 2.5)], 80.0)[0],
                         "refused: starts_agreeing")
        self.assertEqual(ps.judge(True, best, agreeing, 8.0)[0], "refused: from_gps_m")

    def test_a_start_that_lost_the_building_does_not_count_as_agreeing(self):
        best = run([10, 5, 41.6], 2.0)
        lost = run([10, 5, 41.6], float("inf"))
        self.assertEqual(ps.judge(True, best, [best, lost, lost], 80.0)[1]["starts_agreeing"][0], 1)


if __name__ == "__main__":
    unittest.main()


SOLVED = Path(__file__).resolve().parents[1] / "camera_truth" / "photo_solve" / "solved.json"


def _store_ready():
    try:
        from buildings.pp_tiles import store
        return any(store().glob("plateau/*/*.json"))
    except Exception:
        return False


class Tris(unittest.TestCase):
    def test_the_whole_box_is_asked_for_before_the_triangles_are_read(self):
        """What the store happened to hold must not decide the scene: the box around the fix is built every time
        (a box built before costs nothing), and only then read."""
        import tempfile
        from unittest import mock
        asked = []
        ex = {"lon": 139.7, "lat": 35.6}

        def area(origin, centre, radius):
            self.assertEqual(len(asked), 1)                    # the box came first
            return np.zeros((5, 3, 3))
        with tempfile.TemporaryDirectory() as d, \
                mock.patch("buildings.plateau_pp.cached", lambda box: asked.append(box)), \
                mock.patch("buildings.plateau_building.area_triangles", area):
            f = ps.step_tris(ex, Path(d))
            self.assertEqual(np.load(f)["tris"].shape, (5, 3, 3))
            ps.step_tris(ex, Path(d))                          # kept: neither asked for nor read again
        self.assertEqual(len(asked), 1)
        w, s, e, n = asked[0]
        self.assertAlmostEqual((n - s) * 110950, 2 * ps.TRIS_RADIUS, places=3)
        self.assertAlmostEqual((w + e) / 2, 139.7); self.assertAlmostEqual((s + n) / 2, 35.6)


class Fetch(unittest.TestCase):
    def test_a_photo_given_by_its_address_is_fetched_once_into_the_work_directory(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "there.jpg"; src.write_bytes(b"pixels")
            work = Path(d) / "work"; work.mkdir()
            got = ps.photo_file(src.as_uri(), work)
            self.assertEqual((got.parent, got.read_bytes()), (work, b"pixels"))
            src.write_bytes(b"changed")
            self.assertEqual(ps.photo_file(src.as_uri(), work).read_bytes(), b"pixels")
            self.assertEqual(ps.photo_file(str(src), work), src.resolve())     # a file is used where it is


class Kept(unittest.TestCase):
    def test_every_kept_photo_is_the_file_it_was_solved_from(self):
        import hashlib, json
        doc = json.loads(SOLVED.read_text())
        for p in doc["photos"]:
            with self.subTest(photo=p["file"]):
                f = SOLVED.parent / p["file"]
                self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(), p["sha256"])
                self.assertEqual(p["verdict"], "solved")

    @unittest.skipUnless(_store_ready(), "no PLATEAU++ tile store here")
    def test_every_kept_camera_is_what_its_coarse_camera_and_masks_give(self):
        import json
        from PIL import Image
        from buildings.plateau_building import area_triangles, building_triangles
        from world_model.silhouette_pose import solve
        doc = json.loads(SOLVED.read_text())
        for p in doc["photos"]:
            with self.subTest(photo=p["file"]):
                origin = tuple(p["origin"]); cam = p["coarse_camera"]
                tgt = building_triangles([p["target"]], origin)[p["target"]]
                scene = area_triangles(origin, cam["eye"][:2], 400.0)
                masks = [np.asarray(Image.open(SOLVED.parent / m).convert("L")) > 127 for m in p["masks"]]
                best, runs = solve(cam, scene, tgt, masks, eye_z=p["place"]["ground"] + 1.6)
                place, turn = ps._apart(best["camera"], p["camera"])
                self.assertLess(place, 0.05)
                self.assertLess(turn, 0.05)
                self.assertEqual(ps.judge(p["place"]["alone"], best, runs, p["exif"]["search_radius_m"])[0], "solved")
