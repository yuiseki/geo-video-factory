import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from photos import photo_walk as pw  # noqa: E402


def photo(x=0.0, y=0.0, z=1.6, bearing=0.0, pitch=0.0, fov_v=50.0, width=1920, height=1280, **more):
    return dict(eye=(x, y, z), bearing=bearing, pitch=pitch, fov_v=fov_v, width=width, height=height, **more)


class CoverageTests(unittest.TestCase):
    def test_from_the_photos_own_pose_the_whole_frame_is_covered(self):
        p = photo(bearing=40.0, pitch=10.0)
        self.assertEqual(pw.coverage(p, p["eye"], 40.0, 10.0), 1.0)

    def test_looking_the_other_way_nothing_is_covered(self):
        p = photo(bearing=40.0)
        self.assertEqual(pw.coverage(p, p["eye"], 220.0, 0.0), 0.0)

    def test_walking_forward_along_a_level_axis_keeps_the_frame_covered(self):
        p = photo(bearing=0.0)
        for step in (5.0, 15.0, 30.0):
            self.assertEqual(pw.coverage(p, (0.0, step, 1.6), 0.0, 0.0), 1.0)

    def test_stepping_back_or_sideways_uncovers_part_of_the_frame(self):
        p = photo(bearing=0.0)
        self.assertLess(pw.coverage(p, (0.0, -10.0, 1.6), 0.0, 0.0), 1.0)
        self.assertLess(pw.coverage(p, (8.0, 0.0, 1.6), 0.0, 0.0), 1.0)

    def test_turning_uncovers_the_side_turned_toward_in_proportion(self):
        p = photo(bearing=0.0)
        small, large = pw.coverage(p, p["eye"], 10.0, 0.0), pw.coverage(p, p["eye"], 30.0, 0.0)
        self.assertLess(large, small)
        self.assertLess(small, 1.0)
        self.assertGreater(small, 0.7)

    def test_a_narrower_frame_tolerates_a_turn_the_photo_still_contains(self):
        p = photo(bearing=0.0, fov_v=60.0)
        self.assertEqual(pw.coverage(p, p["eye"], 8.0, 0.0, fov_v=30.0), 1.0)

    def test_the_ground_is_not_the_photos_job(self):
        # level frame under a photo that looked up: the rows the photo misses only see the ground.
        # (not exactly 1: a camera pitched up spans less bearing at the horizon than a level one)
        p = photo(bearing=0.0, pitch=14.0, fov_v=53.0)
        self.assertGreater(pw.coverage(p, p["eye"], 0.0, 0.0, ground_z=0.0), 0.98)
        # without a ground those rows count as missing
        self.assertLess(pw.coverage(p, p["eye"], 0.0, 0.0, ground_z=-1e9), 0.8)


class WalkLineTests(unittest.TestCase):
    A, B = (0.0, 0.0), (0.0, 30.0)

    def test_the_line_moves_sideways_onto_the_photos_eye_inside_the_crosswalk(self):
        line = pw.walk_line(self.A, self.B, 8.0, photo(x=1.7, y=2.2))
        self.assertAlmostEqual(line["start"][0], 1.7)
        self.assertAlmostEqual(line["end"][0], 1.7)
        self.assertAlmostEqual(line["offset"], 1.7)
        self.assertAlmostEqual(line["start"][1], 2.2)          # starts where the photo was taken
        self.assertAlmostEqual(line["end"][1], 30.0)
        self.assertAlmostEqual(line["bearing"], 0.0)
        self.assertAlmostEqual(line["eye_gap"], 0.0)

    def test_an_eye_outside_the_crosswalk_keeps_the_line_inside_and_reports_the_gap(self):
        line = pw.walk_line(self.A, self.B, 8.0, photo(x=9.0, y=-5.0), margin=0.5)
        self.assertAlmostEqual(line["start"][0], 3.5)
        self.assertAlmostEqual(line["start"][1], 0.0)          # an eye behind the kerb: start at the kerb
        self.assertAlmostEqual(line["eye_gap"], math.hypot(5.5, 5.0))

    def test_direction_follows_the_order_of_the_ends(self):
        self.assertAlmostEqual(pw.walk_line(self.B, self.A, 8.0, photo(x=0.0, y=30.0))["bearing"], 180.0)
        self.assertAlmostEqual(pw.bearing((0, 0), (-1, 1)), 315.0)


class StraightWalkTests(unittest.TestCase):
    def test_constant_speed_on_the_line_looking_along_it(self):
        frames = pw.straight_walk((1.0, 2.0), (1.0, 14.0), eye_z=55.0, pitch=6.0, speed=1.2, fps=24)
        self.assertEqual(len(frames), 241)                      # 12 m at 1.2 m/s = 10 s, both ends included
        self.assertEqual({(f["x"], f["bearing"], f["pitch"], f["z"]) for f in frames}, {(1.0, 0.0, 6.0, 55.0)})
        steps = [b["y"] - a["y"] for a, b in zip(frames, frames[1:])]
        self.assertAlmostEqual(min(steps), 0.05)
        self.assertAlmostEqual(max(steps), 0.05)
        self.assertAlmostEqual(frames[-1]["y"], 14.0)

    def test_westward_walk_has_bearing_270(self):
        frames = pw.straight_walk((10.0, 0.0), (0.0, 0.0), eye_z=1.6, pitch=0.0, speed=1.0, fps=10)
        self.assertEqual(len(frames), 101)
        self.assertAlmostEqual(frames[3]["bearing"], 270.0)
        self.assertAlmostEqual(frames[50]["x"], 5.0)


class RankTests(unittest.TestCase):
    def setUp(self):
        self.crosswalks = [{"name": "main", "a": (0.0, 0.0), "b": (0.0, 30.0), "width": 8.0}]
        self.photos = {
            "along": photo(x=1.0, y=1.0, bearing=2.0, pitch=8.0, n3d=600),
            "across": photo(x=1.0, y=1.0, bearing=90.0, n3d=600),
            "far": photo(x=40.0, y=0.0, bearing=0.0, n3d=600),
            "back": photo(x=-1.0, y=29.0, bearing=181.0, n3d=600),
            "aerial": photo(x=1.0, y=1.0, z=120.0, bearing=0.0, pitch=-25.0, n3d=600),
        }

    def test_the_photo_taken_on_the_crosswalk_looking_along_it_wins_each_direction(self):
        rows = pw.rank_walks(self.photos, self.crosswalks, ground_z=0.0)
        best = {d: [r for r in rows if r["direction"] == d][0] for d in ("ab", "ba")}
        self.assertEqual((best["ab"]["photo"], best["ba"]["photo"]), ("along", "back"))
        self.assertEqual({(r["photo"], r["direction"]) for r in rows[:2]}, {("along", "ab"), ("back", "ba")})
        self.assertEqual(rows[0]["fails"], [])
        self.assertGreater(rows[0]["coverage_min"], 0.95)
        self.assertEqual(len(rows), 2 * len(self.photos))

    def test_rows_say_why_a_photo_fails(self):
        rows = {(r["photo"], r["direction"]): r for r in pw.rank_walks(self.photos, self.crosswalks, ground_z=0.0)}
        self.assertEqual(rows[("along", "ab")]["fails"], [])
        self.assertIn("coverage", rows[("across", "ab")]["fails"])
        self.assertIn("eye_gap", rows[("far", "ab")]["fails"])
        self.assertIn("eye_height", rows[("aerial", "ab")]["fails"])
        self.assertAlmostEqual(rows[("along", "ab")]["turn"], 2.0)
        self.assertAlmostEqual(rows[("along", "ab")]["walk_m"], 29.0)

    def test_detail_compares_the_photos_pixels_per_degree_with_the_frames(self):
        soft = dict(self.photos, along=photo(x=1.0, y=1.0, bearing=2.0, fov_v=71.0, width=1536, height=864))
        row = [r for r in pw.rank_walks(soft, self.crosswalks, ground_z=0.0, frame_height=640)
               if r["photo"] == "along" and r["direction"] == "ab"][0]
        self.assertAlmostEqual(row["detail"], 864 / 640, places=3)   # the frame takes the photo's own fov
        self.assertIn("detail", row["fails"])


class GeoTests(unittest.TestCase):
    def test_crosswalks_in_lon_lat_become_local_metres(self):
        doc = {"crosswalks": [{"name": "d", "width": 8.0,
                               "line": [[139.7006562, 35.6593767], [139.7004627, 35.6596179]]}]}
        cw = pw.crosswalks_local(doc, (139.70055, 35.65950))[0]
        self.assertAlmostEqual(cw["a"][0], 9.6, delta=0.1)
        self.assertAlmostEqual(cw["a"][1], -13.7, delta=0.1)
        self.assertAlmostEqual(pw.bearing(cw["a"], cw["b"]), 326.8, delta=0.3)
        self.assertEqual((cw["name"], cw["width"]), ("d", 8.0))


if __name__ == "__main__":
    unittest.main()
