import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vpr_eval as ve  # noqa: E402


def item(i, lon, lat, creator="a", date="2020-01-01", role="db"):
    return {"id": f"p{i}", "lon": lon, "lat": lat, "creator": creator, "date": date, "role": role}


class Metres(unittest.TestCase):
    def test_one_thousandth_of_a_degree_of_latitude_is_about_111_m(self):
        self.assertAlmostEqual(ve.metres(139.7, 35.0, 139.7, 35.001), 111.2, delta=0.5)


class Eligible(unittest.TestCase):
    def test_the_same_creator_on_the_same_day_is_not_a_fair_match(self):
        q = item(0, 0, 0, "a", "2020-01-01")
        self.assertFalse(ve.eligible(q, item(1, 0, 0, "a", "2020-01-01")))
        self.assertTrue(ve.eligible(q, item(2, 0, 0, "a", "2020-01-02")))
        self.assertTrue(ve.eligible(q, item(3, 0, 0, "b", "2020-01-01")))

    def test_a_photo_never_matches_itself(self):
        q = item(0, 0, 0, "a", "2020-01-01")
        self.assertFalse(ve.eligible(q, q))


class Evaluate(unittest.TestCase):
    def setUp(self):
        # p0 and p1 stand 11 m apart, p2 is 1.1 km away; p3 is shot with p0 on the same day.
        self.items = [
            item(0, 139.7, 35.0, "a"), item(1, 139.7, 35.0001, "b"),
            item(2, 139.7, 35.01, "c"), item(3, 139.7, 35.0, "a"),
        ]

    def test_the_twin_from_the_same_shoot_is_skipped_and_the_next_best_counts(self):
        d = np.array([[1, 0], [0.8, 0.6], [0.6, 0.8], [1, 0]], dtype=np.float32)
        rows = ve.evaluate(self.items, d, ks=(1, 2))
        r0 = rows[0]
        self.assertEqual(r0["ranked"][0], "p1")
        self.assertAlmostEqual(r0["top1_m"], 11.1, delta=0.2)
        self.assertAlmostEqual(r0["oracle_m"], 11.1, delta=0.2)
        self.assertTrue(r0["hit"][1])

    def test_a_far_top1_is_a_miss_at_one_but_a_hit_at_two(self):
        d = np.array([[1, 0], [0, 1], [0.9, 0.44], [1, 0]], dtype=np.float32)
        r0 = ve.evaluate(self.items, d, ks=(1, 2))[0]
        self.assertEqual(r0["ranked"][:2], ["p2", "p1"])
        self.assertFalse(r0["hit"][1])
        self.assertTrue(r0["hit"][2])

    def test_only_database_photos_are_retrieved(self):
        self.items[1]["role"] = "query"
        d = np.array([[1, 0], [1, 0], [0.6, 0.8], [1, 0]], dtype=np.float32)
        r0 = ve.evaluate(self.items, d, ks=(1,))[0]
        self.assertEqual(r0["ranked"][0], "p2")


class Summary(unittest.TestCase):
    def test_recall_counts_only_queries_that_have_a_match_within_reach(self):
        rows = [
            {"oracle_m": 5, "top1_m": 3, "hit": {1: True, 5: True}},
            {"oracle_m": 10, "top1_m": 400, "hit": {1: False, 5: True}},
            {"oracle_m": 900, "top1_m": 950, "hit": {1: False, 5: False}},
        ]
        s = ve.summary(rows, ks=(1, 5))
        self.assertEqual(s["queries"], 3)
        self.assertEqual(s["reachable"], 2)
        self.assertEqual(s["recall"], {1: 0.5, 5: 1.0})
        self.assertEqual(s["median_top1_m"], 400)


if __name__ == "__main__":
    unittest.main()
