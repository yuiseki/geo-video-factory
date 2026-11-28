import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import colmap_sfm as cs  # noqa: E402
import sfm_compare as sc  # noqa: E402


def looking(heading_deg):
    h = math.radians(heading_deg)
    return np.stack([[math.cos(h), -math.sin(h), 0.0], [0.0, 0.0, -1.0], [math.sin(h), math.cos(h), 0.0]])


class Georeference(unittest.TestCase):
    def test_sphere_enu_round_trips_through_the_reader(self):
        origin = (139.776, 35.7116)
        e, n = cs.sphere_enu(139.7765, 35.7119, origin)
        lon, lat = sc._sphere_lonlat(e, n, *origin)
        self.assertAlmostEqual(lon, 139.7765, places=9)
        self.assertAlmostEqual(lat, 35.7119, places=9)

    def test_cameras_land_on_their_gps_after_the_fit(self):
        # an SfM frame: scaled by 0.2, turned 40 degrees about up, y pointing down, shifted
        world = {"a.jpg": (0.0, 0.0, looking(0)), "b.jpg": (20.0, 0.0, looking(90)),
                 "c.jpg": (0.0, 30.0, looking(180)), "d.jpg": (15.0, 25.0, looking(270))}
        th = math.radians(40)
        turn = np.array([[math.cos(th), -math.sin(th), 0], [math.sin(th), math.cos(th), 0], [0, 0, 1]])
        flip = np.diag([1.0, -1.0, -1.0])
        a = flip @ turn                     # world -> sfm rotation
        sfm = {}
        for k, (e, n, r) in world.items():
            c_w = np.array([e, n, 1.6])
            sfm[k] = (r @ a.T, 0.2 * a @ c_w + np.array([3.0, -1.0, 7.0]))
        gps = {k: (v[0], v[1]) for k, v in world.items()}
        cams = cs.georeference(sfm, gps, eye_z=1.6)
        for k, (e, n, r) in world.items():
            ce, cn, cu = cams[k]["C"]
            self.assertAlmostEqual(ce, e, places=4)
            self.assertAlmostEqual(cn, n, places=4)
            self.assertAlmostEqual(sc.angle_deg(cams[k]["R"], r), 0, places=4)

    def test_written_model_reads_back(self):
        cams = {"a.jpg": {"R": looking(30), "C": np.array([4.0, -2.0, 1.6])}}
        with tempfile.TemporaryDirectory() as d:
            cs.write_model(Path(d), cams, (139.776, 35.7116))
            got = sc.colmap_cams(Path(d))
        e, n = cs.sphere_enu(*got["a.jpg"]["lonlat"], (139.776, 35.7116))
        self.assertAlmostEqual(e, 4.0, places=4)
        self.assertAlmostEqual(n, -2.0, places=4)
        self.assertAlmostEqual(sc.angle_deg(got["a.jpg"]["R"], looking(30)), 0, places=5)


class Components(unittest.TestCase):
    def test_a_dir_of_models_is_read_as_components(self):
        cams = {"a.jpg": {"R": looking(0), "C": np.zeros(3)}}
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            cs.write_model(d / "0", cams, (139.776, 35.7116))
            cs.write_model(d / "1", {"b.jpg": cams["a.jpg"], "c.jpg": cams["a.jpg"]}, (139.776, 35.7116))
            comps = sc.components(d)
        self.assertEqual(sorted(len(c) for c in comps), [1, 2])


if __name__ == "__main__":
    unittest.main()
