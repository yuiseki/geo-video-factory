import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from buildings import glb_spatial as gs
from buildings import plateau_pp

from test_glb_strip import plain_glb


class RemoveImplausible(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "models").mkdir()
        (self.dir / "models" / "t.glb").write_bytes(plain_glb())
        self.manifest = {"tiles": [{"glb": "models/t.glb", "rtc": [0.0, 0.0, 6378137.0], "ids": ["a", "b"]}]}

    def shapes(self, payload, rtc, ids):
        return {"a": {"lonlat": [135.5, 34.66], "height": 20.0, "area": 400.0},
                "b": {"lonlat": [135.5016, 34.6618], "height": 155.0, "area": 2.0}}

    def test_the_needle_leaves_the_tile_and_is_recorded(self):
        with mock.patch.object(gs, "extract_glb_feature_shapes", self.shapes):
            m = plateau_pp.remove_implausible(self.dir, self.manifest, osm_features=[])
        left = gs.extract_glb_feature_heights((self.dir / "models" / "t.glb").read_bytes(), [0.0, 0.0, 6378137.0],
                                              ["a", "b"])
        self.assertEqual(set(left), {"a"})
        self.assertEqual([(r["id"], r["trap"]) for r in m["removed_buildings"]], [("b", "needle")])
        self.assertEqual(m["tiles"][0]["bytes"], (self.dir / "models" / "t.glb").stat().st_size)

    def test_running_it_twice_changes_nothing_more(self):
        with mock.patch.object(gs, "extract_glb_feature_shapes", self.shapes):
            m = plateau_pp.remove_implausible(self.dir, self.manifest, osm_features=[])
            before = (self.dir / "models" / "t.glb").read_bytes()
            m = plateau_pp.remove_implausible(self.dir, m, osm_features=[])
        self.assertEqual((self.dir / "models" / "t.glb").read_bytes(), before)
        self.assertEqual(len(m["removed_buildings"]), 1)


class Overpass(unittest.TestCase):
    def test_no_public_server_is_ever_called(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                plateau_pp.overpass_endpoint()

    def test_the_own_server_comes_from_the_environment(self):
        with mock.patch.dict(os.environ, {"OVERPASS_URL": "https://example.invalid/api/interpreter"}):
            self.assertEqual(plateau_pp.overpass_endpoint(), "https://example.invalid/api/interpreter")


class RoofTexture(unittest.TestCase):
    def test_bounds_in_local_metres(self):
        e = plateau_pp.roof_texture_entry("r.jpg", [139.0, 35.0, 139.01, 35.01], [139.005, 35.005])
        self.assertAlmostEqual(e["bounds_m"][2] - e["bounds_m"][0], 0.01 * 111320.0 * 0.81915, delta=5)


if __name__ == "__main__":
    unittest.main()
