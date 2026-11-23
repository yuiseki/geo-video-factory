import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import facade_ortho as fo  # noqa: E402


def look_at(eye, target):
    """World-to-camera rotation and translation of a level camera (x right, y down, z forward)."""
    eye, target = np.asarray(eye, float), np.asarray(target, float)
    z = (target - eye) / np.linalg.norm(target - eye)
    x = np.cross(z, [0.0, 0.0, 1.0])
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.stack([x, y, z])
    return R, -R @ eye


def pattern(s, h):
    """A smooth colour that depends on where a point is on the wall (s along it, h above the ground)."""
    return np.stack([128 + 100 * np.sin(s * 1.3), 128 + 100 * np.cos(h * 1.7), 60 + 10.0 * s + 5.0 * h], -1)


def photograph(R, t, f, width, height, k=0.0):
    """Photo of the wall y = 0 (s = x, h = z), by casting a ray through every pixel centre."""
    v, u = np.mgrid[0:height, 0:width] + 0.5
    xd, yd = (u - width / 2) / f, (v - height / 2) / f
    x, y = xd.copy(), yd.copy()
    for _ in range(20):                                       # undo the radial distortion
        d = 1 + k * (x * x + y * y)
        x, y = xd / d, yd / d
    ray = np.stack([x, y, np.ones_like(x)], -1) @ R           # camera to world
    eye = -R.T @ t
    lam = -eye[1] / ray[..., 1]
    hit = eye + lam[..., None] * ray
    return np.clip(pattern(hit[..., 0], hit[..., 2]), 0, 255).astype(np.uint8)


class CurtainTests(unittest.TestCase):
    def test_texel_centres_run_along_the_line_and_down_from_the_top(self):
        pts, normals, s = fo.curtain([(0, 0), (10, 0)], z0=2.0, height=4.0, step=1.0)
        self.assertEqual(pts.shape, (4, 10, 3))
        np.testing.assert_allclose(s, np.arange(10) + 0.5)
        np.testing.assert_allclose(pts[0, :, 0], np.arange(10) + 0.5)
        np.testing.assert_allclose(pts[:, 3, 2], [5.5, 4.5, 3.5, 2.5])      # row 0 is the top
        np.testing.assert_allclose(pts[..., 1], 0.0)

    def test_the_outside_is_on_the_right_of_the_direction_of_travel(self):
        _, normals, _ = fo.curtain([(0, 0), (10, 0)], 0.0, 1.0, 1.0)
        np.testing.assert_allclose(normals, np.tile([0.0, -1.0], (10, 1)), atol=1e-12)

    def test_arc_length_continues_around_a_corner(self):
        pts, normals, s = fo.curtain([(0, 0), (3, 0), (3, 4)], 0.0, 1.0, 1.0)
        self.assertEqual(pts.shape[1], 7)
        np.testing.assert_allclose(pts[0, 4, :2], [3.0, 1.5])
        np.testing.assert_allclose(normals[4], [1.0, 0.0], atol=1e-12)

    def test_a_step_that_divides_the_length_keeps_every_texel(self):
        self.assertEqual(fo.curtain([(0, 0), (4, 0)], 0.0, 0.3, 0.1)[0].shape, (3, 40, 3))


class ProjectTests(unittest.TestCase):
    def test_the_point_on_the_axis_lands_on_the_principal_point(self):
        uv, depth = fo.project(np.array([[0.0, 0.0, 5.0]]), np.eye(3), np.zeros(3), 1000.0, 320.0, 240.0)
        np.testing.assert_allclose(uv, [[320.0, 240.0]])
        np.testing.assert_allclose(depth, [5.0])

    def test_simple_radial_distortion_follows_colmap(self):
        uv, _ = fo.project(np.array([[0.5, 0.0, 5.0]]), np.eye(3), np.zeros(3), 1000.0, 320.0, 240.0, k=0.2)
        np.testing.assert_allclose(uv, [[320.0 + 1000.0 * 0.1 * (1 + 0.2 * 0.01), 240.0]])

    def test_points_behind_the_camera_have_no_pixel(self):
        uv, depth = fo.project(np.array([[0.0, 0.0, -5.0]]), np.eye(3), np.zeros(3), 1000.0, 320.0, 240.0)
        self.assertTrue(np.isnan(uv).all())
        self.assertLess(depth[0], 0)

    def test_rotation_and_translation_are_world_to_camera(self):
        R, t = look_at((0, -10, 1.5), (0, 0, 1.5))
        uv, depth = fo.project(np.array([[1.0, 0.0, 2.5]]), R, t, 500.0, 100.0, 100.0)
        np.testing.assert_allclose(uv, [[150.0, 50.0]], atol=1e-9)             # east is right, up is up
        np.testing.assert_allclose(depth, [10.0])


class SampleTests(unittest.TestCase):
    def setUp(self):
        self.image = np.zeros((2, 3, 3), np.uint8)
        self.image[..., 0] = [[0, 100, 200], [40, 140, 240]]

    def test_a_pixel_centre_returns_the_pixel(self):
        colour, valid = fo.sample(self.image, np.array([[1.5, 0.5], [2.5, 1.5]]))
        np.testing.assert_allclose(colour[:, 0], [100, 240])
        self.assertTrue(valid.all())

    def test_between_centres_is_the_bilinear_mix(self):
        colour, _ = fo.sample(self.image, np.array([[1.0, 1.0]]))
        np.testing.assert_allclose(colour[0, 0], (0 + 100 + 40 + 140) / 4)

    def test_outside_the_centres_and_nan_are_invalid(self):
        _, valid = fo.sample(self.image, np.array([[0.2, 0.5], [1.5, 1.8], [np.nan, 0.5], [1.5, 1.0]]))
        self.assertEqual(valid.tolist(), [False, False, False, True])


class OrthoViewTests(unittest.TestCase):
    F, W, H = 800.0, 640, 480

    def ortho(self, eye, target, k=0.0, **more):
        R, t = look_at(eye, target)
        photo = photograph(R, t, self.F, self.W, self.H, k)
        pts, normals, s = fo.curtain([(0, 0), (4, 0)], 0.0, 3.0, 0.05)
        colour, valid, score = fo.ortho_view(photo, pts, normals, R, t, self.F, self.W / 2, self.H / 2, k, **more)
        truth = pattern(pts[..., 0], pts[..., 2])
        return colour, valid, score, truth

    def test_a_frontal_photo_gives_back_the_wall(self):
        colour, valid, _, truth = self.ortho((2, -6, 1.5), (2, 0, 1.5))
        self.assertGreater(valid.mean(), 0.99)
        self.assertLess(np.abs(colour[valid].astype(float) - truth[valid]).max(), 4.0)

    def test_an_oblique_photo_with_lens_distortion_gives_back_the_same_wall(self):
        colour, valid, _, truth = self.ortho((-1.5, -5, 1.2), (2, 0, 1.6), k=0.08)
        self.assertGreater(valid.mean(), 0.9)
        self.assertLess(np.abs(colour[valid].astype(float) - truth[valid]).max(), 5.0)

    def test_a_camera_behind_the_wall_sees_nothing(self):
        _, valid, score, _ = self.ortho((2, 6, 1.5), (2, 0, 1.5))
        self.assertFalse(valid.any())
        self.assertEqual(score.max(), 0.0)

    def test_score_is_pixels_per_metre_and_drops_with_distance_and_slant(self):
        near = self.ortho((2, -6, 1.5), (2, 0, 1.5))[2]
        far = self.ortho((2, -12, 1.5), (2, 0, 1.5))[2]
        slant = self.ortho((-4, -6, 1.5), (2, 0, 1.5))[2]
        centre = (near.shape[0] // 2, near.shape[1] // 2)
        self.assertAlmostEqual(float(near[centre]), self.F / 6.0, delta=1.5)
        self.assertAlmostEqual(float(far[centre]), self.F / 12.0, delta=1.0)
        self.assertLess(slant[centre], near[centre] * 0.6)

    def test_grazing_views_are_dropped(self):
        _, valid, _, _ = self.ortho((-9, -1, 1.5), (2, 0, 1.5), min_cos=0.2)
        self.assertFalse(valid.any())


class FuseTests(unittest.TestCase):
    def test_median_drops_what_only_one_view_saw(self):
        stack = np.full((3, 2, 2, 3), 100, np.uint8)
        stack[1, 0, 0] = 250                                    # a passer-by in one view
        valid = np.ones((3, 2, 2), bool)
        out, count = fo.fuse_median(stack, valid)
        np.testing.assert_array_equal(out, np.full((2, 2, 3), 100, np.uint8))
        np.testing.assert_array_equal(count, np.full((2, 2), 3))

    def test_median_ignores_invalid_views_and_leaves_unseen_texels_black(self):
        stack = np.zeros((3, 1, 2, 3), np.uint8)
        stack[0], stack[1], stack[2] = 10, 200, 90
        valid = np.array([[[True, False]], [[False, False]], [[True, False]]])
        out, count = fo.fuse_median(stack, valid, rows=1)
        self.assertEqual(out[0, 0].tolist(), [50, 50, 50])
        self.assertEqual(out[0, 1].tolist(), [0, 0, 0])
        self.assertEqual(count.tolist(), [[2, 0]])

    def test_best_takes_each_texel_from_its_highest_scoring_view(self):
        stack = np.zeros((2, 1, 2, 3), np.uint8)
        stack[0], stack[1] = 10, 20
        score = np.array([[[5.0, 0.0]], [[1.0, 2.0]]], np.float32)
        out, which = fo.fuse_best(stack, score)
        self.assertEqual(out[0, :, 0].tolist(), [10, 20])
        self.assertEqual(which.tolist(), [[0, 1]])

    def test_best_marks_texels_no_view_scored(self):
        out, which = fo.fuse_best(np.full((2, 1, 1, 3), 9, np.uint8), np.zeros((2, 1, 1), np.float32))
        self.assertEqual((out.tolist(), which.tolist()), ([[[0, 0, 0]]], [[-1]]))


class FitCurtainTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(1)
        x = rng.uniform(0, 30, 4000)
        self.wall = np.c_[x, -1.2 + rng.normal(0, 0.05, x.size)]          # the real wall is 1.2 m outside
        self.guide = [(-10, 0), (40, 0)]

    def test_the_guide_moves_onto_the_points(self):
        line, offset, count = fo.fit_curtain(self.guide, self.wall, step=0.5)
        seen = count >= 10
        self.assertGreater(seen.sum(), 50)
        np.testing.assert_allclose(offset[seen], 1.2, atol=0.05)
        np.testing.assert_allclose(line[seen, 1], -1.2, atol=0.05)

    def test_stray_points_do_not_pull_the_line(self):
        stray = np.c_[np.linspace(0, 30, 300), np.full(300, -3.5)]         # a canopy in front of the wall
        _, offset, count = fo.fit_curtain(self.guide, np.vstack([self.wall, stray]), step=0.5)
        np.testing.assert_allclose(offset[count >= 10], 1.2, atol=0.08)

    def test_covered_run_is_the_longest_stretch_with_points(self):
        _, _, count = fo.fit_curtain(self.guide, self.wall, step=0.5)
        i0, i1 = fo.covered_run(count, min_points=10, max_gap=4)
        self.assertAlmostEqual((i0 + 0.5) * 0.5 - 10, 0.0, delta=1.5)
        self.assertAlmostEqual((i1 + 0.5) * 0.5 - 10, 30.0, delta=1.5)

    def test_covered_run_bridges_short_gaps_only(self):
        count = np.array([0, 20, 20, 0, 20, 20, 20, 0, 0, 0, 0, 20, 0])
        self.assertEqual(fo.covered_run(count, min_points=10, max_gap=2), (1, 6))
        self.assertEqual(fo.covered_run(np.zeros(5, int), min_points=10, max_gap=2), (0, 0))


class ReliefTests(unittest.TestCase):
    """A wall whose lower 10 m stands 1 m outside the guide and whose upper 10 m is set back by 2 m."""

    def setUp(self):
        rng = np.random.default_rng(2)
        x, z = rng.uniform(0, 40, 20000), rng.uniform(0, 20, 20000)
        y = np.where(z < 10, -1.0, 2.0) + rng.normal(0, 0.03, x.size)
        self.points = np.c_[x, y, z]
        self.guide = [(0, 0), (40, 0)]

    def test_each_cell_takes_the_median_distance_of_its_points(self):
        relief, count = fo.fit_relief(self.guide, self.points, z0=0.0, height=20.0, cell_s=4.0, cell_z=5.0, smooth=0)
        self.assertEqual(relief.shape, (4, 10))
        np.testing.assert_allclose(relief[:2], -2.0, atol=0.05)             # row 0 is the top
        np.testing.assert_allclose(relief[2:], 1.0, atol=0.05)
        self.assertGreater(count.min(), 100)

    def test_cells_without_points_take_their_neighbours(self):
        hole = (self.points[:, 0] > 16) & (self.points[:, 0] < 24) & (self.points[:, 2] < 5)
        relief, count = fo.fit_relief(self.guide, self.points[~hole], 0.0, 20.0, 4.0, 5.0, smooth=0)
        self.assertEqual(count[3, 4:6].tolist(), [0, 0])
        np.testing.assert_allclose(relief[3, 4:6], 1.0, atol=0.05)

    def test_no_points_at_all_leaves_the_wall_where_it_was(self):
        relief, count = fo.fit_relief(self.guide, np.zeros((0, 3)), 0.0, 20.0, 4.0, 5.0)
        self.assertEqual((float(np.abs(relief).max()), int(count.sum())), (0.0, 0))

    def test_apply_moves_texels_along_the_normal(self):
        pts, normals, s = fo.curtain(self.guide, 0.0, 20.0, 0.5)
        relief, _ = fo.fit_relief(self.guide, self.points, 0.0, 20.0, 4.0, 5.0, smooth=0)
        moved = fo.apply_relief(pts, normals, relief, cell_s=4.0, cell_z=5.0, step=0.5)
        np.testing.assert_allclose(moved[..., [0, 2]], pts[..., [0, 2]])
        np.testing.assert_allclose(moved[-4, :, 1], -1.0, atol=0.05)        # near the ground: 1 m outside
        np.testing.assert_allclose(moved[3, :, 1], 2.0, atol=0.05)          # near the top: set back
        middle = moved[20, :, 1]                                            # the step is blended, not torn
        self.assertTrue(((middle > -1.0) & (middle < 2.0)).all())


if __name__ == "__main__":
    unittest.main()
