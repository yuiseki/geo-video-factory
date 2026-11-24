import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from geo import skyline_match as sm  # noqa: E402

BINS = 720  # half a degree


def box(x0, x1, y0, y1, z0, z1):
    """The twelve triangles of an axis-aligned box."""
    c = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], float)
    quads = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]
    return np.array([[c[q[i]] for i in tri] for q in quads for tri in ((0, 1, 2), (0, 2, 3))])


def at(profile, azimuth):
    """The value of the bin whose centre is nearest to the azimuth (degrees)."""
    return profile[int(np.floor(azimuth / (360 / BINS))) % BINS]


def level_camera(heading, pitch=0.0):
    """World-to-camera rotation (x right, y down, z forward) looking at the heading (clockwise from north),
    tipped up by the pitch. World axes are east, north, up."""
    h, p = np.radians(heading), np.radians(pitch)
    z = np.array([np.sin(h) * np.cos(p), np.cos(h) * np.cos(p), np.sin(p)])
    x = np.array([np.cos(h), -np.sin(h), 0.0])
    return np.stack([x, np.cross(z, x), z])


class ModelSkyline(unittest.TestCase):
    def setUp(self):
        self.near = box(-5, 5, 20, 30, 0, 20)

    def test_edges_are_listed_once(self):
        a, b = sm.unique_edges(self.near)
        self.assertEqual(a.shape, (18, 3))  # 12 edges of the box and 6 diagonals of its faces
        self.assertEqual(b.shape, (18, 3))

    def test_the_roof_edge_of_a_box_seen_from_the_ground(self):
        sky = sm.model_skyline(*sm.unique_edges(self.near), eye=[0, 0, 0], bins=BINS)
        self.assertAlmostEqual(at(sky, 0.25), 45.0, delta=0.05)  # the near roof edge, 20 m away and 20 m up
        az = 10.25
        want = np.degrees(np.arctan2(20, 20 / np.cos(np.radians(az))))
        self.assertAlmostEqual(at(sky, az), want, delta=0.01)
        self.assertTrue(np.isnan(at(sky, 90.25)))  # nothing stands to the east
        self.assertTrue(np.isnan(at(sky, 180.25)))

    def test_the_eye_height_lowers_the_skyline(self):
        sky = sm.model_skyline(*sm.unique_edges(self.near), eye=[0, 0, 10], bins=BINS)
        self.assertAlmostEqual(at(sky, 0.25), np.degrees(np.arctan2(10, 20)), delta=0.05)

    def test_a_taller_building_behind_shows_above(self):
        tris = np.concatenate([self.near, box(-2, 2, 40, 50, 0, 80)])
        sky = sm.model_skyline(*sm.unique_edges(tris), eye=[0, 0, 0], bins=BINS)
        self.assertAlmostEqual(at(sky, 0.25), np.degrees(np.arctan2(80, 40)), delta=0.05)
        self.assertAlmostEqual(at(sky, 10.25), np.degrees(np.arctan2(20, 20 / np.cos(np.radians(10.25)))), delta=0.01)

    def test_a_building_across_north_wraps_around(self):
        sky = sm.model_skyline(*sm.unique_edges(self.near), eye=[0, 0, 0], bins=BINS)
        self.assertAlmostEqual(at(sky, 359.75), 45.0, delta=0.05)
        self.assertAlmostEqual(at(sky, 350.25), at(sky, 9.75), delta=1e-6)


class PixelRays(unittest.TestCase):
    def test_the_centre_of_a_level_camera_looks_along_its_heading(self):
        az, el = sm.pixel_rays(401, 301, 300.0, 200.5, 150.5, 0.0, level_camera(90.0), step=1)
        self.assertAlmostEqual(az[150, 200], 90.0, places=6)
        self.assertAlmostEqual(el[150, 200], 0.0, places=6)
        self.assertGreater(az[150, 300], 90.0)  # to the right is clockwise
        self.assertGreater(el[50, 200], 0.0)  # the top of the picture is up
        self.assertAlmostEqual(az[150, 300], 90.0 + np.degrees(np.arctan2(100, 300)), places=6)

    def test_a_tipped_camera(self):
        az, el = sm.pixel_rays(401, 301, 300.0, 200.5, 150.5, 0.0, level_camera(350.0, 30.0), step=1)
        self.assertAlmostEqual(az[150, 200], 350.0, places=6)
        self.assertAlmostEqual(el[150, 200], 30.0, places=6)

    def test_the_step_takes_the_centres_of_the_blocks(self):
        az, el = sm.pixel_rays(400, 300, 300.0, 200.0, 150.0, 0.0, level_camera(0.0), step=4)
        self.assertEqual(az.shape, (75, 100))
        full, _ = sm.pixel_rays(400, 300, 300.0, 200.0, 150.0, 0.0, level_camera(0.0), step=1)
        self.assertAlmostEqual(az[10, 20], (full[41, 81] + full[42, 82]) / 2, places=3)

    def test_radial_distortion_is_undone(self):
        f, k = 300.0, 0.05
        xu = 0.3  # the ray tan(angle) = 0.3 to the right lands at xu (1 + k xu^2) in the picture
        u = 200.5 + f * xu * (1 + k * xu * xu)
        az, _ = sm.pixel_rays(401, 301, f, 200.5, 150.5, k, level_camera(0.0), step=1)
        col = np.arange(401) + 0.5
        got = np.interp(u, col, az[150])
        self.assertAlmostEqual(got, np.degrees(np.arctan(xu)), places=4)


class PhotoSkyline(unittest.TestCase):
    def grid(self):
        az, el = np.meshgrid(np.arange(-30, 30, 0.05) % 360, np.arange(-10, 40, 0.05))
        return az, el

    def test_three_kinds_of_columns(self):
        az, el = self.grid()
        rel = (az + 180) % 360 - 180
        top = np.where(rel < -10, 20.0, np.where(rel < 10, 100.0, -100.0))  # a roof at 20, a wall past the frame, open sky
        got = sm.photo_skyline(az, el, el > top, bins=BINS)
        self.assertAlmostEqual(at(got["sky"], 340.25), 20.0, delta=0.26)
        self.assertTrue(np.isnan(at(got["floor"], 340.25)))
        self.assertTrue(np.isnan(at(got["sky"], 0.25)))
        self.assertAlmostEqual(at(got["floor"], 0.25), 40.0, delta=0.26)  # the building reaches at least the frame top
        self.assertAlmostEqual(at(got["ceil"], 20.25), -10.0, delta=0.26)  # nothing stands above the frame bottom
        self.assertTrue(np.isnan(at(got["sky"], 90.25)))  # outside the picture
        self.assertTrue(np.isnan(at(got["floor"], 90.25)))
        self.assertTrue(np.isnan(at(got["ceil"], 90.25)))

    def test_a_speck_in_the_sky_does_not_lift_the_skyline(self):
        az, el = self.grid()
        sky = el > 20.0
        sky[700, 100] = False
        got = sm.photo_skyline(az, el, sky, bins=BINS)
        self.assertAlmostEqual(at(got["sky"], (az[0, 100]) + 0.01), 20.0, delta=0.26)


class Match(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(1)
        walk = np.cumsum(rng.normal(0, 1.0, (5, BINS)), axis=1)
        self.model = 20 + walk - np.linspace(0, 1, BINS) * walk[:, -1:]  # five places, closed profiles

    def photo(self, place, shift, lo=100, n=120):
        nan = np.full(BINS, np.nan)
        sky = nan.copy()
        b = np.arange(lo, lo + n)
        sky[b] = self.model[place, (b + shift) % BINS]
        return dict(sky=sky, floor=nan.copy(), ceil=nan.copy())

    def test_the_place_and_the_turn_are_found(self):
        cost = sm.match_cost(self.photo(3, 37), self.model)
        self.assertEqual(cost.shape, (5, BINS))
        place, shift = np.unravel_index(np.argmin(cost), cost.shape)
        self.assertEqual((place, shift), (3, 37))
        self.assertAlmostEqual(cost[3, 37], 0.0, places=6)

    def test_the_cost_is_the_mean_clipped_difference(self):
        ph = self.photo(0, 0)
        ph["sky"][100:130] += 2.0  # 30 of the 120 bins are off by 2 degrees
        ph["sky"][130:140] += 50.0  # 10 are off by more than the limit
        cost = sm.match_cost(ph, self.model, tau=5.0)
        self.assertAlmostEqual(cost[0, 0], (30 * 2.0 + 10 * 5.0) / 120, places=5)

    def test_the_floor_and_the_ceiling_are_one_sided(self):
        nan = np.full(BINS, np.nan)
        model = np.full((1, BINS), 30.0)
        floor, ceil = nan.copy(), nan.copy()
        floor[0:10] = 32.0  # the building leaves the frame at 32, the model only reaches 30
        floor[10:20] = 25.0  # satisfied
        ceil[20:30] = 29.0  # the photo shows sky down to 29, the model stands to 30
        ceil[30:40] = 35.0  # satisfied
        cost = sm.match_cost(dict(sky=nan.copy(), floor=floor, ceil=ceil), model)
        self.assertAlmostEqual(cost[0, 0], (10 * 2.0 + 10 * 1.0) / 40, places=5)
        only = sm.match_cost(dict(sky=nan.copy(), floor=floor, ceil=ceil), model, use=("floor",))
        self.assertAlmostEqual(only[0, 0], 10 * 2.0 / 20, places=5)

    def test_open_sky_in_the_model_counts_as_the_horizon(self):
        nan = np.full(BINS, np.nan)
        sky = nan.copy()
        sky[0:10] = 3.0
        cost = sm.match_cost(dict(sky=sky, floor=nan.copy(), ceil=nan.copy()), np.full((1, BINS), np.nan))
        self.assertAlmostEqual(cost[0, 0], 3.0, places=5)

    def test_too_few_bins_gives_no_answer(self):
        nan = np.full(BINS, np.nan)
        sky = nan.copy()
        sky[0:5] = 3.0
        cost = sm.match_cost(dict(sky=sky, floor=nan.copy(), ceil=nan.copy()), self.model, min_bins=20)
        self.assertTrue(np.isnan(cost).all())


class RoundTrip(unittest.TestCase):
    def test_a_rendered_box_is_matched_where_it_was_seen(self):
        tris = np.concatenate([box(-5, 5, 20, 30, 0, 20), box(8, 14, 25, 40, 0, 35)])
        a, b = sm.unique_edges(tris)
        eyes = np.array([[0, 0, 1.5], [6, 0, 1.5], [0, -8, 1.5], [-6, 4, 1.5]], float)
        model = np.stack([sm.model_skyline(a, b, e, bins=BINS) for e in eyes])
        R = level_camera(10.0, 25.0)
        az, el = sm.pixel_rays(1600, 1200, 1000.0, 800.0, 600.0, 0.02, R, step=1)  # about 40 pixels per cell
        truth = np.nan_to_num(model[1], nan=0.0)
        sky = el > truth[np.floor(az / (360 / BINS)).astype(int) % BINS]
        photo = sm.photo_skyline(az, el, sky, bins=BINS)
        cost = sm.match_cost(photo, model)
        place, shift = np.unravel_index(np.nanargmin(cost), cost.shape)
        self.assertEqual(place, 1)
        self.assertIn(shift, (0, 1, BINS - 1))
        self.assertLess(cost[1, 0], 0.3)


if __name__ == "__main__":
    unittest.main()
