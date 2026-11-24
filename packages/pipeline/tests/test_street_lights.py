import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from buildings import street_lights  # noqa: E402


class SnapTests(unittest.TestCase):
    def test_snaps_each_point_to_the_nearest_candidate_within_reach(self):
        candidates = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
        snapped = street_lights.snap_points([(1.0, 1.0), (9.0, 8.0), (50.0, 50.0)], candidates, max_distance=5.0)
        self.assertEqual(snapped, [(0.0, 0.0), (10.0, 10.0), None])

    def test_lnglat_round_trip_through_local_meters(self):
        origin = (139.7005, 35.66)
        xy = street_lights.to_local((139.701, 35.6605), origin)
        back = street_lights.to_lnglat(xy, origin)
        self.assertAlmostEqual(back[0], 139.701, places=9)
        self.assertAlmostEqual(back[1], 35.6605, places=9)


if __name__ == "__main__":
    unittest.main()
