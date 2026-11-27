"""upright: the pitch and roll of a camera read from the picture's lines of things that stand upright."""
import unittest

import numpy as np

from support import import_pipeline

up = import_pipeline("geo.upright")
pp = import_pipeline("geo.photo_place")

F, W, H = 1000.0, 1300, 975


def drawn(R, a, b):
    """The segment of the picture a world segment is drawn as by a camera at the origin."""
    out = []
    for p in (a, b):
        c = R @ np.asarray(p, float)
        out += [F * c[0] / c[2] + W / 2, F * c[1] / c[2] + H / 2]
    return out


def street(heading, pitch, roll, posts=30, clutter=40, seed=1):
    """Posts standing ahead of the camera, and as many lines again lying and leaning every way."""
    rng = np.random.default_rng(seed)
    R = pp.camera(heading, pitch, roll)
    hd = np.radians(heading)
    ahead, side = np.array([np.sin(hd), np.cos(hd), 0]), np.array([np.cos(hd), -np.sin(hd), 0])
    segs = []
    for _ in range(posts):
        foot = ahead * rng.uniform(20, 60) + side * rng.uniform(-15, 15) + [0, 0, rng.uniform(0, 10)]
        segs.append(drawn(R, foot, foot + [0, 0, rng.uniform(4, 10)]))
    for _ in range(clutter):
        foot = ahead * rng.uniform(20, 60) + side * rng.uniform(-15, 15) + [0, 0, rng.uniform(0, 15)]
        lean = rng.normal(size=3)
        segs.append(drawn(R, foot, foot + lean / np.linalg.norm(lean) * rng.uniform(4, 10)))
    return np.array(segs)


class UpFromLines(unittest.TestCase):
    def test_posts_seen_from_below_give_the_pitch_and_roll_of_the_camera(self):
        for heading, pitch, roll in ((40.0, 21.0, 2.5), (290.0, 18.5, -2.0), (120.0, 34.0, 0.0), (200.0, -17.5, -0.5)):
            got = up.up_from_lines(street(heading, pitch, roll), F, W / 2, H / 2)
            self.assertAlmostEqual(got["pitch"], pitch, delta=0.15)
            self.assertAlmostEqual(got["roll"], roll, delta=0.15)
            self.assertGreaterEqual(got["lines"], 30)

    def test_the_same_lines_give_the_same_answer_every_time(self):
        segs = street(40.0, 21.0, 2.5)
        self.assertEqual(up.up_from_lines(segs, F, W / 2, H / 2), up.up_from_lines(segs, F, W / 2, H / 2))

    def test_fewer_than_two_lines_say_nothing(self):
        self.assertIsNone(up.up_from_lines(street(40.0, 21.0, 2.5)[:1], F, W / 2, H / 2))
        self.assertIsNone(up.up_from_lines(np.zeros((0, 4)), F, W / 2, H / 2))


class Ranges(unittest.TestCase):
    def test_an_upright_read_from_many_lines_narrows_the_search_around_it(self):
        got = up.ranges({"pitch": 21.1, "roll": 2.6, "lines": 99, "of": 258, "share": 0.4})
        self.assertEqual(got, {"pitch": "19:23:2", "roll": "1:4:1.5"})

    def test_an_upright_read_from_few_lines_or_none_leaves_the_search_as_it_was(self):
        self.assertEqual(up.ranges(None), {})
        self.assertEqual(up.ranges({"pitch": 21.1, "roll": 2.6, "lines": 12, "of": 258, "share": 0.4}), {})
        self.assertEqual(up.ranges({"pitch": 21.1, "roll": 2.6, "lines": 99, "of": 2000, "share": 0.05}), {})


if __name__ == "__main__":
    unittest.main()
