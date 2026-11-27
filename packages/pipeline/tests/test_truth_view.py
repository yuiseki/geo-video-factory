"""truth_view: the pictures a person places a photo with, and checks a kept camera by."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from support import import_pipeline

tv = import_pipeline("world_model.truth_view")
cp = import_pipeline("world_model.corner_pose")


class Grid(unittest.TestCase):
    def test_the_grid_keeps_the_photo_and_labels_full_resolution_pixels(self):
        d = Path(tempfile.mkdtemp())
        Image.new("RGB", (2000, 1500), (90, 140, 220)).save(d / "p.jpg")
        out = tv.grid(d / "p.jpg", d / "g.jpg", width=1000)
        self.assertEqual(Image.open(out).size, (1000, 750))

    def test_a_crop_is_shown_at_full_resolution_around_the_given_pixel(self):
        d = Path(tempfile.mkdtemp())
        Image.new("RGB", (2000, 1500), (90, 140, 220)).save(d / "p.jpg")
        out = tv.grid(d / "p.jpg", d / "c.jpg", crop=(500, 400, 150))
        self.assertEqual(Image.open(out).size, (300, 300))


class Draw(unittest.TestCase):
    def test_a_buildings_edges_are_drawn_where_the_camera_sees_them(self):
        d = Path(tempfile.mkdtemp())
        Image.new("RGB", (800, 600), (255, 255, 255)).save(d / "p.jpg")
        cam = {"eye": [0, -40, 1.6], "Rw": [[1, 0, 0], [0, 0, -1], [0, 1, 0]], "params": [500, 500, 400, 300],
               "width": 800, "height": 600}
        tri = np.array([[[-5, 0, 0], [5, 0, 0], [5, 0, 10]]], float)
        photo = {"file": "p.jpg", "camera": cam, "width": 800, "height": 600, "points": [[[5, 0, 10], [0, 0]]]}
        out = tv.draw(photo, {"b": tri}, d, d / "o.jpg", scale=1.0)
        img = np.asarray(Image.open(out).convert("RGB")).astype(int)
        u, v = cp.project(cam, [[0, 0, 0]])[0].astype(int)      # the middle of the bottom edge
        patch = img[v - 3:v + 4, u - 3:u + 4]
        self.assertTrue(((patch[..., 0] > 200) & (patch[..., 1] < 80)).any())


if __name__ == "__main__":
    unittest.main()
