"""osm_street_lamps: street lamps for a scene, from OSM lamp nodes and, where OSM has none, along the roads."""
import json
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import import_pipeline

sl = import_pipeline("world_model.osm_street_lamps")

O = (139.0, 35.0)
KX = 111320.0 * math.cos(math.radians(35.0))


def east(m):          # a longitude m metres east of O
    return 139.0 + m / KX


def north(m):
    return 35.0 + m / 110950.0


def road(way_id, nodes, **tags):
    els = [{"type": "node", "id": way_id * 100 + i, "lon": lon, "lat": lat} for i, (lon, lat) in enumerate(nodes)]
    els.append({"type": "way", "id": way_id, "nodes": [n["id"] for n in els], "tags": tags})
    return els


def local(lamp):
    lon, lat = lamp["lnglat"]
    return ((lon - O[0]) * KX, (lat - O[1]) * 110950.0)


class AlongRoads(unittest.TestCase):
    def test_lamps_stand_at_the_spacing_on_alternate_kerbs_half_the_width_out(self):
        els = road(1, [(139.0, 35.0), (east(110), 35.0)], highway="secondary", width="12")
        lamps = sl.from_overpass(els, spacing=25)
        xy = [local(l) for l in lamps]
        self.assertEqual([round(x) for x, _ in xy], [0, 25, 50, 75, 100])
        self.assertEqual([round(y, 1) for _, y in xy], [6.5, -6.5, 6.5, -6.5, 6.5])    # kerb + 0.5 m, sides alternate
        self.assertTrue(all(l["from"] == "road" for l in lamps))
        self.assertEqual([l["heading"] for l in lamps], [180.0, 0.0, 180.0, 0.0, 180.0])   # toward the road's centre

    def test_the_width_comes_from_lanes_or_the_road_class_when_untagged(self):
        by_lanes = sl.from_overpass(road(1, [(139.0, 35.0), (east(10), 35.0)], highway="primary", lanes="4"), spacing=25)
        by_class = sl.from_overpass(road(2, [(139.0, 35.0), (east(10), 35.0)], highway="residential"), spacing=25)
        self.assertAlmostEqual(local(by_lanes[0])[1], 4 * 3.0 / 2 + 0.5, places=1)
        self.assertAlmostEqual(local(by_class[0])[1], sl.CLASS_WIDTH["residential"] / 2 + 0.5, places=1)

    def test_the_spacing_runs_on_across_the_bends_of_a_way(self):
        els = road(1, [(139.0, 35.0), (east(30), 35.0), (east(30), north(35))], highway="tertiary")
        self.assertEqual(len(sl.from_overpass(els, spacing=20)), 4)        # 0, 20, 40, 60 m along 65 m

    def test_tunnels_footways_and_service_roads_get_no_lamps(self):
        els = (road(1, [(139.0, 35.0), (east(50), 35.0)], highway="primary", tunnel="yes")
               + road(2, [(139.0, 35.0), (east(50), 35.0)], highway="footway")
               + road(3, [(139.0, 35.0), (east(50), 35.0)], highway="service"))
        self.assertEqual(sl.from_overpass(els, spacing=25), [])


class FromOsmNodes(unittest.TestCase):
    def test_mapped_lamps_are_kept_and_road_lamps_near_them_dropped(self):
        els = road(1, [(139.0, 35.0), (east(110), 35.0)], highway="secondary", width="12")
        els.append({"type": "node", "id": 9, "lon": east(50), "lat": north(7), "tags": {"highway": "street_lamp"}})
        lamps = sl.from_overpass(els, spacing=25)
        mapped = [l for l in lamps if l["from"] == "osm"]
        self.assertEqual([l["osm"] for l in mapped], [9])
        self.assertNotIn(50, [round(local(l)[0]) for l in lamps if l["from"] == "road"])
        self.assertEqual(len(lamps), 5)


class Fetch(unittest.TestCase):
    def test_a_box_is_asked_once_from_the_own_overpass_and_kept_in_the_shared_cache(self):
        calls = []
        els = road(1, [(139.0, 35.0), (east(110), 35.0)], highway="secondary")

        def fetch(url, query):
            calls.append(url)
            return {"elements": els}

        with tempfile.TemporaryDirectory() as root, \
                mock.patch.dict(os.environ, {"GEO_VIDEO_CACHE": root, "OVERPASS_URL": "https://overpass.example/api"}):
            path = sl.lamps_file([139.0, 35.0, 139.01, 35.01], fetch=fetch)
            again = sl.lamps_file([139.0, 35.0, 139.01, 35.01], fetch=lambda u, q: self.fail("asked again"))
            doc = json.loads(Path(path).read_text())
            self.assertEqual(path, again)
            self.assertTrue(str(path).startswith(root))
        self.assertEqual(calls, ["https://overpass.example/api"])
        self.assertIn("ODbL", doc["source"])
        self.assertEqual(len(doc["lamps"]), 5)

    def test_no_public_server_is_ever_called(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit):
            sl.lamps_file([139.0, 35.0, 139.01, 35.01], fetch=lambda u, q: {"elements": []})


if __name__ == "__main__":
    unittest.main()
