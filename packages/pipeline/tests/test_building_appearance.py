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
    def test_citygml_colors_fill_missing_tile_palette_in_id_order(self):
        features = [{'type': 'Feature', 'id': 'b', 'properties': {'color': '#81909a'}},
                    {'type': 'Feature', 'id': 'a', 'properties': {'color': '#987654'}}]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'manifest.json').write_text(json.dumps({'tiles': [
                {'ids': ['a', 'b', 'c'], 'facade_colors': ['#123456', None, None]},
                {'ids': ['b', 'a']},
            ]}))
            result = appearance.apply_citygml_colors(root, features)
        self.assertEqual(result['tiles'][0]['facade_colors'], ['#123456', '#81909a', None])
        self.assertEqual(result['tiles'][1]['facade_colors'], ['#81909a', '#987654'])

    def test_citygml_and_orthophoto_harmonization_suppress_bright_white_green_and_purple_casts(self):
        features = [
            {'type': 'Feature', 'id': 'bldg-bright', 'properties': {'sampled': True, 'color': '#e7ebe2'}},
            {'type': 'Feature', 'id': 'bldg-green', 'properties': {'sampled': True, 'color': '#5c6f5b'}},
            {'type': 'Feature', 'id': 'bldg-purple', 'properties': {'sampled': False, 'color': '#b9a6c8'}},
        ]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'manifest.json').write_text(json.dumps({
                'tiles': [{'ids': ['bldg-bright', 'bldg-green', 'bldg-purple']}],
            }))
            result = appearance.apply_citygml_colors(root, features)
        colors = result['tiles'][0]['facade_colors']
        for hex_color in colors:
            r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
            self.assertLessEqual(max(r, g, b), 175, f'{hex_color} is too bright and washes out under directional light')
            self.assertLessEqual(g, max(r, b) + 3, f'{hex_color} has an unnatural green cast')
            self.assertFalse(r > g + 6 and b > g + 6, f'{hex_color} has an unnatural purple/magenta cast')

    def test_osm_overlap_uses_footprint_area_not_a_centroid(self):
        def feature(identifier, west, east):
            return {'type': 'Feature', 'id': identifier, 'properties': {'height': 9}, 'geometry': {
                'type': 'Polygon', 'coordinates': [[[west, 35.70], [east, 35.70], [east, 35.701], [west, 35.701], [west, 35.70]]]}}
        osm = [feature('way/overlap', 139.79, 139.80), feature('way/small', 139.81, 139.82)]
        footprints = [feature('gml/a', 139.798, 139.801), feature('gml/b', 139.8195, 139.821)]
        with TemporaryDirectory() as directory:
            result = appearance.build_osm_proxy_tiles(osm, [139.78, 35.69, 139.83, 35.71], Path(directory), plateau_footprints=footprints)
        self.assertEqual(result['tiles'][-1]['ids'], ['way/small'])

    def test_palette_terminates_when_many_buildings_share_the_same_source_color(self):
        buildings = [{'id': str(index), 'ortho_color': [183, 174, 159]} for index in range(500)]
        with patch.object(appearance, '_varied_color', return_value='#888888') as color:
            result = appearance.assign_facade_colors(buildings)
        self.assertEqual(len(result), len(buildings))
        self.assertLess(color.call_count, len(buildings) * 20)

    def test_citygml_fallback_adds_only_missing_ids_as_ground_based_proxy(self):
        ring = [[139.79, 35.70], [139.7901, 35.70], [139.7901, 35.7001], [139.79, 35.7001], [139.79, 35.70]]
        features = [
            {'type': 'Feature', 'id': identifier, 'properties': {'height': 8, 'color': '#8c9596'},
             'geometry': {'type': 'Polygon', 'coordinates': [ring]}}
            for identifier in ('bldg-existing', 'bldg-missing')
        ]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'manifest.json').write_text(json.dumps({
                'format': 'geo-video-factory.plateau-3d/1', 'center': [139.79, 35.70],
                'tiles': [{'ids': ['bldg-existing'], 'feature_centroids': {'bldg-existing': [139.79005, 35.70005]}}],
            }))
            result = appearance.build_osm_proxy_tiles(features, [139.78, 35.69, 139.80, 35.71], root, kind='citygml-proxy')
            self.assertEqual(result['tiles'][-1]['kind'], 'citygml-proxy')
            self.assertEqual(result['tiles'][-1]['ids'], ['bldg-missing'])
            self.assertEqual(result['tiles'][-1]['facade_colors'], ['#8c9596'])
            self.assertEqual(result['citygml_proxy_building_count'], 1)

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

    def test_mixed_textured_and_untextured_feature_still_receives_facade_color(self):
        image = Image.new('RGB', (16, 16), (140, 110, 85))
        json_chunk = json.dumps({
            'asset': {'version': '2.0'},
            'buffers': [{'byteLength': 48}],
            'bufferViews': [
                {'buffer': 0, 'byteOffset': 0, 'byteLength': 12}, {'buffer': 0, 'byteOffset': 12, 'byteLength': 1},
                {'buffer': 0, 'byteOffset': 16, 'byteLength': 24}, {'buffer': 0, 'byteOffset': 40, 'byteLength': 2},
            ],
            'accessors': [
                {'bufferView': 0, 'componentType': 5126, 'count': 1, 'type': 'VEC3'},
                {'bufferView': 1, 'componentType': 5121, 'count': 1, 'type': 'SCALAR'},
                {'bufferView': 2, 'componentType': 5126, 'count': 2, 'type': 'VEC3'},
                {'bufferView': 3, 'componentType': 5121, 'count': 2, 'type': 'SCALAR'},
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
        binary = struct.pack('<3f', 0, 0, 0) + bytes([0]) + b'\0' * 3
        binary += struct.pack('<6f', 2, 0, 0, 4, 0, 0) + bytes([0, 1]) + b'\0' * 2
        total = 12 + 8 + len(json_chunk) + 8 + len(binary)
        glb = struct.pack('<4sII', b'glTF', 2, total) + struct.pack('<I4s', len(json_chunk), b'JSON') + json_chunk
        glb += struct.pack('<I4s', len(binary), b'BIN\0') + binary
        palette = appearance.infer_glb_facade_colors(
            glb, list(appearance._ecef(139.5, 35.5)), ['gml-mixed', 'gml-fully-textured'], image, [139, 35, 140, 36], seed='v006',
        )
        self.assertIsNotNone(palette['gml-mixed'])
        self.assertTrue(palette['gml-mixed'].startswith('#'))
        self.assertIsNone(palette['gml-fully-textured'])

    def test_infer_glb_facade_colors_samples_footprint_polygon_not_only_centroid(self):
        image = Image.new('RGB', (100, 100), (190, 150, 110))
        # Paint a narrow dark shadow/road strip right across the centroid (x=45..55, y=45..55)
        ImageDraw.Draw(image).rectangle((45, 45, 55, 55), fill=(30, 60, 180))
        rtc = list(appearance._ecef(139.5, 35.5))
        # 4 corners around the center (~ +/- 0.25 deg in local meters: ~22km, here use 0.2 deg in meters)
        east_pt = appearance._ecef(139.7, 35.5)
        west_pt = appearance._ecef(139.3, 35.5)
        north_pt = appearance._ecef(139.5, 35.7)
        south_pt = appearance._ecef(139.5, 35.3)
        # Convert ECEF to GLB local: (dx, dz, -dy)
        to_local = lambda pt: (pt[0] - rtc[0], pt[2] - rtc[2], -(pt[1] - rtc[1]))
        verts = [to_local(east_pt), to_local(north_pt), to_local(west_pt), to_local(south_pt)]
        binary = b''.join(struct.pack('<3f', *v) for v in verts) + bytes([0, 0, 0, 0])
        json_chunk = json.dumps({
            'asset': {'version': '2.0'},
            'buffers': [{'byteLength': len(binary)}],
            'bufferViews': [
                {'buffer': 0, 'byteOffset': 0, 'byteLength': 48},
                {'buffer': 0, 'byteOffset': 48, 'byteLength': 4},
            ],
            'accessors': [
                {'bufferView': 0, 'componentType': 5126, 'count': 4, 'type': 'VEC3'},
                {'bufferView': 1, 'componentType': 5121, 'count': 4, 'type': 'SCALAR'},
            ],
            'materials': [{'pbrMetallicRoughness': {}}],
            'meshes': [{'primitives': [{'attributes': {'POSITION': 0, '_BATCHID': 1}, 'material': 0}]}],
        }, separators=(',', ':')).encode()
        json_chunk += b' ' * ((-len(json_chunk)) % 4)
        total = 12 + 8 + len(json_chunk) + 8 + len(binary)
        glb = struct.pack('<4sII', b'glTF', 2, total) + struct.pack('<I4s', len(json_chunk), b'JSON') + json_chunk + struct.pack('<I4s', len(binary), b'BIN\0') + binary
        palette = appearance.infer_glb_facade_colors(
            glb, rtc, ['gml-footprint'], image, [139.0, 35.0, 140.0, 36.0], seed='v006',
        )
        color = palette['gml-footprint']
        r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
        self.assertGreater(r, b, f'footprint sampling should reflect roof (190,150,110) not centroid strip (30,60,180): got {color}')

    def test_infer_glb_facade_colors_supports_feature_id_0_and_draco_without_buffer_views(self):
        image = Image.new('RGB', (16, 16), (130, 120, 110))
        rtc = list(appearance._ecef(139.5, 35.5))
        # Case 1: _FEATURE_ID_0 attribute
        binary = struct.pack('<6f', 0, 0, 0, 2, 0, 0) + bytes([0, 1]) + b'\0' * 2
        json_chunk = json.dumps({
            'asset': {'version': '2.0'},
            'buffers': [{'byteLength': len(binary)}],
            'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': 24}, {'buffer': 0, 'byteOffset': 24, 'byteLength': 2}],
            'accessors': [
                {'bufferView': 0, 'componentType': 5126, 'count': 2, 'type': 'VEC3'},
                {'bufferView': 1, 'componentType': 5121, 'count': 2, 'type': 'SCALAR'},
            ],
            'materials': [{'pbrMetallicRoughness': {}}],
            'meshes': [{'primitives': [{'attributes': {'POSITION': 0, '_FEATURE_ID_0': 1}, 'material': 0}]}],
        }, separators=(',', ':')).encode()
        json_chunk += b' ' * ((-len(json_chunk)) % 4)
        total = 12 + 8 + len(json_chunk) + 8 + len(binary)
        glb_feat = struct.pack('<4sII', b'glTF', 2, total) + struct.pack('<I4s', len(json_chunk), b'JSON') + json_chunk + struct.pack('<I4s', len(binary), b'BIN\0') + binary
        palette = appearance.infer_glb_facade_colors(glb_feat, rtc, ['gml-0', 'gml-1'], image, [139, 35, 140, 36], seed='v006')
        self.assertTrue(palette['gml-0'].startswith('#'))
        self.assertTrue(palette['gml-1'].startswith('#'))
        self.assertNotEqual(palette['gml-0'], palette['gml-1'])

        # Case 2: Draco compressed primitive where accessors omit bufferView
        draco_doc = {
            'asset': {'version': '2.0'},
            'extensionsUsed': ['KHR_draco_mesh_compression'],
            'accessors': [
                {'componentType': 5126, 'count': 3, 'type': 'VEC3'},
                {'componentType': 5121, 'count': 3, 'type': 'SCALAR'},
            ],
            'materials': [{'pbrMetallicRoughness': {}}],
            'meshes': [{'primitives': [{'attributes': {'POSITION': 0, '_BATCHID': 1}, 'material': 0, 'extensions': {'KHR_draco_mesh_compression': {'bufferView': 0}}}]}],
        }
        draco_json = json.dumps(draco_doc, separators=(',', ':')).encode()
        draco_json += b' ' * ((-len(draco_json)) % 4)
        glb_draco = struct.pack('<4sII', b'glTF', 2, 20 + len(draco_json)) + struct.pack('<I4s', len(draco_json), b'JSON') + draco_json
        draco_palette = appearance.infer_glb_facade_colors(glb_draco, rtc, ['gml-d0', 'gml-d1'], image, [139, 35, 140, 36], seed='v006')
        self.assertTrue(draco_palette['gml-d0'].startswith('#'))
        self.assertTrue(draco_palette['gml-d1'].startswith('#'))

    def test_integration_manifest_combines_textured_plateau_untextured_plateau_and_osm_proxy(self):
        rtc = list(appearance._ecef(139.79, 35.70))
        # 1 textured PLATEAU feature (id 0) + 2 untextured PLATEAU features (ids 1, 2)
        binary = struct.pack('<3f', 0, 0, 0) + bytes([0, 0, 0, 0])
        binary += struct.pack('<6f', 20, 0, 0, -20, 0, 0) + bytes([1, 2]) + b'\0' * 2
        doc = {
            'asset': {'version': '2.0'},
            'buffers': [{'byteLength': len(binary)}],
            'bufferViews': [
                {'buffer': 0, 'byteOffset': 0, 'byteLength': 12}, {'buffer': 0, 'byteOffset': 12, 'byteLength': 1},
                {'buffer': 0, 'byteOffset': 16, 'byteLength': 24}, {'buffer': 0, 'byteOffset': 40, 'byteLength': 2},
            ],
            'accessors': [
                {'bufferView': 0, 'componentType': 5126, 'count': 1, 'type': 'VEC3'},
                {'bufferView': 1, 'componentType': 5121, 'count': 1, 'type': 'SCALAR'},
                {'bufferView': 2, 'componentType': 5126, 'count': 2, 'type': 'VEC3'},
                {'bufferView': 3, 'componentType': 5121, 'count': 2, 'type': 'SCALAR'},
            ],
            'materials': [{'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}}}, {'pbrMetallicRoughness': {}}],
            'textures': [{'source': 0}],
            'images': [{'uri': 'data:image/png;base64,' + base64.b64encode(b'fake').decode()}],
            'meshes': [{'primitives': [
                {'attributes': {'POSITION': 0, '_BATCHID': 1}, 'material': 0},
                {'attributes': {'POSITION': 2, '_BATCHID': 3}, 'material': 1},
            ]}],
        }
        json_chunk = json.dumps(doc, separators=(',', ':')).encode()
        json_chunk += b' ' * ((-len(json_chunk)) % 4)
        total = 12 + 8 + len(json_chunk) + 8 + len(binary)
        glb = struct.pack('<4sII', b'glTF', 2, total) + struct.pack('<I4s', len(json_chunk), b'JSON') + json_chunk + struct.pack('<I4s', len(binary), b'BIN\0') + binary
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'models').mkdir()
            (root / 'models' / 'plateau.glb').write_bytes(glb)
            ortho_path = root / 'ortho.png'
            Image.new('RGB', (32, 32), (165, 130, 105)).save(ortho_path)
            manifest = {
                'format': 'geo-video-factory.plateau-3d/1',
                'bbox_degrees': [139.78, 35.69, 139.80, 35.71],
                'center': [139.79, 35.70],
                'tiles': [{'glb': 'models/plateau.glb', 'rtc': rtc, 'ids': ['gml-tex', 'gml-u1', 'gml-u2']}],
            }
            (root / 'manifest.json').write_text(json.dumps(manifest))
            appearance.apply_orthophoto_palette(root, ortho_path, seed='ryogoku')
            osm_features = [{
                'type': 'Feature', 'id': 'way/osm-1', 'properties': {'height': 14},
                'geometry': {'type': 'Polygon', 'coordinates': [[[139.792, 35.702], [139.793, 35.702], [139.793, 35.703], [139.792, 35.703], [139.792, 35.702]]]},
            }]
            with Image.open(ortho_path) as ortho:
                final = appearance.build_osm_proxy_tiles(osm_features, [139.78, 35.69, 139.80, 35.71], root, orthophoto=ortho, seed='ryogoku')
            self.assertEqual(final['tile_count'], 2)
            self.assertEqual(final['proxy_tile_count'], 1)
            self.assertIsNone(final['tiles'][0]['facade_colors'][0])
            self.assertTrue(final['tiles'][0]['facade_colors'][1].startswith('#'))
            self.assertTrue(final['tiles'][0]['facade_colors'][2].startswith('#'))
            self.assertNotEqual(final['tiles'][0]['facade_colors'][1], final['tiles'][0]['facade_colors'][2])
            self.assertEqual(final['tiles'][1]['ids'], ['way/osm-1'])
            self.assertTrue(final['tiles'][1]['facade_colors'][0].startswith('#'))

    def test_b3dm_rtc_and_native_glb_node_translation_produce_identical_centroids_and_colors(self):
        rtc_ecef = appearance._ecef(139.79, 35.70)
        # Displace 10m east, 10m north, 10m up using ECEF->local glTF [dx, dz, -dy]
        p_east_north_up = appearance._ecef(139.79011, 35.70009, 10.0)
        dx, dy, dz = (p_east_north_up[i] - rtc_ecef[i] for i in range(3))
        local_verts = [(0.0, 0.0, 0.0), (dx, dz, -dy)]

        def make_glb(node_spec):
            binary = b''.join(struct.pack('<3f', *v) for v in local_verts) + bytes([0, 0, 0, 0])
            doc = {
                'asset': {'version': '2.0'},
                'scene': 0, 'scenes': [{'nodes': [0]}],
                'nodes': [node_spec],
                'buffers': [{'byteLength': len(binary)}],
                'bufferViews': [
                    {'buffer': 0, 'byteOffset': 0, 'byteLength': 24},
                    {'buffer': 0, 'byteOffset': 24, 'byteLength': 2},
                ],
                'accessors': [
                    {'bufferView': 0, 'componentType': 5126, 'count': 2, 'type': 'VEC3'},
                    {'bufferView': 1, 'componentType': 5121, 'count': 2, 'type': 'SCALAR'},
                ],
                'materials': [{'pbrMetallicRoughness': {}}],
                'meshes': [{'primitives': [{'attributes': {'POSITION': 0, '_BATCHID': 1}, 'material': 0}]}],
            }
            jc = json.dumps(doc, separators=(',', ':')).encode()
            jc += b' ' * ((-len(jc)) % 4)
            return struct.pack('<4sII', b'glTF', 2, 12 + 8 + len(jc) + 8 + len(binary)) + struct.pack('<I4s', len(jc), b'JSON') + jc + struct.pack('<I4s', len(binary), b'BIN\0') + binary

        b3dm_glb = make_glb({'mesh': 0})
        native_glb = make_glb({'mesh': 0, 'translation': [rtc_ecef[0], rtc_ecef[2], -rtc_ecef[1]]})

        c_b3dm = appearance.extract_glb_feature_centroids(b3dm_glb, list(rtc_ecef), ['bldg-1'])
        c_native = appearance.extract_glb_feature_centroids(native_glb, [0.0, 0.0, 0.0], ['bldg-1'])
        self.assertAlmostEqual(c_b3dm['bldg-1'][0], c_native['bldg-1'][0], places=6)
        self.assertAlmostEqual(c_b3dm['bldg-1'][1], c_native['bldg-1'][1], places=6)
        self.assertAlmostEqual(c_native['bldg-1'][0], 139.790055, places=4)
        self.assertAlmostEqual(c_native['bldg-1'][1], 35.700045, places=4)

        image = Image.new('RGB', (32, 32), (140, 125, 110))
        bbox = [139.78, 35.69, 139.80, 35.71]
        pal_b3dm = appearance.infer_glb_facade_colors(b3dm_glb, list(rtc_ecef), ['bldg-1'], image, bbox, seed='v1')
        pal_native = appearance.infer_glb_facade_colors(native_glb, [0.0, 0.0, 0.0], ['bldg-1'], image, bbox, seed='v1')
        self.assertEqual(pal_b3dm, pal_native)

    def test_draco_compressed_glb_decodes_positions_and_batch_ids_for_centroids_and_colors(self):
        import DracoPy
        import numpy as np
        rtc_ecef = appearance._ecef(139.79, 35.70)
        # Building 0 at (-0.005, -0.005) deg offset from center; Building 1 at (+0.005, +0.005) deg offset
        p0 = appearance._ecef(139.785, 35.695)
        p1 = appearance._ecef(139.795, 35.705)
        d0 = [p0[0] - rtc_ecef[0], p0[2] - rtc_ecef[2], -(p0[1] - rtc_ecef[1])]
        d1 = [p1[0] - rtc_ecef[0], p1[2] - rtc_ecef[2], -(p1[1] - rtc_ecef[1])]
        pts = np.array([
            d0, [d0[0] + 10, d0[1], d0[2]], [d0[0], d0[1], d0[2] + 10],
            d1, [d1[0] + 10, d1[1], d1[2]], [d1[0], d1[1], d1[2] + 10],
        ], dtype=np.float32)
        faces = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.uint32)
        batch_ids = np.array([[0], [0], [0], [1], [1], [1]], dtype=np.uint8)
        draco_bytes = DracoPy.encode(pts, faces, quantization_bits=16, generic_attributes={1: batch_ids})
        decoded = DracoPy.decode(draco_bytes)
        pos_uid = next(attr['unique_id'] for attr in decoded.attributes if attr['attribute_type'] == 0)
        bid_uid = next(attr['unique_id'] for attr in decoded.attributes if attr['unique_id'] != pos_uid)
        doc = {
            'asset': {'version': '2.0'},
            'extensionsUsed': ['KHR_draco_mesh_compression'],
            'buffers': [{'byteLength': len(draco_bytes)}],
            'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(draco_bytes)}],
            'accessors': [
                {'componentType': 5126, 'count': 6, 'type': 'VEC3'},
                {'componentType': 5121, 'count': 6, 'type': 'SCALAR'},
            ],
            'materials': [{'pbrMetallicRoughness': {}}],
            'meshes': [{'primitives': [{
                'attributes': {'POSITION': 0, '_BATCHID': 1},
                'material': 0,
                'extensions': {'KHR_draco_mesh_compression': {
                    'bufferView': 0,
                    'attributes': {'POSITION': pos_uid, '_BATCHID': bid_uid},
                }},
            }]}],
        }
        jc = json.dumps(doc, separators=(',', ':')).encode()
        jc += b' ' * ((-len(jc)) % 4)
        bin_pad = draco_bytes + b'\0' * ((-len(draco_bytes)) % 4)
        glb = struct.pack('<4sII', b'glTF', 2, 12 + 8 + len(jc) + 8 + len(bin_pad)) + struct.pack('<I4s', len(jc), b'JSON') + jc + struct.pack('<I4s', len(bin_pad), b'BIN\0') + bin_pad

        centroids = appearance.extract_glb_feature_centroids(glb, list(rtc_ecef), ['gml-d0', 'gml-d1'])
        self.assertIn('gml-d0', centroids)
        self.assertIn('gml-d1', centroids)
        self.assertAlmostEqual(centroids['gml-d0'][0], 139.785, places=3)
        self.assertAlmostEqual(centroids['gml-d1'][0], 139.795, places=3)

        image = Image.new('RGB', (100, 100), (40, 40, 40))
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 60, 40, 90), fill=(210, 70, 60))   # SW quadrant -> gml-d0
        draw.rectangle((60, 10, 90, 40), fill=(60, 110, 210))  # NE quadrant -> gml-d1
        palette = appearance.infer_glb_facade_colors(glb, list(rtc_ecef), ['gml-d0', 'gml-d1'], image, [139.78, 35.69, 139.80, 35.71], seed='v1')
        r0, _, b0 = (int(palette['gml-d0'][i:i + 2], 16) for i in (1, 3, 5))
        r1, _, b1 = (int(palette['gml-d1'][i:i + 2], 16) for i in (1, 3, 5))
        self.assertGreater(r0, b0)
        self.assertGreater(b1, r1)

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
            self.assertTrue(gltf['meshes'][0]['primitives'][0]['attributes'].get('_BATCHID') is not None)
            self.assertEqual(tile['facade_colors'], [appearance.assign_facade_colors([{'id': 'way/100', 'ortho_color': [183, 174, 159]}], seed='geo-video-factory')[0]['facade_color']])
            self.assertEqual(gltf['materials'][0]['pbrMetallicRoughness']['metallicFactor'], 0)
            self.assertEqual(json.loads((Path(directory) / 'manifest.json').read_text())['proxy_tile_count'], 1)

    def test_osm_proxy_uses_orthophoto_color_in_facade_colors_and_batch_ids(self):
        features = [
            {
                'type': 'Feature', 'id': 'way/400', 'properties': {'height': 10},
                'geometry': {'type': 'Polygon', 'coordinates': [[[139.2, 35.7], [139.3, 35.7], [139.3, 35.8], [139.2, 35.8], [139.2, 35.7]]]},
            },
            {
                'type': 'Feature', 'id': 'way/401', 'properties': {'height': 15},
                'geometry': {'type': 'Polygon', 'coordinates': [[[139.7, 35.2], [139.8, 35.2], [139.8, 35.3], [139.7, 35.3], [139.7, 35.2]]]},
            },
        ]
        image = Image.new('RGB', (100, 100), (40, 40, 40))
        draw = ImageDraw.Draw(image)
        draw.rectangle((15, 15, 35, 35), fill=(210, 80, 70))
        draw.rectangle((65, 65, 85, 85), fill=(70, 110, 200))
        with TemporaryDirectory() as directory:
            result = appearance.build_osm_proxy_tiles(features, [139.0, 35.0, 140.0, 36.0], Path(directory), orthophoto=image, seed='v006')
            tile = result['tiles'][0]
            self.assertEqual(len(tile['facade_colors']), 2)
            r0, g0, b0 = (int(tile['facade_colors'][0][i:i + 2], 16) for i in (1, 3, 5))
            r1, g1, b1 = (int(tile['facade_colors'][1][i:i + 2], 16) for i in (1, 3, 5))
            self.assertGreater(r0, b0)
            self.assertGreater(b1, r1)
            gltf, binary, _ = plateau_3d.glb_chunks((Path(directory) / tile['glb']).read_bytes())
            for expected_id, mesh in enumerate(gltf['meshes']):
                attr_index = mesh['primitives'][0]['attributes']['_BATCHID']
                values = appearance._accessor_values(gltf, binary, attr_index)
                self.assertTrue(all(int(round(row[0])) == expected_id for row in values))

    def test_osm_proxy_supports_multipolygon_holes_and_bbox_crossing_buildings(self):
        features = [
            {
                'type': 'Feature', 'id': 'way/crossing', 'properties': {'height': '12 m'},
                'geometry': {'type': 'Polygon', 'coordinates': [[[139.795, 35.70], [139.810, 35.70], [139.810, 35.705], [139.795, 35.705], [139.795, 35.70]]]},
            },
            {
                'type': 'Feature', 'id': 'relation/courtyard', 'properties': {'building:levels': '3'},
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [
                        [[139.785, 35.695], [139.789, 35.695], [139.789, 35.699], [139.785, 35.699], [139.785, 35.695]],
                        [[139.786, 35.696], [139.788, 35.696], [139.788, 35.698], [139.786, 35.698], [139.786, 35.696]],
                    ],
                },
            },
            {
                'type': 'Feature', 'id': 'relation/multi', 'properties': {'height': 9},
                'geometry': {
                    'type': 'MultiPolygon',
                    'coordinates': [
                        [[[139.781, 35.691], [139.782, 35.691], [139.782, 35.692], [139.781, 35.692], [139.781, 35.691]]],
                        [[[139.783, 35.691], [139.784, 35.691], [139.784, 35.692], [139.783, 35.692], [139.783, 35.691]]],
                    ],
                },
            },
            {
                'type': 'Feature', 'id': 'way/non-building', 'properties': {'building': 'no', 'height': 10},
                'geometry': {'type': 'Polygon', 'coordinates': [[[139.781, 35.695], [139.782, 35.695], [139.782, 35.696], [139.781, 35.696], [139.781, 35.695]]]},
            },
        ]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            # Place a PLATEAU centroid inside the courtyard hole; the surrounding ring should NOT be skipped.
            (root / 'manifest.json').write_text(json.dumps({
                'format': 'geo-video-factory.plateau-3d/1',
                'bbox_degrees': [139.78, 35.69, 139.80, 35.71],
                'center': [139.79, 35.70],
                'tiles': [{'ids': ['gml-courtyard'], 'feature_centroids': {'gml-courtyard': [139.787, 35.697]}}],
            }))
            result = appearance.build_osm_proxy_tiles(features, [139.78, 35.69, 139.80, 35.71], root)
            proxy_tile = result['tiles'][-1]
            self.assertEqual(proxy_tile['ids'], ['way/crossing', 'relation/courtyard', 'relation/multi'])
            gltf, binary, _ = plateau_3d.glb_chunks((root / proxy_tile['glb']).read_bytes())
            # Courtyard has 4 outer + 4 inner edges = 8 walls (48 wall verts) + roof triangles (> 6*3 verts);
            # MultiPolygon has 2 separate boxes so its primitive must have > 36 vertices.
            courtyard_pos_count = gltf['accessors'][gltf['meshes'][1]['primitives'][0]['attributes']['POSITION']]['count']
            multi_pos_count = gltf['accessors'][gltf['meshes'][2]['primitives'][0]['attributes']['POSITION']]['count']
            self.assertGreater(courtyard_pos_count, 36)
            self.assertGreater(multi_pos_count, 36)

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
