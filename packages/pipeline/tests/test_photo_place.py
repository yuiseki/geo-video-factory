"""photo_place: one photograph placed on a city model by the line between the buildings and the sky."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from geo import photo_place as pp  # noqa: E402
from geo import corner_match as cm  # noqa: E402
from geo import skyline_match as sm  # noqa: E402

BINS = 360


def box(x0, y0, x1, y1, top):
    """The four walls and the roof of a box standing on z = 0, as triangles (n, 3, 3)."""
    c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    tris = []
    for (ax, ay), (bx, by) in zip(c, c[1:] + c[:1]):
        tris += [[(ax, ay, 0), (bx, by, 0), (bx, by, top)], [(ax, ay, 0), (bx, by, top), (ax, ay, top)]]
    tris += [[(*c[0], top), (*c[1], top), (*c[2], top)], [(*c[0], top), (*c[2], top), (*c[3], top)]]
    return np.array(tris, float)


def town():
    """Boxes of different heights and widths north of the origin, low enough for their roofs to be in the picture: no two standing points see the same roofline."""
    return np.concatenate([box(-60, 40, -35, 60, 12), box(-30, 45, -5, 70, 22), box(0, 50, 18, 65, 9),
                           box(22, 38, 50, 58, 28), box(55, 45, 80, 70, 16), box(-90, 30, -65, 50, 19)])


def photograph(tris, eye, heading, pitch, roll, hfov, size=(360, 240)):
    """What a camera at this pose sees of the town: blue sky above the roofline, grey below."""
    w, h = size
    f = w / 2 / np.tan(np.radians(hfov) / 2)
    az, el = sm.pixel_rays(w, h, f, w / 2, h / 2, 0.0, pp.camera(heading, pitch, roll), step=1)
    line = np.nan_to_num(sm.model_skyline(*sm.unique_edges(tris), eye, bins=3600), nan=0.0)
    sky = el > line[np.floor(az / 0.1).astype(int) % 3600]
    rgb = np.where(sky[..., None], np.array([70, 130, 230]), np.array([120, 115, 110])).astype(np.uint8)
    return rgb, sky


def canyon_photograph(tris, eye, heading, pitch, hfov, size=(360, 240)):
    """A photo without sky: the walls change brightness at every corner the camera can see (a vertical edge of the
    world), nothing else."""
    w, h = size
    f = w / 2 / np.tan(np.radians(hfov) / 2)
    az, _ = sm.pixel_rays(w, h, f, w / 2, h / 2, 0.0, pp.camera(heading, pitch, 0.0), step=1)
    corners = np.flatnonzero(cm.model_corners(cm.prepare(tris, eye[2] + 3), eye, bins=3600)) * 0.1
    passed = (az[..., None] >= corners).sum(-1)
    return (100 + 60 * (passed % 2)).astype(float), np.zeros((h, w), bool)


class SpanTests(unittest.TestCase):
    def test_the_end_is_included(self):
        np.testing.assert_allclose(pp.span("0:30:10"), [0, 10, 20, 30])
        np.testing.assert_allclose(pp.span("-2:2:2"), [-2, 0, 2])

    def test_a_single_value(self):
        np.testing.assert_allclose(pp.span("5:5:1"), [5])


class CameraTests(unittest.TestCase):
    def test_level_and_looking_north(self):
        R = pp.camera(0, 0, 0)
        np.testing.assert_allclose(R @ [0, 1, 0], [0, 0, 1], atol=1e-12)   # north is forward
        np.testing.assert_allclose(R @ [1, 0, 0], [1, 0, 0], atol=1e-12)   # east is right
        np.testing.assert_allclose(R @ [0, 0, 1], [0, -1, 0], atol=1e-12)  # up is up in the picture

    def test_heading_is_clockwise_from_north(self):
        np.testing.assert_allclose(pp.camera(90, 0, 0) @ [1, 0, 0], [0, 0, 1], atol=1e-12)

    def test_pitch_looks_up(self):
        np.testing.assert_allclose(pp.camera(0, 90, 0) @ [0, 0, 1], [0, 0, 1], atol=1e-12)

    def test_it_is_a_rotation(self):
        R = pp.camera(33, 12, -4)
        np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-12)
        self.assertAlmostEqual(float(np.linalg.det(R)), 1.0)

    def test_positive_roll_turns_the_picture_clockwise(self):
        x, y, _ = pp.camera(0, 0, 10) @ [0, 0, 1]  # the world's up, drawn in the picture (y is down)
        self.assertLess(y, 0)
        self.assertGreater(x, 0)


class SkyMaskTests(unittest.TestCase):
    def test_blue_sky_above_grey_buildings(self):
        rgb, sky = photograph(town(), np.array([0.0, 0.0, 1.6]), 0, 10, 0, 70)
        found = pp.sky_mask(rgb, "blue")
        self.assertGreater((found == sky).mean(), 0.98)

    def test_an_overcast_sky_is_bright_and_touches_the_top(self):
        rgb = np.full((120, 160, 3), 90, np.uint8)
        rgb[:50] = 230
        rgb[90:110, 40:120] = 240  # a bright wall that does not reach the top
        found = pp.sky_mask(rgb, "bright")
        self.assertGreater(found[:45].mean(), 0.99)  # the opening rounds the corners
        self.assertFalse(found[60:].any())

    def test_a_night_sky_is_dark_and_the_threshold_can_move(self):
        rgb = np.full((120, 160, 3), 150, np.uint8)
        rgb[:50] = 30
        self.assertGreater(pp.sky_mask(rgb, "dark")[:45].mean(), 0.99)
        self.assertFalse(pp.sky_mask(rgb, "dark", dark_below=20).any())

    def test_a_small_blue_patch_is_not_sky(self):
        rgb = np.full((200, 300, 3), 110, np.uint8)
        rgb[:6, :8] = (70, 130, 230)
        self.assertFalse(pp.sky_mask(rgb, "blue").any())

    def test_an_unknown_kind_is_an_error(self):
        with self.assertRaises(ValueError):
            pp.sky_mask(np.zeros((10, 10, 3), np.uint8), "green")


class GridTests(unittest.TestCase):
    def test_places_cover_the_square_and_stand_at_one_height(self):
        places, xs, ys = pp.grid_places(10, 20, 4, 2, 5.5)
        np.testing.assert_allclose(xs, [6, 8, 10, 12, 14])
        np.testing.assert_allclose(ys, [16, 18, 20, 22, 24])
        self.assertEqual(places.shape, (25, 3))
        np.testing.assert_allclose(places[0], [6, 16, 5.5])
        np.testing.assert_allclose(places[1], [8, 16, 5.5])  # east runs fastest: rows are north

    def test_the_ground_is_the_low_end_of_the_model_near_the_point(self):
        tris = np.concatenate([town(), box(2000, 2000, 2010, 2010, 5) - [0, 0, 300]])
        self.assertAlmostEqual(pp.ground_level(tris, 0, 0), 0.0)

    def test_no_model_near_the_point_is_an_error(self):
        with self.assertRaises(ValueError):
            pp.ground_level(town(), 5000, 5000)


class SearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tris = town()
        cls.edges = sm.unique_edges(cls.tris)
        cls.eye = np.array([4.0, -6.0, 1.6])
        cls.rgb, cls.sky = photograph(cls.tris, cls.eye, 8.0, 12.0, 0.0, 70.0)
        cls.places, _, _ = pp.grid_places(0, 0, 12, 2, 1.6)
        cls.poses = [(p, 0.0, 70.0) for p in (8.0, 12.0, 16.0)]

    def test_the_pose_the_picture_was_made_from_is_found(self):
        best, cost, turn = pp.search(self.edges, self.sky, self.places, self.poses, bins=BINS, workers=None)
        self.assertEqual(cost.shape, (3, len(self.places)))
        self.assertEqual(turn.shape, cost.shape)
        self.assertLessEqual(np.hypot(best["east"] - 4, best["north"] + 6), 2.0)
        self.assertEqual(best["pitch"], 12.0)
        self.assertLessEqual(abs(best["heading"] - 8.0), 1.0)
        self.assertAlmostEqual(best["up"], 1.6)
        self.assertAlmostEqual(best["cost"], float(np.nanmin(cost)))
        self.assertLess(best["cost"], 0.5)

    def test_corners_place_a_photo_without_sky(self):
        gray, nosky = canyon_photograph(self.tris, self.eye, 8.0, 12.0, 70.0)
        corners = dict(prep=cm.prepare(self.tris, 4.6), gray=gray, weight=2.0)
        with self.assertRaises(SystemExit):                     # no roofline: the skyline alone refuses
            pp.search(self.edges, nosky, self.places, self.poses, bins=BINS, workers=None, min_sky=10)
        best, _, _ = pp.search(self.edges, nosky, self.places, self.poses, bins=BINS, workers=None, min_sky=10,
                               corners=corners)
        self.assertLessEqual(np.hypot(best["east"] - 4, best["north"] + 6), 2.0)
        self.assertLessEqual(abs((best["heading"] - 8.0 + 180) % 360 - 180), 1.0)

    def test_worker_processes_give_the_same_answer(self):
        alone = pp.search(self.edges, self.sky, self.places, self.poses, bins=BINS, workers=None)
        pooled = pp.search(self.edges, self.sky, self.places, self.poses, bins=BINS, workers=(2, 2))
        self.assertEqual(alone[0], pooled[0])
        np.testing.assert_array_equal(alone[1], pooled[1])
        np.testing.assert_array_equal(alone[2], pooled[2])

    def test_headings_outside_the_window_are_not_considered(self):
        best, cost, turn = pp.search(self.edges, self.sky, self.places, self.poses, headings=(90.0, 180.0),
                                     bins=BINS, workers=None)
        self.assertTrue(90.0 <= best["heading"] <= 180.0)
        self.assertTrue(((turn * 360 / BINS >= 90) & (turn * 360 / BINS <= 180)).all())
        self.assertGreater(best["cost"], 0.5)

    def test_a_window_may_cross_north(self):
        best, _, _ = pp.search(self.edges, self.sky, self.places, self.poses, headings=(350.0, 20.0),
                               bins=BINS, workers=None)
        self.assertLessEqual(abs(best["heading"] - 8.0), 1.0)

    def test_rivals_start_with_the_best_place_and_keep_their_distance(self):
        _, cost, turn = pp.search(self.edges, self.sky, self.places, self.poses, bins=BINS, workers=None)
        rivals = pp.rivals(self.places, self.poses, cost, turn, bins=BINS, count=3, apart=10.0)
        self.assertEqual(len(rivals), 3)
        self.assertAlmostEqual(rivals[0]["cost"], float(np.nanmin(cost)))
        self.assertEqual(sorted(r["cost"] for r in rivals), [r["cost"] for r in rivals])
        for i, a in enumerate(rivals):
            for b in rivals[:i]:
                self.assertGreaterEqual(np.hypot(a["east"] - b["east"], a["north"] - b["north"]), 10.0)
        self.assertEqual(set(rivals[0]), {"east", "north", "cost", "heading", "pitch", "hfov"})

    def test_a_place_is_alone_when_no_place_10_m_away_fits_as_well(self):
        r = lambda c: dict(east=0.0, north=0.0, cost=c, heading=0.0, pitch=0.0, hfov=60.0)
        self.assertTrue(pp.alone([r(0.59), r(0.97)]))
        self.assertTrue(pp.alone([r(1.08), r(1.112)]))         # 3 % apart: a choice was made
        self.assertFalse(pp.alone([r(0.0), r(0.0)]))           # no sky: every place fits
        self.assertFalse(pp.alone([r(1.914), r(1.922)]))       # within 1 %: a tie
        self.assertFalse(pp.alone([r(0.5)]))                   # nothing to compare with

    def test_the_fine_search_is_half_a_metre_and_half_a_degree_around_the_coarse_answer(self):
        coarse = dict(east=4.0, north=-6.0, up=1.6, pitch=12.0, roll=0.0, hfov=70.0)
        places, poses = pp.fine_space(coarse)
        self.assertEqual(places.shape, (17 * 17, 3))
        np.testing.assert_allclose(places[:, :2].min(0), [0.0, -10.0])
        np.testing.assert_allclose(places[:, :2].max(0), [8.0, -2.0])
        np.testing.assert_allclose(places[:, 2], 1.6)
        self.assertEqual(len(poses), 9 * 9 * 5)
        np.testing.assert_allclose(sorted({p[0] for p in poses}), np.arange(10, 14.01, 0.5))
        np.testing.assert_allclose(sorted({p[2] for p in poses}), 70 * np.linspace(0.96, 1.04, 5))


class PlaceTests(unittest.TestCase):
    """The whole run on a small picture: files and their contents."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.tris = town()
        rgb, _ = photograph(cls.tris, np.array([4.0, -6.0, 1.6]), 8.0, 12.0, 0.0, 70.0)
        Image.fromarray(rgb).save(root / "p01_town.png")
        np.savez_compressed(root / "tris.npz", tris=cls.tris.astype(np.float32))
        cls.out = root / "out"
        cls.lines = []
        cls.result = pp.place(root / "p01_town.png", root / "tris.npz", cls.out, 0.0, 0.0, 70.0,
                              radius=8, grid=2, pitch="8:16:4", roll="0:0:1", fov_range="1:1:1", mesh_radius=75,
                              work_w=360, bins=BINS, workers=None, fine_half=2.0, fine_roll=0.0, fine_fov=1, log=cls.lines.append)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_pose_is_recovered(self):
        best = self.result["best"]
        self.assertLessEqual(np.hypot(best["east"] - 4, best["north"] + 6), 1.0)
        self.assertLessEqual(abs(best["heading"] - 8), 1.0)
        self.assertLessEqual(abs(best["pitch"] - 12), 1.0)
        self.assertLessEqual(best["cost"], self.result["coarse"]["cost"])
        self.assertAlmostEqual(self.result["moved_m"], float(np.hypot(best["east"], best["north"])))

    def test_result_json_holds_what_was_returned(self):
        saved = json.loads((self.out / "result.json").read_text())
        self.assertEqual(saved, json.loads(json.dumps(self.result)))
        self.assertEqual(saved["photo"], "p01_town.png")
        self.assertEqual(saved["given"], [0.0, 0.0, 70.0])
        self.assertAlmostEqual(saved["ground"], 0.0)
        self.assertEqual(saved["eye_height"], 1.6)
        self.assertGreaterEqual(len(saved["rivals"]), 1)
        self.assertEqual(saved["alone"], pp.alone(saved["rivals"]))

    def test_cams_json_is_what_the_projection_reads(self):
        cams = json.loads((self.out / "cams.json").read_text())
        self.assertEqual(list(cams), ["p01"])
        cam = cams["p01"]
        best = self.result["best"]
        self.assertEqual((cam["name"], cam["width"], cam["height"], cam["model"]), ("p01_town.png", 360, 240, "PINHOLE"))
        self.assertTrue(Path(cam["photo"]).is_absolute())
        np.testing.assert_allclose(cam["eye"], [best["east"], best["north"], best["up"]])
        np.testing.assert_allclose(cam["Rw"], pp.camera(best["heading"], best["pitch"], best["roll"]))
        f = 180 / np.tan(np.radians(best["hfov"]) / 2)
        np.testing.assert_allclose(cam["params"], [f, f, 180, 120])
        self.assertAlmostEqual(cam["fov_v"], float(np.degrees(2 * np.arctan(120 / f))))
        self.assertEqual(cam["fit_roll_deg"], best["roll"])

    def test_the_mesh_is_the_model_around_the_camera(self):
        with np.load(self.out / "mesh.npz") as mesh:
            tris, ground = mesh["tris"], float(mesh["ground"])
        self.assertEqual(tris.dtype, np.float32)
        self.assertLess(len(tris), len(self.tris))
        self.assertGreater(len(tris), 0)
        best = self.result["best"]
        ctr = tris.mean(1)
        self.assertLess(np.hypot(ctr[:, 0] - best["east"], ctr[:, 1] - best["north"]).max(), 75)
        self.assertAlmostEqual(ground, 0.0)

    def test_the_pictures_for_the_eye_are_written(self):
        with Image.open(self.out / "mask.jpg") as im:
            self.assertEqual(im.size, (360, 240))
        with Image.open(self.out / "overlay.jpg") as im:
            self.assertEqual(im.size, (1600, 1067))
            px = np.asarray(im.convert("RGB")).astype(int)
        self.assertGreater(((px[..., 0] > 200) & (px[..., 1] < 90) & (px[..., 2] < 90)).sum(), 100)  # the red roofline
        with Image.open(self.out / "costmap.png") as im:
            self.assertGreaterEqual(min(im.size), 200)
            self.assertGreater(len(im.convert("RGB").getcolors(1 << 20)), 5)

    def test_the_overlay_roofline_lies_on_the_edge_of_the_sky(self):
        """The check that matters: at the found pose the model's roofline falls where the picture's sky ends."""
        best = self.result["best"]
        rgb, sky = photograph(self.tris, np.array([best["east"], best["north"], best["up"]]), best["heading"],
                              best["pitch"], best["roll"], best["hfov"])
        with Image.open(self.out.parent / "p01_town.png") as im:
            given = np.asarray(im)[..., 2] > 200
        self.assertGreater((sky == given).mean(), 0.97)

    def test_progress_is_reported(self):
        text = "\n".join(self.lines)
        for word in ("worked at 360 x 240", "sky ", "coarse:", "fine:", "placed "):
            self.assertIn(word, text)

    def test_the_key_and_the_ground_can_be_given(self):
        root = Path(self.tmp.name)
        result = pp.place(root / "p01_town.png", root / "tris.npz", root / "out2", 4.0, -6.0, 70.0, radius=2, grid=2,
                          pitch="12:12:1", roll="0:0:1", fov_range="1:1:1", key="town", ground=0.4, eye=1.2,
                          work_w=360, bins=BINS, workers=None, fine_half=2.0, fine_roll=0.0, fine_fov=1, log=lambda s: None)
        self.assertEqual(list(json.loads((root / "out2" / "cams.json").read_text())), ["town"])
        self.assertAlmostEqual(result["best"]["up"], 1.6)
        self.assertEqual(result["ground"], 0.4)


class MainTests(unittest.TestCase):
    def test_options_are_read_from_the_command_line(self):
        args = pp.parse_args(["photo.jpg", "tris.npz", "out", "10", "-20", "65", "--radius=40", "--grid=1",
                              "--pitch=0:10:2", "--sky=dark", "--dark-below=30", "--heading=350:20", "--key=abc",
                              "--mesh-radius=300", "--fov-range=0.9:1.1:5", "--eye=2", "--ground=3.5", "--roll=-1:1:1"])
        self.assertEqual(args[:3], ["photo.jpg", "tris.npz", "out"])
        self.assertEqual(args[3:6], [10.0, -20.0, 65.0])
        self.assertEqual(args[6], dict(radius=40.0, grid=1.0, pitch="0:10:2", sky="dark", dark_below=30.0,
                                       heading=(350.0, 20.0), key="abc", mesh_radius=300.0, fov_range="0.9:1.1:5",
                                       eye=2.0, ground=3.5, roll="-1:1:1"))

    def test_an_unknown_option_is_an_error(self):
        with self.assertRaises(SystemExit):
            pp.parse_args(["photo.jpg", "tris.npz", "out", "10", "-20", "65", "--radious=40"])

    def test_too_few_arguments_is_an_error(self):
        with self.assertRaises(SystemExit):
            pp.parse_args(["photo.jpg", "tris.npz", "out"])


if __name__ == "__main__":
    unittest.main()
