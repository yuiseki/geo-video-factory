import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sfm_compare as sc  # noqa: E402


def rot_z(deg):
    a = math.radians(deg)
    return np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])


def looking(heading_deg):
    """World-to-camera rotation of a level camera looking toward heading (0 north, 90 east)."""
    h = math.radians(heading_deg)
    fwd = np.array([math.sin(h), math.cos(h), 0.0])
    right = np.array([math.cos(h), -math.sin(h), 0.0])
    down = np.array([0.0, 0.0, -1.0])
    return np.stack([right, down, fwd])


class Frames(unittest.TestCase):
    def test_lonlat_round_trip(self):
        o = (139.776, 35.7116)
        e, n = sc.to_enu(139.777, 35.7120, o)
        self.assertAlmostEqual(e, 0.001 * 111320 * math.cos(math.radians(35.7116)), places=6)
        lon, lat = sc.from_enu(e, n, o)
        self.assertAlmostEqual(lon, 139.777, places=9)
        self.assertAlmostEqual(lat, 35.7120, places=9)

    def test_heading_of_a_camera(self):
        for h in (0, 45, 90, 200, 359):
            self.assertAlmostEqual(sc.heading(looking(h)) % 360, h, places=6)

    def test_angle_between_rotations(self):
        self.assertAlmostEqual(sc.angle_deg(looking(10), looking(40)), 30, places=6)


class Readers(unittest.TestCase):
    def test_colmap_text_model(self):
        r = looking(90)
        c = np.array([3.0, 4.0, 1.5])
        t = -r @ c
        q = sc.r_to_quat(r)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "images.txt").write_text(f"# c\n1 {q[0]} {q[1]} {q[2]} {q[3]} {t[0]} {t[1]} {t[2]} 1 007.jpg\n\n")
            (d / "enu_origin.txt").write_text("# lat lon alt\n35.7 139.7 0\n")
            cams = sc.colmap_cams(d)
        self.assertEqual(list(cams), ["007.jpg"])
        lon, lat = cams["007.jpg"]["lonlat"]
        self.assertAlmostEqual(sc.to_enu(lon, lat, (139.7, 35.7))[0], 3.0, delta=0.02)
        self.assertAlmostEqual(sc.angle_deg(cams["007.jpg"]["R"], r), 0, places=5)

    def test_opensfm_reconstructions_are_components(self):
        r = looking(180)
        c = np.array([-2.0, 5.0, 1.0])
        aa = sc.r_to_axis_angle(r)
        recs = [{"shots": {"001.jpg": {"rotation": list(aa), "translation": list(-r @ c)}}},
                {"shots": {"002.jpg": {"rotation": [0, 0, 0], "translation": [0, 0, 0]},
                           "003.jpg": {"rotation": [0, 0, 0], "translation": [0, 0, 0]}}}]
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "reconstruction.json").write_text(json.dumps(recs))
            (d / "reference_lla.json").write_text(json.dumps({"latitude": 35.7, "longitude": 139.7, "altitude": 0}))
            comps = sc.opensfm_cams(d)
        self.assertEqual([sorted(x) for x in comps], [["001.jpg"], ["002.jpg", "003.jpg"]])
        lon, lat = comps[0]["001.jpg"]["lonlat"]
        e, n = sc.to_enu(lon, lat, (139.7, 35.7))
        self.assertAlmostEqual(e, -2.0, delta=0.02)
        self.assertAlmostEqual(n, 5.0, delta=0.02)
        self.assertAlmostEqual(sc.angle_deg(comps[0]["001.jpg"]["R"], r), 0, places=5)


class Scoring(unittest.TestCase):
    def test_errors_against_truth(self):
        o = (139.776, 35.7116)
        truth = {"a": {"lonlat": sc.from_enu(0, 0, o), "R": looking(0)},
                 "b": {"lonlat": sc.from_enu(10, 0, o), "R": looking(90)}}
        model = {"a": {"lonlat": sc.from_enu(3, 4, o), "R": looking(10)},
                 "b": {"lonlat": sc.from_enu(10, 0, o), "R": looking(90)},
                 "c": {"lonlat": sc.from_enu(50, 0, o), "R": looking(0)}}
        rows = sc.against_truth(model, truth)
        self.assertEqual([r["name"] for r in rows], ["a", "b"])
        self.assertAlmostEqual(rows[0]["apart_m"], 5.0, places=3)
        self.assertAlmostEqual(rows[0]["turn_deg"], 10.0, places=3)
        self.assertAlmostEqual(rows[1]["apart_m"], 0.0, places=3)

    def test_missing_truth_photo_is_reported_unregistered(self):
        o = (139.776, 35.7116)
        truth = {"a": {"lonlat": sc.from_enu(0, 0, o), "R": looking(0)}}
        rows = sc.against_truth({}, truth)
        self.assertEqual(rows, [{"name": "a", "registered": False}])

    def test_components_merge_with_the_larger_one_winning(self):
        a = {"x": {"id": "big"}, "y": {"id": "big"}, "z": {"id": "big"}}
        b = {"z": {"id": "small"}, "w": {"id": "small"}}
        m = sc.merged([b, a])
        self.assertEqual({k: v["id"] for k, v in m.items()}, {"x": "big", "y": "big", "z": "big", "w": "small"})

    def test_similarity_fit_recovers_scale_rotation_shift(self):
        rng = np.random.default_rng(0)
        src = rng.normal(size=(6, 3))
        rr = rot_z(30)
        dst = 2.5 * src @ rr.T + np.array([1.0, -2.0, 0.5])
        s, r, t = sc.similarity(src, dst)
        self.assertAlmostEqual(s, 2.5, places=6)
        self.assertAlmostEqual(sc.angle_deg(r, rr), 0, places=5)
        np.testing.assert_allclose(s * src @ r.T + t, dst, atol=1e-9)


if __name__ == "__main__":
    unittest.main()
