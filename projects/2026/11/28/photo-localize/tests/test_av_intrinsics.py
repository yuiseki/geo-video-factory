import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import av_intrinsics as ai  # noqa: E402


def sfm(f35_by_view, focal_mm=2.35):
    views = [{"viewId": str(i), "intrinsicId": "7", "width": "1600", "height": "1205",
              "metadata": {"Exif:FocalLength": str(focal_mm), "Exif:FocalLengthIn35mmFilm": str(f)}}
             for i, f in enumerate(f35_by_view)]
    return {"views": views, "intrinsics": [{"intrinsicId": "7", "width": "1600", "height": "1205",
                                            "sensorWidth": "9.79", "sensorHeight": "7.37",
                                            "focalLength": str(focal_mm), "initialFocalLength": str(focal_mm)}]}


class Intrinsics(unittest.TestCase):
    def test_sensor_width_makes_the_35mm_focal_length(self):
        d = ai.fix(sfm([16, 16]))
        i = d["intrinsics"][0]
        f_px = float(i["focalLength"]) / float(i["sensorWidth"]) * 1600
        self.assertAlmostEqual(f_px, 16 / math.hypot(36, 24) * math.hypot(1600, 1205), places=3)
        self.assertAlmostEqual(float(i["sensorHeight"]) / float(i["sensorWidth"]), 1205 / 1600, places=6)

    def test_views_of_different_lenses_in_one_group_get_their_own_intrinsic(self):
        d = ai.fix(sfm([16, 24, 16]))
        ids = [v["intrinsicId"] for v in d["views"]]
        self.assertEqual(ids[0], ids[2])
        self.assertNotEqual(ids[0], ids[1])
        self.assertEqual(len(d["intrinsics"]), 2)


if __name__ == "__main__":
    unittest.main()
