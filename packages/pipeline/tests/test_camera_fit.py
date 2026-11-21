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
