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


class Place(unittest.TestCase):
    """The search widens while its answer is not decided: not alone, on the rim, or fitting badly."""

    def place(self, by_radius, limit):
        import tempfile
        from unittest import mock
        calls = []

        def once(place, photo, tris, ex, sky, out, radius, veil=None, coarse_grid=None, tilt=None):
            calls.append((radius, veil, coarse_grid)); Path(out).mkdir()
            cost, alone, moved = by_radius[radius]
            return {"best": {"cost": cost}, "alone": alone, "moved_m": moved}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ps, "_place_once", once):
            res = ps.step_place("p.jpg", "tris.npz", {"search_radius_m": limit}, "blue", Path(d), veil="tree.png")
        return res, calls

    def test_a_good_fix_is_searched_once(self):
        res, calls = self.place({40.0: (0.6, True, 18.0)}, 300.0)
        self.assertEqual([c[0] for c in calls], [40.0])
        self.assertEqual(res["radius"], 40.0)
        self.assertEqual(calls[0][1], "tree.png")

    def test_an_answer_that_fits_badly_is_not_taken_for_decided(self):
        res, calls = self.place({40.0: (2.0, True, 10.0), 100.0: (1.2, True, 50.0), 250.0: (0.7, True, 190.0)}, 500.0)
        self.assertEqual([c[0] for c in calls], [40.0, 100.0, 250.0])
        self.assertEqual(res["best"]["cost"], 0.7)
        self.assertEqual([t["cost"] for t in res["tried"]], [2.0, 1.2, 0.7])

    def test_an_answer_on_the_rim_or_not_alone_widens_up_to_the_limit(self):
        res, calls = self.place({40.0: (0.5, True, 38.0), 80.0: (0.5, False, 20.0)}, 80.0)
        self.assertEqual([c[0] for c in calls], [40.0, 80.0])

    def test_a_wide_search_steps_coarser(self):
        _, calls = self.place({r: (2.0, True, 1.0) for r in (40.0, 100.0, 250.0, 500.0)}, 500.0)
        self.assertEqual([c[2] for c in calls], [8.0, 8.0, 8.0, 16.0])


class Trees(unittest.TestCase):
    def test_the_tree_mask_is_made_once_by_the_vision_python(self):
        import tempfile
        from unittest import mock
        ran = []

        def run(cmd, **kw):
            ran.append(cmd)
            out = Path(next(a for a in cmd if a.startswith("--out=")).split("=", 1)[1]); out.mkdir()
            (out / "tree.png").write_bytes(b"png"); (out / "sky.png").write_bytes(b"png")
        with tempfile.TemporaryDirectory() as d, mock.patch("subprocess.run", run):
            f = ps.step_trees("p.jpg", Path(d), "vpython")
            self.assertEqual(f, Path(d) / "trees" / "tree.png")
            self.assertEqual(ps.step_trees("p.jpg", Path(d), "vpython"), f)
        self.assertEqual(len(ran), 1)
        self.assertEqual(ran[0][:3], ["vpython", "-m", "world_model.tree_mask"])
        self.assertIn("--photo=p.jpg", ran[0])

    def test_without_a_vision_python_it_stops(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d, self.assertRaises(SystemExit):
            ps.step_trees("p.jpg", Path(d), None)


class SkyReading(unittest.TestCase):
    """The colour reading is sharp and stays; the segmentation's sky replaces it only where colour missed much."""

    def reading(self, colour, seen):
        import json, tempfile
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "tree.json").write_text(json.dumps({"sky": seen}))
            got = ps.sky_reading({"kind": colour and "blue", "share": {"blue": colour or 0.0}}, Path(d) / "tree.png")
            return "seen" if got == Path(d) / "sky.png" else got

    def test_colour_is_kept_when_the_two_agree(self):
        self.assertEqual(self.reading(0.36, 0.34), "blue")
        self.assertEqual(self.reading(0.31, 0.33), "blue")

    def test_sky_behind_branches_that_colour_missed_is_taken_from_the_segmentation(self):
        self.assertEqual(self.reading(0.029, 0.049), "seen")

    def test_no_colour_sky_falls_back_to_the_segmentation_and_none_at_all_is_none(self):
        self.assertEqual(self.reading(None, 0.2), "seen")
        self.assertIsNone(self.reading(None, 0.01))


class Target(unittest.TestCase):
    def test_a_building_behind_the_trees_is_not_the_one_seen_most(self):
        big = np.zeros((6, 8), bool); big[:, :5] = True            # 30 px, 24 of them behind the tree
        small = np.zeros((6, 8), bool); small[:3, 5:] = True       # 9 px in the open
        trees = np.zeros((6, 8), bool); trees[:, :4] = True
        self.assertEqual(ps.seen_most({"big": big, "small": small}, None)[0], ("big", 30))
        self.assertEqual(ps.seen_most({"big": big, "small": small}, trees), [("small", 9), ("big", 6)])


class Scene(unittest.TestCase):
    def test_the_box_around_the_place_found_is_built_before_the_building_is_read(self):
        """A fix that was 360 m off puts the camera where the first box has no buildings behind it."""
        import tempfile
        from unittest import mock
        asked = []
        ex = {"lon": 139.7, "lat": 35.6}
        with tempfile.TemporaryDirectory() as d, mock.patch("buildings.plateau_pp.cached", lambda box: asked.append(box)):
            ps.step_scene(ex, {"eye": [360.0, -70.0, 3.0]}, Path(d))
            ps.step_scene(ex, {"eye": [360.0, -70.0, 3.0]}, Path(d))
        self.assertEqual(len(asked), 1)
        w, s, e, n = asked[0]
        self.assertAlmostEqual(((s + n) / 2 - 35.6) * 110950, -70.0, places=3)
        self.assertAlmostEqual((n - s) * 110950, 2 * ps.SCENE_RADIUS, places=3)


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


class Refusals(unittest.TestCase):
    """What cannot be solved is refused by name, not left to fail somewhere further down."""

    def test_a_photo_whose_exif_holds_no_position_has_no_fix(self):
        self.assertTrue(ps.has_fix({"lon": 139.7, "lat": 35.6}))
        self.assertFalse(ps.has_fix({"lon": float("nan"), "lat": float("nan")}))
        self.assertFalse(ps.has_fix({"lon": None, "lat": 35.6}))
        self.assertFalse(ps.has_fix({}))

    def test_a_building_of_which_nothing_shows_gives_no_prompt(self):
        seen = np.zeros((6, 8), bool); seen[2:4, 1:5] = True
        self.assertEqual(ps.prompt_of(seen), {"point": [5.0, 5.0], "box": [2, 4, 9, 7]})
        self.assertIsNone(ps.prompt_of(np.zeros((6, 8), bool)))


class Tilt(unittest.TestCase):
    """The pitch and roll read from the picture's upright lines narrow the place search; without them it is as it was."""

    def once(self, tilt):
        got = {}

        def place(*a, **k):
            got.update(k)
        ps._place_once(place, "p.jpg", "tris.npz", {"fx": 3000.0, "hfov_deg": 60.0}, "blue", "out", 40.0, tilt=tilt)
        return got

    def test_a_reading_many_lines_agree_on_is_searched_around(self):
        got = self.once({"pitch": 21.1, "roll": 2.6, "lines": 99, "of": 258, "share": 0.4})
        self.assertEqual((got["pitch"], got["roll"]), ("19:23:2", "1:4:1.5"))

    def test_no_reading_leaves_the_ranges_to_photo_place(self):
        got = self.once(None)
        self.assertNotIn("pitch", got)
        self.assertNotIn("roll", got)

    def test_a_photo_without_a_focal_length_is_not_read(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(ps.step_upright("p.jpg", {"fx": None}, Path(d)))
            self.assertFalse((Path(d) / "upright.json").exists())
