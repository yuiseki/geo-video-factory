"""facade_tiles: repeating window patterns, one per facade style, for walls baked into PLATEAU++ GLBs."""
import unittest

import numpy as np

from support import import_pipeline

facade_tiles = import_pipeline("buildings.facade_tiles")


class Tiles(unittest.TestCase):
    def test_every_style_has_a_day_and_a_night_image_of_the_same_size(self):
        for style in facade_tiles.STYLES:
            day, night = facade_tiles.tile(style)
            self.assertEqual(day.size, night.size, style)
            self.assertEqual(day.size, (facade_tiles.BAYS * facade_tiles.CELL, facade_tiles.STOREYS * facade_tiles.CELL))

    def test_the_same_style_always_gives_the_same_pixels(self):
        a, b = facade_tiles.tile("house")[0], facade_tiles.tile("house")[0]
        self.assertEqual(a.tobytes(), b.tobytes())

    def test_glazed_styles_darken_part_of_the_wall_and_light_part_of_it_at_night(self):
        for style in ("curtain", "house", "rc", "apartment", "office", "old_house"):
            day, night = (np.asarray(im, float) / 255 for im in facade_tiles.tile(style))
            self.assertLess(day.mean(), 0.97, style)                    # glass is darker than paint
            paint = (day.max(axis=2) > 0.95).mean()
            if style == "curtain":
                self.assertLess(paint, 0.4)             # a curtain wall is mostly glass
            else:
                self.assertGreater(paint, 0.3, style)   # elsewhere most of the wall is paint (multiplier 1)
            self.assertGreater((night.max(axis=2) > 0.2).mean(), 0.02, style)

    def test_sheds_and_factories_have_no_storey_windows_and_no_lights(self):
        for style in ("shed", "factory"):
            night = np.asarray(facade_tiles.tile(style)[1], float)
            self.assertEqual(night.max(), 0.0, style)

    def test_scale_gives_metres_per_tile_and_varies_by_building(self):
        bay_a, storey_a = facade_tiles.module("house", "building-a")
        bay_b, storey_b = facade_tiles.module("house", "building-b")
        self.assertNotEqual(bay_a, bay_b)
        self.assertAlmostEqual(storey_a, 2.85)
        self.assertTrue(3.3 <= bay_a <= 4.6)
        self.assertEqual(facade_tiles.module("house", "building-a"), (bay_a, storey_a))

    def test_proxy_style_codes_name_the_styles(self):
        self.assertEqual(facade_tiles.PROXY_STYLES[0], "house")
        self.assertEqual(facade_tiles.PROXY_STYLES[5], "office")


if __name__ == "__main__":
    unittest.main()
