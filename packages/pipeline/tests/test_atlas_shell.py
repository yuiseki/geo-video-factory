"""atlas_shell.push_out: an atlas lies a little off the faces it paints, with the copies of a vertex at one place
moved together (along the faces' mean normal), so the edges of a building stay closed instead of opening a crack
through which the building below shows."""
import unittest

import numpy as np

from support import import_pipeline

shell = import_pipeline("world_model.atlas_shell")


class PushOut(unittest.TestCase):
    def test_a_wall_and_a_roof_meeting_at_an_edge_stay_joined(self):
        # unwelded: a wall (normal +x) and a roof (normal +z) share the edge x=1, z=1 through separate copies
        v = np.array([[1, 0, 0], [1, 1, 0], [1, 1, 1], [1, 0, 1],          # wall
                      [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float)  # roof
        faces = [(0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7)]
        out = shell.push_out(v, faces, 0.15)
        self.assertTrue(np.allclose(out[2], out[6]) and np.allclose(out[3], out[5]))   # the edge copies move together
        self.assertTrue(np.allclose(out[0], v[0] + [0.15, 0, 0]))         # a wall-only vertex moves out of the wall
        self.assertTrue(np.allclose(out[7], v[7] + [0, 0, 0.15]))         # a roof-only vertex up from the roof
        d = out[2] - v[2]
        self.assertAlmostEqual(float(np.linalg.norm(d)), 0.15, places=6)
        self.assertGreater(d[0], 0); self.assertGreater(d[2], 0)


if __name__ == "__main__":
    unittest.main()
