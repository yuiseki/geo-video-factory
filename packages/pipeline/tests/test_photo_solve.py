"""photo_solve: the gates a camera found from the photo alone must pass before it is given as the answer."""
import unittest

import numpy as np

from support import import_pipeline

ps = import_pipeline("geo.photo_solve")

R = np.eye(3).tolist()


def run(eye, miss, Rw=R):
    return {"camera": {"eye": eye, "Rw": Rw, "params": [1, 1, 0, 0]}, "miss_px": miss}


class Judge(unittest.TestCase):
    def test_three_starts_reaching_one_camera_close_to_the_fix_is_solved(self):
        best = run([10, 5, 41.6], 2.0)
        runs = [best, run([10.3, 5, 41.6], 2.2), run([10, 5.4, 41.6], 2.1), run([40, 9, 50], 90.0), run([3, 3, 41], 2.5)]
        verdict, gates = ps.judge(True, best, runs, 80.0)
        self.assertEqual(verdict, "solved")
        self.assertEqual(gates["starts_agreeing"][0], 3)

    def test_each_gate_refuses_on_its_own(self):
        best = run([10, 5, 41.6], 2.0)
        agreeing = [best, run([10.3, 5, 41.6], 2.2), run([10, 5.4, 41.6], 2.1)]
        self.assertEqual(ps.judge(False, best, agreeing, 80.0)[0], "refused: alone")
        self.assertEqual(ps.judge(True, run([10, 5, 41.6], 6.0), [run([10, 5, 41.6], 6.0)] * 3, 80.0)[0],
                         "refused: miss_px")
        self.assertEqual(ps.judge(True, best, [best, run([20, 5, 41.6], 2.1), run([3, 9, 41.6], 2.5)], 80.0)[0],
                         "refused: starts_agreeing")
        self.assertEqual(ps.judge(True, best, agreeing, 8.0)[0], "refused: from_gps_m")

    def test_a_start_that_lost_the_building_does_not_count_as_agreeing(self):
        best = run([10, 5, 41.6], 2.0)
        lost = run([10, 5, 41.6], float("inf"))
        self.assertEqual(ps.judge(True, best, [best, lost, lost], 80.0)[1]["starts_agreeing"][0], 1)


if __name__ == "__main__":
    unittest.main()
