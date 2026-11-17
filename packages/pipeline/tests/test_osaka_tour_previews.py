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


class OsakaTourVideoTests(unittest.TestCase):
    def test_wide_view_contains_namba_and_cosmosquare_with_margin(self):
        import json
        import math
        tour = json.loads((PROJECT / 'shots/tour.json').read_text(encoding='utf-8'))
        wide = tour['shots'][7]['from']
        self.assertEqual(wide, tour['shots'][7]['to'])
        self.assertEqual(wide['pitch'], 0)
        def mercator(lon, lat):
            return ((lon + 180) / 360, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2)
        cx, cy = mercator(*wide['center'])
        scale = 512 * 2 ** wide['zoom']
        for point in ([135.5011, 34.6661], [135.4122147, 34.6425771]):
            x, y = mercator(*point)
            px, py = 640 + (x - cx) * scale, 360 + (y - cy) * scale
            self.assertTrue(120 < px < 1160 and 120 < py < 600, (point, px, py))

    def test_tour_connects_minami_and_cosmosquare_and_shows_newtram(self):
        import json
        tour = json.loads((PROJECT / 'shots/tour.json').read_text(encoding='utf-8'))
        self.assertEqual(tour['fps'], 24)
        self.assertEqual(len(tour['plateauBuildings']), 2)
        self.assertTrue(all('areas/' in x['manifest'] for x in tour['plateauBuildings']))
        for left, right in zip(tour['shots'], tour['shots'][1:]):
            self.assertEqual(left['to'], right['from'])
        labels = {o.get('text') for shot in tour['shots'] for o in shot.get('overlays', [])}
        self.assertTrue({'心斎橋駅', '道頓堀川', 'なんば駅', 'コスモスクエア駅', 'ニュートラム'} <= labels)
        self.assertNotIn('道頓堀', labels)
        self.assertTrue(any(shot.get('path') == 'fly' for shot in tour['shots']))
        lines = [o for shot in tour['shots'] for o in shot.get('overlays', []) if o.get('type') == 'line']
        self.assertTrue(lines)
        self.assertTrue(all(line['color'] == '#39c7ef' and len(line['coords']) >= 2 for line in lines))


if __name__ == '__main__':
    unittest.main()
