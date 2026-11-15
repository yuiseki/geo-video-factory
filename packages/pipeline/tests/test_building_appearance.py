import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

from support import import_pipeline

appearance = import_pipeline('building_appearance')


class BuildingAppearanceTests(unittest.TestCase):
    def test_samples_orthophoto_color_inside_building_polygon(self):
        image = Image.new('RGB', (100, 100), (36, 118, 74))
        ImageDraw.Draw(image).rectangle((30, 30, 69, 69), fill=(184, 132, 92))
        color = appearance.sample_polygon_color(
            image,
            [[139.4, 35.4], [139.6, 35.4], [139.6, 35.6], [139.4, 35.6], [139.4, 35.4]],
            [139, 35, 140, 36],
        )
        self.assertEqual(color, (184, 132, 92))

    def test_untextured_facades_get_deterministic_varied_colors_and_textured_models_keep_texture(self):
        buildings = [
            {'id': 'plateau-a', 'textured': False, 'ortho_color': [180, 170, 155]},
            {'id': 'plateau-b', 'textured': False, 'ortho_color': [180, 170, 155]},
            {'id': 'plateau-c', 'textured': False, 'ortho_color': [180, 170, 155]},
            {'id': 'plateau-textured', 'textured': True, 'ortho_color': [180, 170, 155], 'texture': 'facade.webp'},
        ]
        first = appearance.assign_facade_colors(buildings, seed='ryogoku-v006')
        second = appearance.assign_facade_colors(buildings, seed='ryogoku-v006')
        colors = [item['facade_color'] for item in first[:3]]
        self.assertEqual(first, second, 'palette assignment must be reproducible')
        self.assertEqual(len(set(colors)), 3, 'adjacent untextured buildings should not collapse to one flat color')
        self.assertTrue(all(isinstance(color, str) and color.startswith('#') for color in colors))
        self.assertNotIn('facade_color', first[3], 'textured PLATEAU must retain its source texture/material')
        self.assertEqual(first[3]['texture'], 'facade.webp')

    def test_osm_proxy_emits_renderer_compatible_glb_tiles_and_excludes_plateau_ids(self):
        features = [
            {
                'type': 'Feature',
                'id': 'way/100',
                'properties': {'height': 18, 'building': 'apartments'},
                'geometry': {'type': 'Polygon', 'coordinates': [[[139.79, 35.70], [139.7901, 35.70], [139.7901, 35.7001], [139.79, 35.7001], [139.79, 35.70]]]},
            },
            {
                'type': 'Feature',
                'id': 'way/101',
                'properties': {'building:levels': 4},
                'geometry': {'type': 'Polygon', 'coordinates': [[[139.791, 35.70], [139.7911, 35.70], [139.7911, 35.7001], [139.791, 35.7001], [139.791, 35.70]]]},
            },
        ]
        with TemporaryDirectory() as directory:
            result = appearance.build_osm_proxy_tiles(
                features,
                [139.78, 35.69, 139.80, 35.71],
                Path(directory),
                plateau_ids={'way/101'},
            )
            self.assertEqual(result['format'], 'geo-video-factory.plateau-3d/1')
            self.assertEqual(result['tile_count'], 1)
            self.assertEqual(result['proxy_tile_count'], 1)
            tile = result['tiles'][0]
            self.assertTrue({'source', 'glb', 'rtc', 'ids', 'sha256'} <= tile.keys())
            self.assertEqual(tile['source'], 'osm://way/100')
            self.assertEqual(tile['ids'], ['way/100'])
            self.assertEqual(len(tile['rtc']), 3)
            self.assertTrue((Path(directory) / tile['glb']).is_file())
            self.assertEqual(json.loads((Path(directory) / 'manifest.json').read_text())['proxy_tile_count'], 1)

    def test_osm_proxy_requires_height_or_level_estimate_and_valid_closed_polygon(self):
        invalid = [{
            'type': 'Feature', 'id': 'way/200', 'properties': {},
            'geometry': {'type': 'Polygon', 'coordinates': [[[139.79, 35.70], [139.791, 35.70], [139.79, 35.70]]]},
        }]
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'height|levels'):
                appearance.build_osm_proxy_tiles(invalid, [139.7, 35.6, 139.9, 35.8], Path(directory))


if __name__ == '__main__':
    unittest.main()
