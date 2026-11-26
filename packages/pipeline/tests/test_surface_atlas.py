import unittest

import numpy as np

from world_model import surface_atlas as sa


def wall(x0, x1, z0, z1, y):
    """A wall in the plane north = y, facing south (outward normal -y)."""
    a, b, c, d = [x0, y, z0], [x1, y, z0], [x1, y, z1], [x0, y, z1]
    return np.array([[a, b, c], [a, c, d]], float)


def camera(eye, width=400, height=300, f=300.0):
    """Looking north, level."""
    return {"eye": list(eye), "Rw": [[1, 0, 0], [0, 0, -1], [0, 1, 0]], "width": width, "height": height,
            "params": [f, f, width / 2, height / 2]}


class SurfaceAtlasTest(unittest.TestCase):
    def test_wall_normal_faces_south_and_chart_reads_left_to_right(self):
        tris = wall(0, 10, 0, 5, 20)
        groups = sa.planar_faces(tris)
        self.assertEqual(len(groups), 1)
        points, mask, normal, corners = sa.chart(tris, 0.5, pad=0)
        np.testing.assert_allclose(normal, [0, -1, 0], atol=1e-9)
        self.assertEqual(points.shape[:2], (10, 20))
        self.assertTrue(mask.all())
        np.testing.assert_allclose(points[0, 0], [0.25, 20, 4.75])    # top row, and west is on the left from outside
        np.testing.assert_allclose(points[-1, -1], [9.75, 20, 0.25])
        self.assertAlmostEqual(corners[..., 0].max(), 20)
        self.assertAlmostEqual(corners[..., 1].max(), 10)

    def test_two_planes_are_two_faces(self):
        tris = np.concatenate([wall(0, 10, 0, 5, 20), wall(0, 10, 0, 5, 21)])
        self.assertEqual(len(sa.planar_faces(tris)), 2)

    def test_depth_buffer_keeps_the_nearer_wall(self):
        cam = camera([5, 0, 2])
        depth = sa.depth_buffer(np.concatenate([wall(0, 10, 0, 5, 30), wall(4, 6, 0, 5, 10)]), cam, scale=1.0)
        self.assertAlmostEqual(float(depth[150, 200]), 10, places=3)
        self.assertAlmostEqual(float(depth[150, 160]), 30, places=3)
        self.assertTrue(np.isinf(depth[5, 200]))

    def test_triangle_crossing_the_camera_plane_still_occludes(self):
        cam = camera([5, 0, 2])
        ground = np.array([[[-50, -50, 0], [50, -50, 0], [50, 50, 0]], [[-50, -50, 0], [50, 50, 0], [-50, 50, 0]]], float)
        depth = sa.depth_buffer(ground, cam, scale=1.0)
        self.assertTrue(np.isfinite(depth[290, 200]))
        self.assertTrue(np.isinf(depth[100, 200]))

    def test_observe_reads_the_photo_and_drops_hidden_texels(self):
        cam = camera([5, 0, 2])
        back, front = wall(0, 10, 0, 5, 30), wall(4, 6, 0, 5, 10)
        depth = sa.depth_buffer(np.concatenate([back, front]), cam, scale=1.0)
        image = np.zeros((300, 400, 3), np.uint8)
        image[:, :200] = (200, 0, 0)
        image[:, 200:] = (0, 0, 200)
        points, mask, normal, _ = sa.chart(back, 0.5, pad=0)
        colour, weight = sa.observe(image, points, normal, cam, depth, scale=1.0)
        self.assertGreater(weight[5, 2], 0)
        np.testing.assert_allclose(colour[5, 2], [200, 0, 0], atol=1)
        np.testing.assert_allclose(colour[5, 17], [0, 0, 200], atol=1)
        self.assertEqual(weight[5, 10], 0)                               # behind the front wall
        turned, _ = sa.observe(image, points, -normal, cam, depth, scale=1.0)[1], None
        self.assertEqual(turned.max(), 0)

    def test_fuse_takes_the_median_and_falls_back_to_the_sharpest(self):
        colours = np.array([[[10.0] * 3, [50.0] * 3, [1.0] * 3], [[20.0] * 3, [60.0] * 3, [2.0] * 3],
                            [[90.0] * 3, [70.0] * 3, [3.0] * 3]])
        weights = np.array([[1.0, 1.0, 0.0], [1.0, 5.0, 0.0], [1.0, 0.0, 0.0]])
        out, count = sa.fuse(colours, weights, few=3)
        self.assertEqual(count.tolist(), [3, 2, 0])
        np.testing.assert_allclose(out[0], [20] * 3)
        np.testing.assert_allclose(out[1], [60] * 3)
        self.assertTrue(np.isnan(out[2]).all())

    def test_topk_keeps_the_heaviest_views_per_texel(self):
        stack = sa.TopK(3, 2)
        for v, w in enumerate([[1, 0, 5], [3, 0, 1], [2, 0, 9], [0.5, 0, 0]]):
            stack.add(np.full((3, 3), 10.0 * (v + 1)), np.array(w, float))
        colours, weights = stack.arrays()
        self.assertEqual(sorted(weights[:, 0].tolist()), [2.0, 3.0])
        self.assertEqual(sorted(colours[:, 0, 0].tolist()), [20.0, 30.0])
        self.assertEqual(sorted(weights[:, 2].tolist()), [5.0, 9.0])
        self.assertEqual(weights[:, 1].tolist(), [0.0, 0.0])
        self.assertEqual(stack.count.tolist(), [4, 0, 3])

    def test_observe_follows_radial_distortion(self):
        cam = {"eye": [0.0, 0.0, 0.0], "Rw": [[1, 0, 0], [0, 0, -1], [0, 1, 0]], "params": [100.0, 100.0, 100.0, 100.0],
               "width": 200, "height": 200, "distortion": [0.5]}
        image = np.zeros((200, 200, 3), np.uint8)
        image[:, :, 0] = np.arange(200)[None, :]            # red = column
        depth = np.full((50, 50), np.inf)
        point = np.array([[4.0, 10.0, 0.0]])                 # x/z = 0.4 -> 0.4 * (1 + 0.5 * 0.16) = 0.432
        colour, weight = sa.observe(image, point, np.array([0.0, -1.0, 0.0]), cam, depth)
        self.assertGreater(weight[0], 0)
        self.assertAlmostEqual(float(colour[0, 0]), 143.2, delta=0.6)

    def test_c_depth_buffer_matches_the_numpy_one(self):
        rng = np.random.default_rng(3)
        base = rng.uniform([-30, 5, -10], [30, 80, 30], (400, 1, 3))
        tris = base + rng.uniform(-6, 6, (400, 3, 3))
        cam = {"eye": [0.0, 0.0, 0.0], "Rw": [[1, 0, 0], [0, 0, -1], [0, 1, 0]], "params": [300.0, 300.0, 320.0, 240.0],
               "width": 640, "height": 480}
        slow = sa.depth_buffer(tris, cam, slow=True)
        fast = sa.depth_buffer(tris, cam)
        self.assertTrue(np.isfinite(slow).mean() > 0.3)
        np.testing.assert_array_equal(np.isfinite(slow), np.isfinite(fast))
        np.testing.assert_allclose(fast[np.isfinite(fast)], slow[np.isfinite(slow)], rtol=1e-5)

    def test_fuse_by_face_takes_one_photo_per_face_and_fills_its_gaps(self):
        # texels 0-3 are face 0, texels 4-5 face 1. View 0 covers all of face 0 moderately, view 1 a part sharply.
        face_of = np.array([0, 0, 0, 0, 1, 1])
        stack = sa.TopK(6, 3)
        stack.add(np.full((6, 3), 10.0), np.array([300, 300, 300, 0, 0, 50.0]), view=0)
        stack.add(np.full((6, 3), 20.0), np.array([900, 0, 0, 100, 60, 0.0]), view=1)
        colours, weights, views = stack.arrays(views=True)
        out, chosen = sa.fuse_by_face(colours, weights, views, face_of, cap=400.0)
        # face 0: view 0 scores 900, view 1 scores 400 + 100 -> view 0 wins where it saw, view 1 fills texel 3
        self.assertEqual(out[:, 0].tolist(), [10.0, 10.0, 10.0, 20.0, 20.0, 10.0])
        self.assertEqual(chosen.tolist(), [0, 0, 0, 1, 1, 0])

    def test_fuse_by_face_leaves_unseen_texels_empty(self):
        stack = sa.TopK(2, 2)
        stack.add(np.full((2, 3), 5.0), np.array([1.0, 0.0]), view=3)
        out, chosen = sa.fuse_by_face(*stack.arrays(views=True), np.array([0, 0]))
        self.assertTrue(np.isnan(out[1]).all())
        self.assertEqual(chosen.tolist(), [3, -1])

    def test_pack_does_not_overlap(self):
        sizes = [(10, 30), (20, 30), (5, 50), (8, 8)]
        pos, rows = sa.pack(sizes, width=64, gap=1)
        canvas = np.zeros((rows, 64), int)
        for (r, c), (y, x) in zip(sizes, pos):
            canvas[y:y + r, x:x + c] += 1
        self.assertEqual(canvas.max(), 1)


class Agreement(unittest.TestCase):
    def test_the_photo_the_others_contradict_loses_its_patch(self):
        # four photos see four texels of one patch; photo 0 is the sharpest but has a passer-by in front
        colours = np.zeros((4, 4, 3), np.float32)
        colours[0] = 20.0
        colours[1:] = 200.0
        weights = np.array([[9.0] * 4, [5.0] * 4, [4.0] * 4, [3.0] * 4], np.float32)
        views = np.repeat(np.arange(4)[:, None], 4, axis=1).astype(np.int16)
        patch = np.zeros(4, int)
        plain, took = sa.fuse_by_face(colours, weights, views, patch)
        self.assertTrue((took == 0).all())
        voted, took = sa.fuse_by_face(colours, weights, views, patch, agree=20.0)
        self.assertTrue((took == 1).all())
        np.testing.assert_allclose(voted, 200.0)


class Smoothing(unittest.TestCase):
    def test_a_slightly_better_view_gives_way_to_the_neighbours(self):
        # three patches in a row; the middle one marginally prefers view 1, its neighbours clearly view 0
        score = np.array([[10.0, 1.0], [9.0, 10.0], [10.0, 1.0]])
        pairs = [(0, 1), (1, 2)]
        self.assertEqual(sa.smooth_labels(score, pairs, strength=0.0).tolist(), [0, 1, 0])
        self.assertEqual(sa.smooth_labels(score, pairs, strength=0.7).tolist(), [0, 0, 0])

    def test_a_view_that_did_not_see_the_patch_is_never_taken(self):
        score = np.array([[10.0, 0.0], [0.0, 3.0], [10.0, 0.0]])
        self.assertEqual(sa.smooth_labels(score, [(0, 1), (1, 2)], strength=5.0).tolist(), [0, 1, 0])


class Exposure(unittest.TestCase):
    def test_gain_brings_a_dim_photo_to_the_others_and_is_limited(self):
        colours = np.full((5, 50, 3), 100.0, np.float32)
        colours[0] = 80.0      # a little dim
        colours[3] = 10.0      # a night photo: not to be rescued
        weights = np.ones((5, 50), np.float32)
        views = np.repeat(np.arange(5)[:, None], 50, axis=1).astype(np.int16)
        g = sa.exposure_gains(colours, weights, views)
        self.assertAlmostEqual(g[0], 1.25, places=2)
        self.assertAlmostEqual(g[1], 1.0, places=2)
        self.assertAlmostEqual(g[3], 1.6, places=2)


class ChangingSurface(unittest.TestCase):
    def test_a_screen_takes_one_moment(self):
        # two neighbouring patches of a screen, three photos showing three different pictures; photo 0 saw
        # patch A a little better, photo 1 saw patch B a little better
        n = 40
        face_of = np.repeat([0, 1], n // 2)
        colours = np.stack([np.full((n, 3), v, np.float32) for v in (20.0, 120.0, 230.0)])
        weights = np.ones((3, n), np.float32)
        weights[0, : n // 2] = 1.3
        weights[1, n // 2:] = 1.3
        views = np.repeat(np.arange(3)[:, None], n, axis=1)
        pairs = np.array([[0, 1]])
        _, plain = sa.fuse_by_face(colours, weights, views, face_of, cap=10.0, pairs=pairs, strength=0.1)
        self.assertEqual(len(set(plain.tolist())), 2)
        _, held = sa.fuse_by_face(colours, weights, views, face_of, cap=10.0, agree=25.0, pairs=pairs, strength=0.1,
                                  changing=30.0)
        self.assertEqual(len(set(held.tolist())), 1)


class Eras(unittest.TestCase):
    def test_two_eras_of_a_facade(self):
        # five photos of one wall: three after a refit (light), two before (dark); a small screen differs in all
        rng = np.random.default_rng(0)
        n = 2000
        base = [200.0, 205.0, 195.0, 60.0, 65.0]
        colours = np.stack([np.full((n, 3), b, np.float32) for b in base])
        colours[:, :200] = rng.uniform(0, 255, (5, 200, 3))
        weights = np.ones((5, n), np.float32)
        views = np.repeat(np.arange(5)[:, None], n, axis=1)
        share, pairs = sa.view_agreement(colours, weights, views)
        self.assertGreater(share[0, 1], 0.85)
        self.assertLess(share[0, 3], 0.1)
        self.assertEqual(sa.view_clusters(share, pairs, k=2).tolist(), [0, 0, 0, 1, 1])


if __name__ == "__main__":
    unittest.main()


class TexelQuality(unittest.TestCase):
    """quality.png: how well the best photo saw each texel, as photo pixels across one texel (0..1)."""

    def test_a_texel_seen_at_a_pixel_or_more_per_texel_is_fully_trusted(self):
        from world_model import surface_atlas as sa
        texel = 0.05
        w = np.array([[(1 / texel) ** 2 * 4, 0.0], [(1 / texel) ** 2, 0.0]])     # 2 px and 1 px per texel side
        np.testing.assert_allclose(sa.texel_quality(w, texel), [1.0, 1.0])

    def test_a_grazing_or_distant_view_fades_and_an_unseen_texel_is_zero(self):
        from world_model import surface_atlas as sa
        texel = 0.05
        w = np.array([[(0.25 / texel) ** 2, (0.1 / texel) ** 2], [0.0, 0.0]])    # the best is a quarter pixel
        q = sa.texel_quality(w, texel)
        self.assertAlmostEqual(float(q[0]), 0.25, places=6)
        self.assertEqual(float(q[1]), 0.0)
