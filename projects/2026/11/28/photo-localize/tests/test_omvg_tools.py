import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import colmap_sfm as cs  # noqa: E402
import omvg_tools as ot  # noqa: E402
import sfm_compare as sc  # noqa: E402


def looking(heading_deg):
    h = math.radians(heading_deg)
    return np.stack([[math.cos(h), -math.sin(h), 0.0], [0.0, 0.0, -1.0], [math.sin(h), math.cos(h), 0.0]])


class Geodesy(unittest.TestCase):
    def test_ecef_round_trip(self):
        x = ot.lla_to_ecef(139.776, 35.7116, 40.0)
        lon, lat, alt = ot.ecef_to_lla(*x)
        self.assertAlmostEqual(lon, 139.776, places=9)
        self.assertAlmostEqual(lat, 35.7116, places=9)
        self.assertAlmostEqual(alt, 40.0, places=4)

    def test_enu_axes(self):
        m = ot.ecef_to_enu_rotation(139.776, 35.7116)
        up = m.T @ np.array([0, 0, 1.0])
        x = ot.lla_to_ecef(139.776, 35.7116, 0.0)
        np.testing.assert_allclose(up, x / np.linalg.norm(x), atol=3e-3)   # geodetic vs geocentric up


class ModelToEnu(unittest.TestCase):
    def test_an_ecef_model_becomes_an_enu_model(self):
        origin = (139.776, 35.7116)
        m = ot.ecef_to_enu_rotation(*origin)
        x0 = ot.lla_to_ecef(*origin, 0.0)
        r_enu = looking(60)
        c_enu = np.array([12.0, -5.0, 1.6])
        cams = {"a.jpg": {"R": r_enu @ m, "C": x0 + m.T @ c_enu}}        # the same camera written in ECEF
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            cs.write_model(d / "ecef", cams, None)
            ot.ecef_model_to_enu(d / "ecef", d / "enu")
            got = sc.components(d / "enu")[0]["a.jpg"]
        e, n = cs.sphere_enu(*got["lonlat"], origin)
        self.assertAlmostEqual(e, 12.0, delta=0.05)
        self.assertAlmostEqual(n, -5.0, delta=0.05)
        self.assertAlmostEqual(sc.angle_deg(got["R"], r_enu), 0, delta=0.01)


class Focals(unittest.TestCase):
    def test_each_view_gets_the_focal_of_its_35mm_equivalent(self):
        data = {"views": [{"key": 0, "value": {"ptr_wrapper": {"data": {
                    "filename": "001.jpg", "width": 1600, "height": 1205, "id_intrinsic": 0}}}}],
                "intrinsics": [{"key": 0, "value": {"ptr_wrapper": {"data": {"focal_length": 1111.0}}}}]}
        ot.set_focals(data, {"001.jpg": 16.0})
        f = data["intrinsics"][0]["value"]["ptr_wrapper"]["data"]["focal_length"]
        self.assertAlmostEqual(f, 16 / math.hypot(36, 24) * math.hypot(1600, 1205), places=6)


if __name__ == "__main__":
    unittest.main()
