"""atlas_views: reading how many photos saw a texel back from build_atlas's seen.png."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from world_model import atlas_views as av  # noqa: E402


class SeenLevel(unittest.TestCase):
    def test_seen_png_stores_the_count_as_build_atlas_writes_it(self):
        counts = np.array([0, 1, 2, 3, 5, 9])
        self.assertEqual(av.seen_png(counts).tolist(), [0, 51, 102, 153, 255, 255])

    def test_the_threshold_keeps_texels_seen_by_at_least_that_many_photos(self):
        values = av.seen_png(np.arange(0, 6)) / 255.0         # what a Non-Color, Closest texture reads
        for need in (1, 2, 3, 5):
            kept = values > av.views_threshold(need)
            self.assertEqual(kept.tolist(), [c >= need for c in range(6)], need)

    def test_one_photo_is_the_default_and_keeps_every_seen_texel(self):
        self.assertLess(av.views_threshold(1), 51 / 255)
        self.assertGreater(av.views_threshold(1), 0)


if __name__ == "__main__":
    unittest.main()
