import unittest

import numpy as np
from scipy.spatial.transform import Rotation

from world_model import sim3
def box_room(size=(60.0, 40.0, 30.0)):
    """Four walls and a floor as triangles, looking inward."""
    x, y, z = size
    c = np.array([[0, 0, 0], [x, 0, 0], [x, y, 0], [0, y, 0], [0, 0, z], [x, 0, z], [x, y, z], [0, y, z]], float)
    quads = [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (0, 3, 2, 1)]
    return np.array([[c[a], c[b], c[d]] for a, b, d, _ in quads] + [[c[b], c[d2], c[d]] for _, b, d2, d in
                                                                    [(q[0], q[1], q[2], q[3]) for q in quads]])


class Sim3Test(unittest.TestCase):
    def setUp(self):
        self.A = Rotation.from_euler("zyx", [40, 5, -3], degrees=True).as_matrix()
        self.s, self.t = 7.5, np.array([12.0, -30.0, 52.0])
        self.sim = (self.s, self.A, self.t)

    def cam_pair(self, eye, yaw):
        Rw = Rotation.from_euler("z", yaw, degrees=True).as_matrix()
        Cs = self.A.T @ (np.array(eye) - self.t) / self.s
        return (Rw @ self.A, Cs), (Rw, np.array(eye, float))

    def test_camera_roundtrip(self):
        (Rs, Cs), (Rw, eye) = self.cam_pair([3.0, 4.0, 54.0], 30)
        R2, e2 = sim3.camera(self.sim, Rs, Cs)
        np.testing.assert_allclose(R2, Rw, atol=1e-9)
        np.testing.assert_allclose(e2, eye, atol=1e-9)

    def test_from_two_anchors_recovers_similarity(self):
        pairs = [self.cam_pair([3.0, 4.0, 54.0], 30), self.cam_pair([40.0, -9.0, 53.0], 200)]
        s, A, t = sim3.from_anchors([p[0] for p in pairs], [p[1] for p in pairs])
        self.assertAlmostEqual(s, self.s, places=6)
        np.testing.assert_allclose(A, self.A, atol=1e-6)
        np.testing.assert_allclose(t, self.t, atol=1e-5)

    def test_sample_surface_lies_on_triangles(self):
        tris = np.array([[[0, 0, 0], [10, 0, 0], [0, 0, 10]]], float)
        pts, n = sim3.sample_surface(tris, spacing=0.5)
        self.assertGreater(len(pts), 150)
        self.assertTrue(np.allclose(pts[:, 1], 0))
        self.assertTrue(np.allclose(np.abs(n[:, 1]), 1))
        self.assertTrue((pts[:, 0] + pts[:, 2] <= 10 + 1e-9).all())

    def test_fit_recovers_scale_and_place_from_a_bad_start(self):
        tris = box_room()
        world, normals = sim3.sample_surface(tris, spacing=0.4, seed=1)
        obs, _ = sim3.sample_surface(tris, spacing=1.5, seed=2)
        true = (2.0, Rotation.from_euler("z", 20, degrees=True).as_matrix(), np.array([5.0, -3.0, 1.0]))
        pts_sfm = (obs - true[2]) @ true[1] / true[0]          # inverse of apply
        start = (2.0 * 1.08, Rotation.from_euler("z", 23, degrees=True).as_matrix(), true[2] + [1.5, -1.0, 0.5])
        sim, med, frac = sim3.fit_to_surface(pts_sfm, world, normals, start, trim=2.0)
        self.assertLess(med, 0.05)
        self.assertGreater(frac, 0.9)
        self.assertAlmostEqual(sim[0], 2.0, delta=0.02)
        np.testing.assert_allclose(sim3.apply(sim, pts_sfm), obs, atol=0.3)


class Choosing(unittest.TestCase):
    def test_support_counts_points_near_the_surface(self):
        from scipy.spatial import cKDTree
        surf = np.array([[x, y, 0.0] for x in range(10) for y in range(10)])
        pts = np.array([[2.0, 2.0, 0.2], [3.0, 3.0, 5.0]])
        ident = (1.0, np.eye(3), np.zeros(3))
        self.assertAlmostEqual(sim3.support(pts, cKDTree(surf), ident, within=1.0), 0.5)

    def test_collapsed_scale_is_not_plausible(self):
        self.assertFalse(sim3.plausible((0.002, np.eye(3), np.zeros(3)), 13.0))
        self.assertTrue(sim3.plausible((35.0, np.eye(3), np.zeros(3)), 30.0))
        self.assertFalse(sim3.plausible((60.0, np.eye(3), np.zeros(3)), 30.0))


if __name__ == "__main__":
    unittest.main()
