import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
PROJECT = ROOT / 'projects/2026/11/17/tour-asakusa-ryogoku'


class AsakusaRyogokuTourTests(unittest.TestCase):
    def test_tour_uses_sota_manifest_and_follows_existing_river_route(self):
        tour = json.loads((PROJECT / 'shots/tour.json').read_text(encoding='utf-8'))
        baseline = json.loads((ROOT / 'packages/renderer/test/fixtures/buildings-asakusa-sumida-river.json').read_text(encoding='utf-8'))
        self.assertEqual(tour['plateauBuildings']['manifest'], 'assets/city/manifest.json')
        self.assertEqual(tour['plateauBuildings']['heightOffset'], -39)
        self.assertEqual([shot['from']['center'] for shot in tour['shots']], [shot['from']['center'] for shot in baseline['shots']])
        self.assertEqual([shot['to']['center'] for shot in tour['shots'][:-1]], [shot['to']['center'] for shot in baseline['shots'][:-1]])
        self.assertEqual(tour['shots'][-1]['to']['center'], [139.7912, 35.6925])
        self.assertLessEqual(tour['shots'][-1]['to']['zoom'], 15.5)
        names = {o.get('text') for shot in tour['shots'] for o in shot.get('overlays', [])}
        self.assertTrue({'浅草寺', '東武 浅草駅', '吾妻橋', '隅田川', '両国国技館'} <= names)


if __name__ == '__main__':
    unittest.main()
