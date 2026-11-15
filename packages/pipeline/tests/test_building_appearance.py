import json
import base64
import struct
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

from support import import_pipeline

appearance = import_pipeline('building_appearance')
plateau_3d = import_pipeline('plateau_3d')


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

    def test_plateau_palette_aligns_orthophoto_colors_to_tile_ids_and_skips_textured_ids(self):
        image = Image.new('RGB', (100, 100), (45, 120, 70))
        draw = ImageDraw.Draw(image)
        draw.rectangle((15, 15, 34, 34), fill=(170, 145, 120))
        draw.rectangle((55, 55, 74, 74), fill=(170, 145, 120))
        footprint = lambda west, south, east, north: {
            'type': 'Polygon',
            'coordinates': [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
        }
        palette = appearance.build_plateau_facade_palette(
            ['gml-a', 'gml-b', 'gml-textured', 'gml-no-footprint'],
            {
                'gml-a': footprint(139.15, 35.65, 139.35, 35.85),
                'gml-b': footprint(139.55, 35.15, 139.75, 35.35),
            },
            image,
            [139, 35, 140, 36],
            textured_ids={'gml-textured'},
            seed='v006',
        )
        self.assertEqual(list(palette), ['gml-a', 'gml-b', 'gml-textured', 'gml-no-footprint'])
        self.assertNotEqual(palette['gml-a'], palette['gml-b'])
        self.assertIsNone(palette['gml-textured'])
        self.assertIsNotNone(palette['gml-no-footprint'], 'missing footprint still needs a deterministic proxy tone')

    def test_glb_batch_ids_map_orthophoto_palette_back_to_untextured_plateau_features(self):
        image = Image.new('RGB', (16, 16), (122, 96, 68))
        json_chunk = json.dumps({
            'asset': {'version': '2.0'},
            'buffers': [{'byteLength': 44}],
            'bufferViews': [
                {'buffer': 0, 'byteOffset': 0, 'byteLength': 24}, {'buffer': 0, 'byteOffset': 24, 'byteLength': 2},
                {'buffer': 0, 'byteOffset': 28, 'byteLength': 12}, {'buffer': 0, 'byteOffset': 40, 'byteLength': 1},
            ],
            'accessors': [
                {'bufferView': 0, 'componentType': 5126, 'count': 2, 'type': 'VEC3'},
                {'bufferView': 1, 'componentType': 5121, 'count': 2, 'type': 'SCALAR'},
                {'bufferView': 2, 'componentType': 5126, 'count': 1, 'type': 'VEC3'},
                {'bufferView': 3, 'componentType': 5121, 'count': 1, 'type': 'SCALAR'},
            ],
            'materials': [{'pbrMetallicRoughness': {}}, {'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}}}],
            'textures': [{'source': 0}],
            'images': [{'uri': 'data:image/png;base64,' + base64.b64encode(b'fake').decode()}],
            'meshes': [{'primitives': [
                {'attributes': {'POSITION': 0, '_BATCHID': 1}, 'material': 0},
                {'attributes': {'POSITION': 2, '_BATCHID': 3}, 'material': 1},
            ]}],
        }, separators=(',', ':')).encode()
        json_chunk += b' ' * ((-len(json_chunk)) % 4)
        binary = struct.pack('<6f', 0, 0, 0, 2, 0, 0) + bytes([0, 1]) + b'\0' * 2
        binary += struct.pack('<3f', 4, 0, 0) + bytes([2]) + b'\0' * 3
        total = 12 + 8 + len(json_chunk) + 8 + len(binary)
        glb = struct.pack('<4sII', b'glTF', 2, total) + struct.pack('<I4s', len(json_chunk), b'JSON') + json_chunk
        glb += struct.pack('<I4s', len(binary), b'BIN\0') + binary
        palette = appearance.infer_glb_facade_colors(
            glb, list(appearance._ecef(139.5, 35.5)), ['gml-a', 'gml-b', 'gml-textured'], image, [139, 35, 140, 36], seed='v006',
        )
        self.assertEqual(palette['gml-textured'], None)
        self.assertTrue(palette['gml-a'].startswith('#'))
        self.assertTrue(palette['gml-b'].startswith('#'))
        self.assertNotEqual(palette['gml-a'], palette['gml-b'])

    def test_apply_orthophoto_palette_persists_colors_in_manifest_id_order(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'models').mkdir()
            (root / 'models' / 'tile.glb').write_bytes(b'glb fixture')
            Image.new('RGB', (2, 2), (110, 120, 130)).save(root / 'ortho.png')
            manifest = {
                'format': 'geo-video-factory.plateau-3d/1',
                'bbox_degrees': [139, 35, 140, 36],
                'tiles': [{'glb': 'models/tile.glb', 'rtc': [1, 2, 3], 'ids': ['gml-a', 'gml-b']}],
            }
            (root / 'manifest.json').write_text(json.dumps(manifest))
            with patch.object(appearance, 'infer_glb_facade_colors', return_value={'gml-a': '#aabbcc', 'gml-b': None}) as infer:
                result = appearance.apply_orthophoto_palette(root, root / 'ortho.png', seed='v006')
            infer.assert_called_once()
            self.assertEqual(result['tiles'][0]['facade_colors'], ['#aabbcc', None])
            self.assertEqual(json.loads((root / 'manifest.json').read_text())['tiles'][0]['facade_colors'], ['#aabbcc', None])

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
            self.assertEqual(len(tile['region']), 6)
            self.assertTrue((Path(directory) / tile['glb']).is_file())
            gltf, _, _ = plateau_3d.glb_chunks((Path(directory) / tile['glb']).read_bytes())
            self.assertTrue(gltf['meshes'][0]['primitives'][0]['attributes'].get('POSITION') is not None)
            self.assertEqual(gltf['materials'][0]['pbrMetallicRoughness']['metallicFactor'], 0)
            self.assertEqual(json.loads((Path(directory) / 'manifest.json').read_text())['proxy_tile_count'], 1)

    def test_osm_proxy_requires_height_or_level_estimate_and_valid_closed_polygon(self):
        invalid = [{
            'type': 'Feature', 'id': 'way/200', 'properties': {},
            'geometry': {'type': 'Polygon', 'coordinates': [[[139.79, 35.70], [139.791, 35.70], [139.791, 35.701], [139.79, 35.70]]]},
        }]
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'height|levels'):
                appearance.build_osm_proxy_tiles(invalid, [139.7, 35.6, 139.9, 35.8], Path(directory))

    def test_osm_proxy_skips_buildings_whose_footprint_contains_a_plateau_building_centroid(self):
        feature = {
            'type': 'Feature', 'id': 'way/300', 'properties': {'height': 12},
            'geometry': {'type': 'Polygon', 'coordinates': [[[139.79, 35.70], [139.7901, 35.70], [139.7901, 35.7001], [139.79, 35.7001], [139.79, 35.70]]]},
        }
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'manifest.json').write_text(json.dumps({
                'format': 'geo-video-factory.plateau-3d/1',
                'bbox_degrees': [139.78, 35.69, 139.80, 35.71],
                'center': [139.79, 35.70],
                'tiles': [{'ids': ['gml-existing'], 'feature_centroids': {'gml-existing': [139.79005, 35.70005]}}],
            }))
            result = appearance.build_osm_proxy_tiles([feature], [139.78, 35.69, 139.80, 35.71], root)
        self.assertEqual(result['tile_count'], 1)
        self.assertEqual(result['proxy_tile_count'], 0)


if __name__ == '__main__':
    unittest.main()
