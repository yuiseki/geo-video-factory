import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import blender_geo as bg  # noqa: E402
import sign_geometry as sg  # noqa: E402

W, H = 1920, 1280
CAMERA = {"location": (0.0, -40.0, 1.6), "tilt": 100, "bearing": 10, "fov": 60, "shift_px": 0}
SECOND = {"location": (-15.0, -35.0, 1.6), "tilt": 98, "bearing": 25, "fov": 55, "shift_px": 0}
# A 6 m x 3 m sign on the wall y = 0 (facing -y), bottom-left corner at x = -2, z = 10.
TRUE = [(-2.0, 0.0, 13.0), (4.0, 0.0, 13.0), (4.0, 0.0, 10.0), (-2.0, 0.0, 10.0)]  # TL, TR, BR, BL


def px(camera, points):
    return [bg.project_point(camera, p, W, H) for p in points]


class RayTests(unittest.TestCase):
    def test_ray_plane_intersection(self):
        hit = sg.intersect_ray_plane((0, -10, 0), (0, 1, 0), (0, 0, 0), (0, -1, 0))
        self.assertEqual(tuple(round(c, 9) for c in hit), (0, 0, 0))
        self.assertIsNone(sg.intersect_ray_plane((0, -10, 0), (1, 0, 0), (0, 0, 0), (0, -1, 0)))
        self.assertIsNone(sg.intersect_ray_plane((0, -10, 0), (0, -1, 0), (0, 0, 0), (0, -1, 0)))  # behind

    def test_triangulate_two_rays(self):
        p = (3.0, 5.0, 7.0)
        rays = [((0, 0, 0), sg.unit(p)), ((10, 0, 0), sg.unit((p[0] - 10, p[1], p[2])))]
        self.assertTrue(all(abs(a - b) < 1e-9 for a, b in zip(sg.triangulate(rays), p)))

    def test_wall_plane_from_a_footprint_edge(self):
        point, normal = sg.wall_plane((-10, 0), (10, 0), toward=(0, -40))
        self.assertEqual(point, (-10, 0, 0.0))
        self.assertEqual(tuple(round(c, 9) for c in normal), (0, -1, 0))


class WallChoiceTests(unittest.TestCase):
    def test_picks_the_nearest_footprint_wall_hit_within_the_building_height(self):
        near = {"name": "near", "outline": [(-5, 0), (5, 0), (5, 10), (-5, 10)], "heightM": 20}
        far = {"name": "far", "outline": [(-20, 30), (20, 30), (20, 40), (-20, 40)], "heightM": 60}
        origin = (0.0, -40.0, 1.6)
        # Aimed at z = 10 on the near wall: chooses `near`, edge y = 0.
        wall = sg.choose_wall(origin, sg.unit((0, 40, 8.4)), [far, near])
        self.assertEqual(wall["building"], "near")
        self.assertEqual(tuple(round(c, 6) for c in wall["normal"]), (0, -1, 0))
        # Aimed above the near building (z = 30 at y = 0): passes over it and hits `far`.
        wall = sg.choose_wall(origin, sg.unit((0, 40, 28.4)), [far, near])
        self.assertEqual(wall["building"], "far")
        self.assertIsNone(sg.choose_wall(origin, sg.unit((1, 0, 0)), [far, near]))


class SignTests(unittest.TestCase):
    def test_sign_from_one_photo_on_a_known_wall(self):
        sign = sg.sign_from_photo(CAMERA, px(CAMERA, TRUE), W, H, wall=((0, 0, 0), (0, -1, 0)))
        for got, want in zip(sign["corners"], TRUE):
            self.assertTrue(all(abs(a - b) < 1e-6 for a, b in zip(got, want)), (got, want))
        self.assertAlmostEqual(sign["widthM"], 6.0, places=6)
        self.assertAlmostEqual(sign["heightM"], 3.0, places=6)
        self.assertLess(sign["reprojectionPx"], 1e-6)
        self.assertLess(sign["squarenessDeg"], 1e-6)
        box = sign["box"]
        self.assertEqual([round(c, 6) for c in box["center"]], [1.0, 0.0, 11.5])
        self.assertEqual([round(c, 6) for c in box["normal"]], [0, -1, 0])
        self.assertEqual([round(c, 6) for c in box["axisU"]], [1, 0, 0])

    def test_sign_from_two_photos_without_a_wall(self):
        sign = sg.sign_from_photos([(CAMERA, px(CAMERA, TRUE)), (SECOND, px(SECOND, TRUE))], W, H)
        for got, want in zip(sign["corners"], TRUE):
            self.assertTrue(all(abs(a - b) < 1e-6 for a, b in zip(got, want)))
        self.assertLess(sign["planarityM"], 1e-6)

    def test_a_wrong_wall_shows_up_as_a_bad_shape(self):
        # Tilting the assumed wall by 20 deg makes the recovered corners non-rectangular in 3D.
        n = (math.sin(math.radians(20)), -math.cos(math.radians(20)), 0)
        sign = sg.sign_from_photo(CAMERA, px(CAMERA, TRUE), W, H, wall=((0, 0, 0), n))
        self.assertGreater(abs(sign["widthM"] - 6.0), 0.1)


class RectanglePlaneTests(unittest.TestCase):
    # The same 6 x 3 m sign, but turned 35 deg away from the y = 0 wall, around its left edge.
    yaw = math.radians(35)
    ux, uy = math.cos(yaw), math.sin(yaw)
    TURNED = [(-2.0, 0.0, 13.0), (-2.0 + 6 * ux, 6 * uy, 13.0), (-2.0 + 6 * ux, 6 * uy, 10.0), (-2.0, 0.0, 10.0)]

    def test_plane_orientation_comes_from_the_quad_itself(self):
        axis_u, normal = sg.rectangle_plane(CAMERA, px(CAMERA, self.TURNED), W, H)
        self.assertAlmostEqual(axis_u[0], self.ux, places=6)
        self.assertAlmostEqual(axis_u[1], self.uy, places=6)
        self.assertAlmostEqual(axis_u[2], 0.0, places=9)
        self.assertAlmostEqual(normal[0] * self.ux + normal[1] * self.uy, 0.0, places=6)
        self.assertLess(normal[1], 0)  # faces the camera

    def test_sign_from_rectangle_only_needs_a_depth_anchor(self):
        # The anchor wall (y = 0) is wrong in orientation; only the depth where the centre ray meets it is used.
        anchor = ((0, 0, 0), (0, -1, 0))
        sign = sg.sign_from_rectangle(CAMERA, px(CAMERA, self.TURNED), W, H, anchor)
        self.assertAlmostEqual(sign["widthM"] / sign["heightM"], 2.0, places=4)
        self.assertLess(sign["squarenessDeg"], 1e-4)
        self.assertLess(sign["reprojectionPx"], 1e-6)


class RectifyTests(unittest.TestCase):
    def test_homography_maps_the_corners(self):
        src = [(100, 50), (400, 80), (390, 300), (90, 280)]
        coeffs = sg.perspective_coeffs(src, 300, 150)
        # PIL convention: output (x, y) -> input ((a x + b y + c) / (g x + h y + 1), ...)
        for (x, y), (u, v) in zip([(0, 0), (299, 0), (299, 149), (0, 149)], src):
            a, b, c, d, e, f, g, h = coeffs
            den = g * x + h * y + 1
            self.assertAlmostEqual((a * x + b * y + c) / den, u, places=6)
            self.assertAlmostEqual((d * x + e * y + f) / den, v, places=6)


if __name__ == "__main__":
    unittest.main()
