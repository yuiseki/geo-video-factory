import random
import unittest

from PIL import Image

from support import import_pipeline

fa = import_pipeline('buildings.facade_archetypes')

BBOX = [139.30, 35.74, 139.34, 35.77]


def square(cx, cy, half):
    return [[cx - half, cy - half], [cx + half, cy - half], [cx + half, cy + half], [cx - half, cy + half], [cx - half, cy - half]]


def stats(rgb, texture=0.03):
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    return {'rgb': rgb, 'hue': h, 'sat': s, 'val': v, 'texture': texture, 'pixels': 400}


class RoofStatsTest(unittest.TestCase):
    def test_measures_color_and_texture_inside_the_footprint_only(self):
        image = Image.new('RGB', (400, 300), (30, 160, 40))
        rng = random.Random(1)
        # a speckled grey roof (rooftop equipment) in the middle of a green field
        for x in range(180, 220):
            for y in range(130, 170):
                g = 120 + rng.choice((-60, 0, 60))
                image.putpixel((x, y), (g, g, g))
        west, south, east, north = BBOX
        lon = west + 200 / 400 * (east - west)
        lat = north - 150 / 300 * (north - south)
        half = 15 / 400 * (east - west)
        result = fa.roof_stats(image, square(lon, lat, half), BBOX)
        self.assertLess(result['sat'], 0.1, 'the green around the roof is not sampled')
        self.assertGreater(result['texture'], 0.12, 'equipment makes the roof speckled')
        self.assertIsNone(fa.roof_stats(image, square(west - 1, south - 1, 0.0001), BBOX), 'outside the photo')


class ClassifyTest(unittest.TestCase):
    def test_reads_building_kinds_from_the_roof(self):
        blue_tin = stats((60, 90, 160))
        dark_tile = stats((60, 60, 62))
        speckled_grey = stats((150, 150, 148), texture=0.16)
        smooth_grey = stats((170, 170, 168), texture=0.04)
        self.assertEqual(fa.classify_facade(blue_tin, 90, 6.3, '3101', pitched=True), 'house')
        self.assertEqual(fa.classify_facade(dark_tile, 110, 6.0, '3101', pitched=True), 'old_house')
        self.assertEqual(fa.classify_facade(speckled_grey, 600, 15.0, '3102', pitched=False), 'apartment')
        self.assertEqual(fa.classify_facade(smooth_grey, 500, 12.0, '3102', pitched=False), 'office')
        self.assertEqual(fa.classify_facade(smooth_grey, 4000, 9.0, '3101', pitched=False), 'factory')
        self.assertEqual(fa.classify_facade(blue_tin, 20, 3.0, '3111', pitched=False), 'shed')
        self.assertEqual(fa.classify_facade(None, 90, 6.3, '3101', pitched=True), 'house', 'no photo: fall back to size and class')

    def test_an_osm_building_type_wins_over_the_roof(self):
        smooth_grey = stats((170, 170, 168), texture=0.04)
        self.assertEqual(fa.classify_facade(smooth_grey, 500, 12.0, '3102', pitched=False, osm_building='apartments'), 'apartment')
        self.assertEqual(fa.classify_facade(smooth_grey, 500, 6.0, '3101', pitched=False, osm_building='warehouse'), 'factory')

    def test_wall_colors_are_deterministic_and_lean_toward_the_roof_hue_for_houses(self):
        red = stats((180, 60, 50))
        blue = stats((50, 70, 170))
        a = fa.facade_wall_color('house', red, 'gsi/1')
        self.assertEqual(a, fa.facade_wall_color('house', red, 'gsi/1'))
        b = fa.facade_wall_color('house', blue, 'gsi/1')
        self.assertGreater(a[0] - a[2], b[0] - b[2], 'a red-roofed house gets a warmer wall than a blue-roofed one')
        self.assertTrue(all(0.0 <= c <= 1.0 for c in a))
        self.assertIn('factory', fa.STYLE_CODES)


if __name__ == '__main__':
    unittest.main()
