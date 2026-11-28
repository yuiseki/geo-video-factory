import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mapanything_anchor as ma  # noqa: E402


class Pose(unittest.TestCase):
    def setUp(self):
        a = np.radians(30)        # looking north-east, level: forward (east sin, north cos), right, down
        fwd = np.array([np.sin(a), np.cos(a), 0]); right = np.array([np.cos(a), -np.sin(a), 0])
        self.cam = {"Rw": np.array([right, np.cross(fwd, right), fwd]).tolist(), "eye": [10.0, -5.0, 41.6]}

    def test_cam2world_puts_the_camera_at_its_eye_and_looks_forward(self):
        pose = ma.pose_of(self.cam)
        np.testing.assert_allclose(pose[:3, 3], self.cam["eye"])
        np.testing.assert_allclose(pose[:3, :3] @ [0, 0, 1], self.cam["Rw"][2])       # camera z is forward
        x_world = np.array([20.0, 3.0, 45.0])                                         # the two conventions agree
        x_cam = np.asarray(self.cam["Rw"]) @ (x_world - self.cam["eye"])
        np.testing.assert_allclose(pose[:3, :3] @ x_cam + pose[:3, 3], x_world)

    def test_camera_of_undoes_pose_of(self):
        back = ma.camera_of(ma.pose_of(self.cam))
        np.testing.assert_allclose(back["eye"], self.cam["eye"])
        np.testing.assert_allclose(back["Rw"], self.cam["Rw"], atol=1e-12)


if __name__ == "__main__":
    unittest.main()
