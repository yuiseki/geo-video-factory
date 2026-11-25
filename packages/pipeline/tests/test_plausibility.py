import unittest

from buildings import plausibility as pl


def square(lon, lat, d=0.0005, **tags):
    ring = [[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d]]
    return {"type": "Feature", "properties": tags, "geometry": {"type": "Polygon", "coordinates": [ring]}}


class OsmHeight(unittest.TestCase):
    def test_levels_win_over_height(self):
        self.assertAlmostEqual(pl.osm_height({"building:levels": "10", "height": "80"}), 33.0)

    def test_height_with_a_unit_is_read(self):
        self.assertEqual(pl.osm_height({"height": "45 m"}), 45.0)

    def test_nothing_usable_is_none(self):
        self.assertIsNone(pl.osm_height({"building": "yes", "building:levels": "0"}))


class Judge(unittest.TestCase):
    def test_a_complex_extruded_to_its_tower_height_disagrees_with_osm(self):
        # Namba Parks: PLATEAU 155 m over 2.5 ha, flat on top all over, OSM 10 levels
        self.assertEqual(pl.judge({"height": 155, "area": 24918, "top": 24586}, 33.0), "taller than OSM says")

    def test_a_complex_with_a_tower_on_it_passes(self):
        # Tokyo Midtown: 249 m, 2 ha, but only a fifth of it reaches the top; OSM maps the low part
        self.assertIsNone(pl.judge({"height": 249, "area": 19565, "top": 4076}, None))
        self.assertIsNone(pl.judge({"height": 114, "area": 12119, "top": 5482}, 16.5))   # Shibuya Mark City

    def test_a_small_tower_that_osm_undercounts_passes(self):
        # an 85 m box on 1,700 m2 against 11 OSM levels: more likely OSM is short than PLATEAU tall
        self.assertIsNone(pl.judge({"height": 85, "area": 1683, "top": 1683}, 36.3))

    def test_a_real_tower_that_osm_undercounts_passes(self):
        # Parks Tower: 158 m in PLATEAU, OSM 30 levels (99 m at 3.3 m a level)
        self.assertIsNone(pl.judge({"height": 158, "area": 2022}, 99.0))

    def test_a_needle_is_refused(self):
        self.assertEqual(pl.judge({"height": 155, "area": 2.0}, None), "needle")

    def test_a_chimney_is_not_a_needle(self):
        self.assertIsNone(pl.judge({"height": 40, "area": 4.0}, None))

    def test_a_giant_tall_slab_without_osm_support_is_refused(self):
        self.assertEqual(pl.judge({"height": 150, "area": 20000, "top": 19000}, None), "giant slab")

    def test_an_ordinary_building_passes(self):
        self.assertIsNone(pl.judge({"height": 30, "area": 800}, 27.0))


class Implausible(unittest.TestCase):
    def test_the_smallest_osm_building_around_the_centre_is_the_witness(self):
        osm = [square(135.5, 34.66, d=0.002, building="retail", **{"building:levels": "10"}),
               square(135.5, 34.66, d=0.0003, building="yes", **{"building:levels": "45"})]
        shapes = {"tower": {"lonlat": [135.5, 34.66], "height": 150.0, "area": 1500.0},
                  "podium": {"lonlat": [135.5015, 34.6615], "height": 150.0, "area": 20000.0, "top": 19800.0}}
        self.assertEqual(pl.implausible(shapes, osm), {"podium": "taller than OSM says"})


class ProxyCap(unittest.TestCase):
    def test_a_proxy_is_never_a_needle(self):
        self.assertAlmostEqual(pl.cap_height(180.0, 25.0), pl.MAX_SLENDERNESS * 5.0)
        self.assertEqual(pl.cap_height(30.0, 400.0), 30.0)


if __name__ == "__main__":
    unittest.main()
