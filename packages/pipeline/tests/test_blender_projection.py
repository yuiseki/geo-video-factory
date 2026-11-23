import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import blender_geo as bg  # noqa: E402

W, H = 1280, 720


class ProjectionTests(unittest.TestCase):
    def test_point_straight_ahead_lands_on_the_image_center(self):
        camera = {"location": (0, 0, 1.6), "tilt": 90, "bearing": 30, "fov": 60, "shift_px": 0}
        b = math.radians(30)
        u, v = bg.project_point(camera, (math.sin(b) * 50, math.cos(b) * 50, 1.6), W, H)
        self.assertAlmostEqual(u, W / 2, places=6)
        self.assertAlmostEqual(v, H / 2, places=6)

    def test_right_is_right_up_is_up_and_shift_moves_the_frame(self):
        camera = {"location": (0, 0, 1.6), "tilt": 90, "bearing": 0, "fov": 60, "shift_px": 0}
        u, v = bg.project_point(camera, (5, 50, 1.6 + 5), W, H)
        f = (H / 2) / math.tan(math.radians(30))
        self.assertAlmostEqual(u, W / 2 + f * 5 / 50, places=6)
        self.assertAlmostEqual(v, H / 2 - f * 5 / 50, places=6)
        shifted = dict(camera, shift_px=100)
        self.assertAlmostEqual(bg.project_point(shifted, (5, 50, 6.6), W, H)[1], v + 100, places=6)

    def test_matches_the_maplibre_camera_of_a_shot_key(self):
        cam = bg.maplibre_camera(center=[139.70, 35.66], zoom=20, pitch=70, bearing=-40,
                                 fov=50, height_px=H, origin=[139.70, 35.66])
        camera = {"location": cam["location"], "tilt": 70, "bearing": -40, "fov": 50, "shift_px": 0}
        u, v = bg.project_point(camera, (0, 0, 0), W, H)
        self.assertAlmostEqual(u, W / 2, places=6)
        self.assertAlmostEqual(v, H / 2, places=6)

    def test_eye_camera_places_a_blender_camera_at_eye_height(self):
        cam = bg.eye_camera(eye=[139.701, 35.661, 1.6], bearing=-45, tilt=92, fov=58, origin=[139.700, 35.660])
        x, y = bg.local_meters([139.701, 35.661], [139.700, 35.660])
        self.assertEqual(cam["location"], (x, y, 1.6))
        self.assertAlmostEqual(cam["rotation_euler"][0], math.radians(92))
        self.assertAlmostEqual(cam["rotation_euler"][2], math.radians(45))
        self.assertAlmostEqual(cam["fov_vertical"], math.radians(58))

    def test_pixel_ray_is_the_inverse_of_projection(self):
        camera = {"location": (3.0, -4.0, 1.6), "tilt": 95, "bearing": -35, "fov": 68, "shift_px": 40}
        point = (-12.0, 30.0, 18.0)
        u, v = bg.project_point(camera, point, W, H)
        origin, direction = bg.pixel_ray(camera, u, v, W, H)
        self.assertEqual(origin, camera["location"])
        to_point = [point[i] - origin[i] for i in range(3)]
        length = math.sqrt(sum(c * c for c in to_point))
        for i in range(3):
            self.assertAlmostEqual(direction[i], to_point[i] / length, places=9)


class RollTests(unittest.TestCase):
    def test_roll_turns_the_image_around_its_centre(self):
        base = {"location": (0, 0, 1.6), "tilt": 90, "bearing": 0, "fov": 60, "shift_px": 0}
        rolled = dict(base, roll=90)
        point = (5, 50, 1.6)  # to the right of the view centre
        u0, v0 = bg.project_point(base, point, W, H)
        u1, v1 = bg.project_point(rolled, point, W, H)
        self.assertAlmostEqual(v0, H / 2, places=6)
        self.assertAlmostEqual(u1, W / 2, places=6)  # with the camera rolled 90 deg it is straight above/below
        self.assertAlmostEqual(abs(v1 - H / 2), u0 - W / 2, places=6)
        self.assertAlmostEqual(bg.project_point(rolled, (0, 50, 1.6), W, H)[0], W / 2, places=6)

    def test_pixel_ray_inverts_projection_with_roll(self):
        camera = {"location": (3.0, -4.0, 1.6), "tilt": 103, "bearing": -25, "fov": 64, "shift_px": 0, "roll": 4.0}
        point = (-12.0, 30.0, 18.0)
        u, v = bg.project_point(camera, point, W, H)
        origin, direction = bg.pixel_ray(camera, u, v, W, H)
        to_point = [point[i] - origin[i] for i in range(3)]
        n = math.sqrt(sum(c * c for c in to_point))
        for i in range(3):
            self.assertAlmostEqual(direction[i], to_point[i] / n, places=9)

    def test_rotation_columns_are_blender_camera_axes(self):
        right, up, back = bg.camera_rotation_columns(tilt=90, bearing=0, roll=0)
        self.assertEqual([round(c, 9) for c in right], [1, 0, 0])
        self.assertEqual([round(c, 9) for c in up], [0, 0, 1])
        self.assertEqual([round(c, 9) for c in back], [0, -1, 0])  # Blender cameras look down local -Z


class SignBoxTests(unittest.TestCase):
    def test_box_from_four_wall_points(self):
        # A 6 m x 3 m sign on a wall facing south (normal -Y), bottom at 10 m.
        corners = [(-3, 20, 13), (3, 20, 13), (-3, 20, 10), (3, 20, 10)]  # TL, TR, BL, BR
        box = bg.sign_box(corners, camera_location=(0, 0, 1.6), depth=1.0)
        self.assertEqual([round(c, 6) for c in box["center"]], [0, 20, 11.5])
        self.assertAlmostEqual(box["halfWidth"], 3)
        self.assertAlmostEqual(box["halfHeight"], 1.5)
        self.assertAlmostEqual(box["halfDepth"], 1.0)
        self.assertEqual([round(c, 6) for c in box["axisU"]], [1, 0, 0])
        self.assertEqual([round(c, 6) for c in box["normal"]], [0, -1, 0])  # toward the camera
        self.assertTrue(bg.inside_sign_box(box, (2.9, 20.5, 12.9)))
        self.assertFalse(bg.inside_sign_box(box, (3.2, 20, 12)))
        self.assertFalse(bg.inside_sign_box(box, (0, 21.5, 12)))

    def test_wall_extent_corners_span_the_sampled_points(self):
        points = [(x, 20.0, z) for x in (-3, -1, 1, 3) for z in (10, 11.5, 13)]
        tl, tr, bl, br = bg.wall_extent_corners(points, normal=(0, -1, 0))
        box = bg.sign_box([tl, tr, bl, br], camera_location=(0, 0, 1.6), depth=1.0)
        self.assertEqual([round(c, 6) for c in box["center"]], [0, 20, 11.5])
        self.assertAlmostEqual(box["halfWidth"], 3)
        self.assertAlmostEqual(box["halfHeight"], 1.5)


class BandTests(unittest.TestCase):
    def test_vertex_arcs_accumulate_edge_lengths(self):
        square = [(0, 0), (10, 0), (10, 10), (0, 10)]
        self.assertEqual(bg.outline_vertex_arcs(square), [0, 10, 20, 30])

    def test_band_on_one_edge_of_a_counter_clockwise_outline(self):
        square = [(0, 0), (10, 0), (10, 10), (0, 10)]  # CCW; the y=0 edge faces -y
        band = bg.outline_band(square, s0=2, s1=8, offset=0.5)
        xs = [p[0] for p, _u in band]
        self.assertAlmostEqual(xs[0], 2)
        self.assertAlmostEqual(xs[-1], 8)
        for (x, y), _u in band:
            self.assertAlmostEqual(y, -0.5)  # pushed outward
        # A viewer outside (y < 0) looking at the wall sees u grow to the right (+x).
        self.assertAlmostEqual(band[0][1], 0)
        self.assertAlmostEqual(band[-1][1], 1)

    def test_band_reverses_u_on_a_clockwise_outline_and_wraps_corners(self):
        square_cw = [(0, 0), (0, 10), (10, 10), (10, 0)]  # CW
        band = bg.outline_band(square_cw, s0=25, s1=35, offset=0.0)  # crosses the (10,0) corner
        points = [p for p, _u in band]
        self.assertIn((10.0, 0.0), [(round(x, 6), round(y, 6)) for x, y in points])
        # On the -y face (from (10,0) toward (0,0)) a viewer outside sees +x on the right, so u falls along the arc.
        self.assertAlmostEqual(band[0][1], 1)
        self.assertAlmostEqual(band[-1][1], 0)


class CrosswalkTests(unittest.TestCase):
    def test_bars_cross_the_walking_line_and_repeat_along_it(self):
        # Japanese zebra: pedestrians step over each bar, so bars span the width across the walking line.
        stripes = bg.crosswalk_stripes((0, 0), (20, 0), width=4.0, stripe=0.45, gap=0.45, trim=1.0)
        self.assertEqual(len(stripes), 20)  # floor((18 + 0.45) / 0.9) = 20
        for quad in stripes:
            xs = sorted(p[0] for p in quad)
            ys = sorted(p[1] for p in quad)
            self.assertAlmostEqual(xs[-1] - xs[0], 0.45)
            self.assertAlmostEqual(ys[0], -2.0)
            self.assertAlmostEqual(ys[-1], 2.0)
        centers = sorted(sum(p[0] for p in q) / 4 for q in stripes)
        self.assertAlmostEqual((centers[0] + centers[-1]) / 2, 10.0)  # centred between the curbs
        self.assertAlmostEqual(centers[1] - centers[0], 0.9)

    def test_bars_follow_a_diagonal(self):
        stripes = bg.crosswalk_stripes((0, 0), (10, 10), width=6.0, stripe=0.45, gap=0.45, trim=0.0)
        quad = stripes[0]
        self.assertAlmostEqual(math.dist(quad[0], quad[1]), 0.45, places=6)
        self.assertAlmostEqual(math.dist(quad[1], quad[2]), 6.0, places=6)


class OutlineTests(unittest.TestCase):
    def test_smooth_outline_passes_through_the_original_vertices(self):
        square = [(0, 0), (10, 0), (10, 10), (0, 10)]
        smooth = bg.smooth_closed_outline(square, samples_per_edge=4)
        self.assertEqual(len(smooth), 16)
        for i, p in enumerate(square):
            self.assertAlmostEqual(smooth[i * 4][0], p[0])
            self.assertAlmostEqual(smooth[i * 4][1], p[1])
        # Between corners the curve bulges outward (Catmull-Rom), so the edge midpoint is outside the square.
        mid = smooth[2]
        self.assertLess(mid[1], 0)

    def test_smooth_outline_keeps_marked_corners_sharp(self):
        square = [(0, 0), (10, 0), (10, 10), (0, 10)]
        smooth = bg.smooth_closed_outline(square, samples_per_edge=4, sharp={0, 1, 2, 3})
        self.assertAlmostEqual(smooth[2][1], 0)  # straight edge when both ends are sharp
        self.assertAlmostEqual(smooth[2][0], 5)

    def test_point_in_polygon(self):
        square = [(0, 0), (10, 0), (10, 10), (0, 10)]
        self.assertTrue(bg.point_in_polygon((5, 5), square))
        self.assertFalse(bg.point_in_polygon((11, 5), square))
        self.assertTrue(bg.point_in_polygon((10.5, 5), square, margin=1.0))


if __name__ == "__main__":
    unittest.main()
