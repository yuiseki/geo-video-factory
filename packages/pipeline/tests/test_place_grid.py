"""place_grid: the places photo_place searches."""
import unittest

import numpy as np

from support import import_pipeline

pg = import_pipeline("geo.place_grid")


class Seeded(unittest.TestCase):
    def test_the_fine_grid_is_laid_around_the_best_places_two_coarse_steps_apart(self):
        coarse, _, _ = pg.grid_places(0, 0, 40, 8, 1.6)
        cost = np.hypot(coarse[:, 0] - 16, coarse[:, 1]) + 0.5 * np.hypot(coarse[:, 0] + 24, coarse[:, 1] - 8)
        cost[np.hypot(coarse[:, 0] + 24, coarse[:, 1] - 8) < 1] = 0.0      # a second low place far from the first
        fine = pg.seeded_places(coarse, cost, 2, 8, 2, 0, 0, 40)
        near = lambda x, y: (np.hypot(fine[:, 0] - x, fine[:, 1] - y) <= 8 * np.sqrt(2) + 1e-6).any()
        self.assertTrue(near(16, 0) or near(24, 0))
        self.assertTrue(near(-24, 8))
        self.assertTrue((np.hypot(fine[:, 0], fine[:, 1]) <= 40 + 1e-9).all())
        self.assertTrue(np.allclose(np.round(fine[:, :2] / 2) * 2, fine[:, :2]))     # on the fine step
        self.assertTrue((fine[:, 2] == 1.6).all())

    def test_a_place_the_coarse_search_could_not_cost_is_never_a_seed(self):
        coarse, _, _ = pg.grid_places(0, 0, 16, 8, 1.6)
        cost = np.full(len(coarse), np.nan); cost[0] = 1.0
        fine = pg.seeded_places(coarse, cost, 3, 8, 2, 0, 0, 100)
        self.assertLessEqual(np.hypot(*(fine[:, :2] - coarse[0, :2]).T).max(), 8 * np.sqrt(2) + 1e-6)


if __name__ == "__main__":
    unittest.main()
