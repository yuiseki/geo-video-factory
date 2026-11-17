import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
PROJECT = ROOT / 'projects/2026/11/17/tour-shisaibashi-dotonbori-cosmosqare'


class OsakaTourPreviewTests(unittest.TestCase):
    def test_two_disjoint_areas_cover_three_subjects(self):
        spec = importlib.util.spec_from_file_location('osaka_preview', PROJECT / 'prepare.py')
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        areas = module.AREAS
        self.assertEqual(set(areas), {'minami', 'cosmosquare'})
        def inside(lon, lat, bbox):
            return bbox[0] < lon < bbox[2] and bbox[1] < lat < bbox[3]
        self.assertTrue(inside(135.5006, 34.6751, areas['minami']))
        self.assertTrue(inside(135.5014, 34.6691, areas['minami']))
        self.assertTrue(inside(135.4122, 34.6426, areas['cosmosquare']))
        self.assertLess(areas['cosmosquare'][2], areas['minami'][0])
        self.assertIn('27100-bldg-maxlod2-2025', module.TILESET)


if __name__ == '__main__':
    unittest.main()
