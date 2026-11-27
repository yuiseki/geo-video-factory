"""plateau_building: one PLATEAU building's own triangles, by gml_id, from the PLATEAU++ tile store."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from support import import_pipeline

pb = import_pipeline("buildings.plateau_building")
pm = import_pipeline("buildings.plateau_mesh")
from test_glb_strip import POINTS, draco_glb, plain_glb  # noqa: E402  (needs the pipeline on the path)

RTC = [-3959000.0, 3345000.0, 3704000.0]


def expected(feature):
    """ECEF of the given feature's triangle: tiles are y-up around their RTC centre."""
    p = POINTS[3 * feature:3 * feature + 3].astype(float)
    return np.c_[RTC[0] + p[:, 0], RTC[1] - p[:, 2], RTC[2] + p[:, 1]]


class FeatureTriangles(unittest.TestCase):
    def test_only_the_wanted_buildings_triangles_come_out(self):
        for make in (plain_glb, draco_glb):
            with self.subTest(glb=make.__name__):
                got = pb.feature_triangles(make(), RTC, ["a", "b"], {"b"})
                self.assertEqual(list(got), ["b"])
                self.assertEqual(got["b"].shape, (1, 3, 3))
                self.assertTrue(np.allclose(got["b"][0], expected(1), atol=1e-3))


class FromStore(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        tiles = self.root / "plateau" / "ab"
        tiles.mkdir(parents=True)
        (tiles / "ab12.glb").write_bytes(draco_glb())
        (tiles / "ab12.json").write_text(json.dumps({"glb": "plateau/ab/ab12.glb", "rtc": RTC, "ids": ["a", "b"]}))
        env = mock.patch.dict(os.environ, {"GEO_VIDEO_CACHE": str(self.root.parent)})
        env.start()
        self.addCleanup(env.stop)

    def test_a_building_is_found_by_its_id_and_put_in_the_local_frame(self):
        lon, lat = 139.79, 35.70
        got = pb.building_triangles(["b"], (lon, lat), store=self.root)
        origin, frame = pm.enu_frame(lon, lat)
        self.assertTrue(np.allclose(got["b"][0], (expected(1) - origin) @ frame.T, atol=1e-3))

    def test_an_id_no_tile_holds_is_an_error_not_an_empty_building(self):
        with self.assertRaises(KeyError):
            pb.building_triangles(["nowhere"], (139.79, 35.70), store=self.root)


class RoofLevels(unittest.TestCase):
    def test_the_levels_are_listed_from_the_top_with_their_corners(self):
        box = []
        for z in (10.0, 25.0):            # a low wing and a tall block on it
            box += [[[0, 0, z], [8, 0, z], [8, 6, z]], [[0, 0, z], [8, 6, z], [0, 6, z]]]
        levels = pb.roof_levels(np.array(box, float))
        self.assertEqual([lv["z"] for lv in levels], [25.0, 10.0])
        self.assertEqual(sorted(map(tuple, levels[0]["corners"])), [(0, 0), (0, 6), (8, 0), (8, 6)])


if __name__ == "__main__":
    unittest.main()
