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


class Frame(unittest.TestCase):
    def test_poses_in_the_first_cameras_frame_are_carried_into_the_anchors_world(self):
        """MapAnything returns the first view near identity: every pose is moved by anchor_given @ inv(first_out)."""
        rng = np.random.default_rng(0)
        q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
        given = np.eye(4); given[:3, :3] = q * np.sign(np.linalg.det(q)); given[:3, 3] = [5.0, -33.0, 40.0]
        rel = np.eye(4); rel[:3, :3] = given[:3, :3].T @ given[:3, :3]; rel[:3, 3] = [2.0, 0.0, 7.0]   # view 2
        first_out = np.eye(4); first_out[:3, 3] = [0.01, -0.02, 0.1]                      # not quite identity
        world = ma.to_anchor_frame([first_out, first_out @ rel], given)
        np.testing.assert_allclose(world[0], given, atol=1e-12)
        np.testing.assert_allclose(world[1], given @ rel, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
