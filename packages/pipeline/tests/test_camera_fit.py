import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import blender_geo as bg  # noqa: E402
import camera_fit  # noqa: E402

W, H = 1920, 1280


class FitTests(unittest.TestCase):
    def test_recovers_a_known_camera_from_point_correspondences(self):
        truth = {"location": (12.0, -30.0, 1.6), "tilt": 98, "bearing": -40, "fov": 55, "shift_px": 0}
        points = [(-20, 30, 25), (10, 25, 32), (-15, 28, 4), (-40, 10, 24), (5, 20, 3), (15, 22, 2), (0, 35, 40)]
        pixels = [bg.project_point(truth, p, W, H) for p in points]
        guess = {"location": (5.0, -20.0, 1.6), "tilt": 95, "bearing": -30, "fov": 50, "shift_px": 0}
        fitted, rms = camera_fit.fit_camera(points, pixels, W, H, guess, fixed={"shift_px": 0})
        self.assertLess(rms, 1e-3)
        for i in range(3):
            self.assertAlmostEqual(fitted["location"][i], truth["location"][i], places=3)
        self.assertAlmostEqual(fitted["bearing"], -40, places=3)
        self.assertAlmostEqual(fitted["tilt"], 98, places=3)
        self.assertAlmostEqual(fitted["fov"], 55, places=3)

    def test_vertical_lines_and_known_edges_recover_tilt_roll_and_bearing(self):
        truth = {"location": (4.0, -45.0, 1.6), "tilt": 104, "bearing": -12, "fov": 62, "shift_px": 0, "roll": 2.5}
        # Two noisy-free sign centres only (too few on their own), plus verticals and two known building edges.
        points = [(-20, 30, 25), (10, 25, 32)]
        pixels = [bg.project_point(truth, p, W, H) for p in points]
        verticals = []
        for x, y in ((-30, 20), (-10, 28), (15, 22), (25, 35)):
            a = bg.project_point(truth, (x, y, 5), W, H)
            b = bg.project_point(truth, (x, y, 30), W, H)
            verticals.append([a, b])
        edges = []
        for x, y in ((-5, 10), (12, 8)):
            edges.append({"xy": (x, y), "pixels": [bg.project_point(truth, (x, y, 8), W, H),
                                                   bg.project_point(truth, (x, y, 40), W, H)]})
        guess = {"location": (0.0, -35.0, 1.6), "tilt": 98, "bearing": 0, "fov": 55, "shift_px": 0, "roll": 0}
        fitted, rms = camera_fit.fit_camera(points, pixels, W, H, guess, fixed={"shift_px": 0, "z": 1.6},
                                            verticals=verticals, edges=edges)
        self.assertLess(rms, 1e-3)
        self.assertAlmostEqual(fitted["roll"], 2.5, places=3)
        self.assertAlmostEqual(fitted["tilt"], 104, places=3)
        self.assertAlmostEqual(fitted["bearing"], -12, places=3)
        self.assertAlmostEqual(fitted["fov"], 62, places=2)
        self.assertAlmostEqual(fitted["location"][1], -45.0, places=2)

    def test_two_views_recover_heights_that_one_view_cannot(self):
        # Street-level view (edges + verticals only) and a high telephoto view, sharing six unknown points.
        street = {"location": (0.0, -40.0, 1.6), "tilt": 100, "bearing": -5, "fov": 66, "shift_px": 0, "roll": -0.5}
        high = {"location": (60.0, -10.0, 35.0), "tilt": 80, "bearing": -95, "fov": 25, "shift_px": 0, "roll": 1.0}
        # Corners of three signs (as in practice: several signs' four corners).
        truth = [(-20, 20, 26), (-12, 20, 26), (-12, 20, 18), (-20, 20, 18),
                 (-30, 15, 14), (-27, 15, 14), (-27, 15, 6), (-30, 15, 6),
                 (-8, 24, 12), (-2, 23, 12), (-2, 23, 9), (-8, 24, 9)]
        size = {"street": (1920, 1280), "high": (1920, 1440)}
        cams = {"street": street, "high": high}
        views = {}
        for name, cam in cams.items():
            w, h = size[name]
            verticals = []
            for x, y in ((-28, 25), (-15, 22), (-5, 18)):
                verticals.append([bg.project_point(cam, (x, y, 4), w, h), bg.project_point(cam, (x, y, 30), w, h)])
            views[name] = {"size": size[name], "points": [bg.project_point(cam, p, w, h) for p in truth],
                           "verticals": verticals, "edges": []}
        # The high view must also see known corners: otherwise the shared points can slide along the
        # street camera's rays (a scale about the street camera) while the high camera follows them.
        for x, y in ((-35, 28), (-10, 30)):
            views["high"]["edges"].append({"xy": (x, y), "pixels": [bg.project_point(high, (x, y, 8), 1920, 1440),
                                                                   bg.project_point(high, (x, y, 30), 1920, 1440)]})
        # Three known corners: two only fix the angle between them, leaving the camera free on a circle.
        for x, y in ((-2, 10), (14, 8), (-25, 5)):
            views["street"]["edges"].append({"xy": (x, y), "pixels": [bg.project_point(street, (x, y, 8), 1920, 1280),
                                                                     bg.project_point(street, (x, y, 40), 1920, 1280)]})
        initial = {
            "street": {"location": (2.0, -35.0, 1.6), "tilt": 97, "bearing": 0, "fov": 60, "shift_px": 0, "roll": 0},
            "high": {"location": (50.0, -20.0, 25.0), "tilt": 83, "bearing": -90, "fov": 30, "shift_px": 0, "roll": 0},
        }
        fixed = {"street": {"z": 1.6, "shift_px": 0}, "high": {"shift_px": 0}}
        cameras, points, rms = camera_fit.fit_views(views, initial, fixed, point_guess=[(-15, 15, 15)] * len(truth))
        self.assertLess(rms, 1e-3)
        for got, want in zip(points, truth):
            self.assertTrue(all(abs(a - b) < 1e-3 for a, b in zip(got, want)), (got, want))
        self.assertAlmostEqual(cameras["high"]["location"][2], 35.0, places=2)
        self.assertAlmostEqual(cameras["street"]["tilt"], 100, places=2)

    def test_report_lists_per_point_residuals_and_the_eye_position(self):
        truth = {"location": (0.0, -30.0, 1.6), "tilt": 95, "bearing": 0, "fov": 60, "shift_px": 0}
        origin = [139.70, 35.66]
        lnglats = [[139.7001, 35.6601], [139.6999, 35.6602], [139.7000, 35.6603], [139.7002, 35.6601], [139.6998, 35.6600]]
        heights = [20.0, 5.0, 30.0, 3.0, 12.0]
        points = []
        for (lng, lat), z in zip(lnglats, heights):
            x, y = bg.local_meters([lng, lat], origin)
            points.append({"name": f"p{len(points)}", "lngLat": [lng, lat], "altitudeM": z,
                           "pixel": list(bg.project_point(truth, (x, y, z), W, H))})
        spec = {"width": W, "height": H, "origin": origin, "points": points,
                "initial": {"location": [0, -25, 1.6], "tilt": 92, "bearing": 5, "fov": 55, "shift_px": 0},
                "fixed": {"shift_px": 0}}
        report = camera_fit.report(spec)
        self.assertLess(report["rmsPx"], 1e-3)
        self.assertAlmostEqual(report["eye"][2], 1.6, places=3)
        self.assertEqual(set(report["residualsPx"]), {"p0", "p1", "p2", "p3", "p4"})


if __name__ == "__main__":
    unittest.main()
