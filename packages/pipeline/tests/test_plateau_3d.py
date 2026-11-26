import os
import json
import math
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import io

from support import import_pipeline

plateau_3d = import_pipeline('buildings.plateau_3d')


class Plateau3DTilesTests(unittest.TestCase):
    def test_texture_optimizer_rejects_glb_external_image_paths(self):
        document = {'asset': {'version': '2.0'}, 'images': [{'uri': 'texture.png'}]}
        raw = json.dumps(document).encode()
        raw += b' ' * ((-len(raw)) % 4)
        glb = struct.pack('<4sII', b'glTF', 2, 20 + len(raw)) + struct.pack('<I4s', len(raw), b'JSON') + raw
        with self.assertRaisesRegex(ValueError, 'external image'):
            plateau_3d._resize_glb_textures(glb, 1024)

    def test_texture_optimizer_updates_mime_type_after_webp_resize(self):
        image_buffer = io.BytesIO()
        Image.new('RGB', (8, 8), (120, 90, 40)).save(image_buffer, 'PNG')
        binary = image_buffer.getvalue()
        document = {
            'asset': {'version': '2.0'}, 'buffers': [{'byteLength': len(binary)}],
            'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(binary)}],
            'images': [{'bufferView': 0, 'mimeType': 'image/png'}],
        }
        raw_json = json.dumps(document).encode()
        raw_json += b' ' * ((-len(raw_json)) % 4)
        binary += b'\0' * ((-len(binary)) % 4)
        total = 12 + 8 + len(raw_json) + 8 + len(binary)
        glb = struct.pack('<4sII', b'glTF', 2, total) + struct.pack('<I4s', len(raw_json), b'JSON') + raw_json
        glb += struct.pack('<I4s', len(binary), b'BIN\0') + binary
        resized = plateau_3d._resize_glb_textures(glb, 4)
        result, _, _ = plateau_3d.glb_chunks(resized)
        self.assertEqual(result['images'][0]['mimeType'], 'image/webp')

    def test_region_intersection_converts_scene_bbox_degrees_to_region_radians(self):
        self.assertTrue(plateau_3d.region_intersects_bbox(
            [math.radians(139.79), math.radians(35.70), math.radians(139.80), math.radians(35.72)],
            [139.795, 35.715, 139.805, 35.725],
        ))
        self.assertFalse(plateau_3d.region_intersects_bbox(
            [math.radians(139.79), math.radians(35.70), math.radians(139.80), math.radians(35.72)],
            [139.81, 35.71, 139.82, 35.72],
        ))

    def test_iter_leaf_contents_uses_ancestor_region_and_skips_parent_content(self):
        tileset = {
            'root': {
                'boundingVolume': {'region': [math.radians(139.7), math.radians(35.6), math.radians(139.9), math.radians(35.8)]},
                'content': {'uri': 'parent.b3dm'},
                'children': [
                    {'content': {'uri': 'inside.b3dm'}},
                    {'boundingVolume': {'region': [math.radians(140), math.radians(35.6), math.radians(140.1), math.radians(35.8)]},
                     'content': {'uri': 'outside.b3dm'}},
                ],
            },
        }
        selected = list(plateau_3d.iter_leaf_contents(tileset, [139.75, 35.65, 139.85, 35.75]))
        self.assertEqual([tile['uri'] for tile in selected], ['inside.b3dm'])
        self.assertEqual(selected[0]['depth'], 1)

    def test_iter_leaf_contents_rejects_non_identity_transform(self):
        tileset = {'root': {'transform': [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 1],
                            'content': {'uri': 'shifted.b3dm'}}}
        with self.assertRaisesRegex(ValueError, 'transform'):
            list(plateau_3d.iter_leaf_contents(tileset, [139, 35, 140, 36]))

    def test_parse_b3dm_separates_json_tables_and_embedded_glb(self):
        feature = json.dumps({'BATCH_LENGTH': 1, 'RTC_CENTER': [1, 2, 3]}).encode()
        batch = json.dumps({'gml_id': ['building-1']}).encode()
        glb = b'glTFfixture!'
        feature += b' ' * ((-len(feature)) % 8)
        batch += b' ' * ((-(28 + len(feature) + len(batch))) % 8)
        total = 28 + len(feature) + len(batch) + len(glb)
        header = struct.pack('<4sIIIIII', b'b3dm', 1, total, len(feature), 0, len(batch), 0)
        result = plateau_3d.parse_b3dm(header + feature + batch + glb)
        self.assertEqual(result['glb'], glb)
        self.assertEqual(result['feature_table']['RTC_CENTER'], [1, 2, 3])
        self.assertEqual(result['batch_table']['gml_id'], ['building-1'])

    def test_parse_b3dm_rejects_truncated_payload(self):
        with self.assertRaisesRegex(ValueError, 'length'):
            plateau_3d.parse_b3dm(struct.pack('<4sIIIIII', b'b3dm', 1, 100, 0, 0, 0, 0))

    def one_tile_resources(self):
        gltf_json = json.dumps({'asset': {'version': '2.0'}}).encode()
        gltf_json += b' ' * ((-len(gltf_json)) % 4)
        glb_length = 12 + 8 + len(gltf_json)
        glb = struct.pack('<4sII', b'glTF', 2, glb_length) + struct.pack('<I4s', len(gltf_json), b'JSON') + gltf_json
        feature = json.dumps({'BATCH_LENGTH': 1, 'RTC_CENTER': [1, 2, 3]}).encode()
        batch = json.dumps({'gml_id': ['gml-1']}).encode()
        feature += b' ' * ((-len(feature)) % 8)
        batch += b' ' * ((-(28 + len(feature) + len(batch))) % 8)
        total = 28 + len(feature) + len(batch) + len(glb)
        b3dm = struct.pack('<4sIIIIII', b'b3dm', 1, total, len(feature), 0, len(batch), 0) + feature + batch + glb
        tileset = {
            'root': {
                'boundingVolume': {'region': [math.radians(139.7), math.radians(35.6), math.radians(139.9), math.radians(35.8)]},
                'content': {'uri': 'tile.b3dm'},
            },
        }
        resources = {'https://tiles.example/root.json': json.dumps(tileset).encode(), 'https://tiles.example/tile.b3dm': b3dm}
        return resources

    def test_prepare_tiles_writes_local_manifest_and_preserves_model_metadata(self):
        resources = self.one_tile_resources()

        with tempfile.TemporaryDirectory() as directory:
            manifest = plateau_3d.prepare_tiles(
                'https://tiles.example/root.json', [139.75, 35.65, 139.85, 35.75], Path(directory),
                fetcher=lambda url: resources[url],
            )
            self.assertEqual(manifest['center'], [139.8, 35.7])
            self.assertEqual(manifest['tile_count'], 1)
            self.assertEqual(manifest['tile_ids'], 1)
            self.assertEqual(manifest['tiles'][0]['ids'], ['gml-1'])
            self.assertTrue((Path(directory) / manifest['tiles'][0]['glb']).is_file())
            self.assertEqual(json.loads((Path(directory) / 'manifest.json').read_text())['format'], 'geo-video-factory.plateau-3d/1')

    def test_prepare_tiles_reads_the_raw_tiles_from_the_shared_cache_after_the_first_download(self):
        resources = self.one_tile_resources()
        calls = []

        def fetch(url):
            calls.append(url)
            return resources[url]

        with tempfile.TemporaryDirectory() as raw, tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first = plateau_3d.prepare_tiles('https://tiles.example/root.json', [139.75, 35.65, 139.85, 35.75], Path(a),
                                             fetcher=fetch, raw_cache=Path(raw))
            second = plateau_3d.prepare_tiles('https://tiles.example/root.json', [139.70, 35.60, 139.80, 35.70], Path(b),
                                              fetcher=lambda url: self.fail(f'fetched {url} again'), raw_cache=Path(raw))
        self.assertEqual(sorted(calls), ['https://tiles.example/root.json', 'https://tiles.example/tile.b3dm'])
        self.assertEqual(first['tiles'][0]['source_sha256'], second['tiles'][0]['source_sha256'])

    def test_prepare_tiles_without_a_fetcher_uses_the_shared_plateau_raw_cache(self):
        resources = self.one_tile_resources()
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as out, \
                patch.dict(os.environ, {'GEO_VIDEO_CACHE': root}), \
                patch.object(plateau_3d, '_default_fetch', lambda url: resources[url]):
            plateau_3d.prepare_tiles('https://tiles.example/root.json', [139.75, 35.65, 139.85, 35.75], Path(out))
            cached = sorted(p.suffix for p in (Path(root) / 'plateau-raw').rglob('*') if p.is_file())
        self.assertEqual(cached, ['.b3dm', '.json'])

    def test_prepare_tiles_records_feature_centroids_from_batched_glb(self):
        from buildings.building_appearance import _ecef
        rtc = list(_ecef(139.8, 35.7))
        binary = struct.pack('<3f', 0.0, 0.0, 0.0) + bytes([0, 0, 0, 0])
        document = {
            'asset': {'version': '2.0'},
            'buffers': [{'byteLength': len(binary)}],
            'bufferViews': [
                {'buffer': 0, 'byteOffset': 0, 'byteLength': 12},
                {'buffer': 0, 'byteOffset': 12, 'byteLength': 1},
            ],
            'accessors': [
                {'bufferView': 0, 'componentType': 5126, 'count': 1, 'type': 'VEC3'},
                {'bufferView': 1, 'componentType': 5121, 'count': 1, 'type': 'SCALAR'},
            ],
            'meshes': [{'primitives': [{'attributes': {'POSITION': 0, '_BATCHID': 1}}]}],
        }
        json_chunk = json.dumps(document, separators=(',', ':')).encode()
        json_chunk += b' ' * ((-len(json_chunk)) % 4)
        total = 12 + 8 + len(json_chunk) + 8 + len(binary)
        glb = struct.pack('<4sII', b'glTF', 2, total) + struct.pack('<I4s', len(json_chunk), b'JSON') + json_chunk + struct.pack('<I4s', len(binary), b'BIN\0') + binary
        feature = json.dumps({'BATCH_LENGTH': 1, 'RTC_CENTER': rtc}).encode()
        batch = json.dumps({'gml_id': ['gml-1']}).encode()
        feature += b' ' * ((-len(feature)) % 8)
        batch += b' ' * ((-(28 + len(feature) + len(batch))) % 8)
        b3dm = struct.pack('<4sIIIIII', b'b3dm', 1, 28 + len(feature) + len(batch) + len(glb), len(feature), 0, len(batch), 0) + feature + batch + glb
        tileset = {
            'root': {
                'boundingVolume': {'region': [math.radians(139.7), math.radians(35.6), math.radians(139.9), math.radians(35.8)]},
                'content': {'uri': 'tile.b3dm'},
            },
        }
        resources = {'https://tiles.example/root.json': json.dumps(tileset).encode(), 'https://tiles.example/tile.b3dm': b3dm}
        with tempfile.TemporaryDirectory() as directory:
            manifest = plateau_3d.prepare_tiles(
                'https://tiles.example/root.json', [139.75, 35.65, 139.85, 35.75], Path(directory),
                fetcher=lambda url: resources[url],
            )
        centroids = manifest['tiles'][0].get('feature_centroids')
        self.assertIsInstance(centroids, dict)
        self.assertIn('gml-1', centroids)
        self.assertAlmostEqual(centroids['gml-1'][0], 139.8, places=4)
        self.assertAlmostEqual(centroids['gml-1'][1], 35.7, places=4)

    def test_cli_passes_plateau_ids_to_osm_proxy_builder(self):
        from unittest.mock import patch
        import sys
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            osm_path = root / 'osm.geojson'
            osm_path.write_text(json.dumps({'type': 'FeatureCollection', 'features': []}), encoding='utf-8')
            fake_manifest = {'format': 'geo-video-factory.plateau-3d/1', 'tiles': [{'ids': ['gml-1', 'gml-2']}]}
            with patch.object(plateau_3d, 'prepare_tiles', return_value=fake_manifest), \
                 patch('buildings.building_appearance.build_osm_proxy_tiles', return_value=fake_manifest) as mock_proxy, \
                 patch.object(sys, 'argv', ['plateau_3d.py', 'https://tiles.example/root.json', '--bbox', '139.7', '35.6', '139.9', '35.8', '--out', str(root / 'out'), '--osm-geojson', str(osm_path)]):
                plateau_3d.main()
            mock_proxy.assert_called_once()
            self.assertEqual(mock_proxy.call_args.kwargs.get('plateau_ids'), {'gml-1', 'gml-2'})

    def test_adaptive_texture_limit_uses_2048_near_center_and_1024_far_and_strips_cesium_rtc(self):
        near_region = [math.radians(139.799), math.radians(35.699), math.radians(139.801), math.radians(35.701), 0, 50]
        far_region = [math.radians(139.810), math.radians(35.710), math.radians(139.812), math.radians(35.712), 0, 50]
        self.assertEqual(plateau_3d.tile_texture_limit(near_region, (139.800, 35.700), 2048, 1024), 2048)
        self.assertEqual(plateau_3d.tile_texture_limit(far_region, (139.800, 35.700), 2048, 1024), 1024)
        image_buffer = io.BytesIO()
        Image.new('RGB', (200, 100), (120, 90, 40)).save(image_buffer, 'PNG')
        binary = image_buffer.getvalue()
        document = {
            'asset': {'version': '2.0'},
            'extensionsUsed': ['CESIUM_RTC'],
            'extensions': {'CESIUM_RTC': {'center': [1.0, 2.0, 3.0]}},
            'buffers': [{'byteLength': len(binary)}],
            'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(binary)}],
            'images': [{'bufferView': 0, 'mimeType': 'image/png'}],
        }
        raw_json = json.dumps(document).encode()
        raw_json += b' ' * ((-len(raw_json)) % 4)
        binary += b'\0' * ((-len(binary)) % 4)
        total = 12 + 8 + len(raw_json) + 8 + len(binary)
        raw_glb = struct.pack('<4sII', b'glTF', 2, total) + struct.pack('<I4s', len(raw_json), b'JSON') + raw_json
        raw_glb += struct.pack('<I4s', len(binary), b'BIN\0') + binary
        optimized = plateau_3d.optimize_glb_textures(raw_glb, max_dimension=64)
        gltf, opt_bin, _ = plateau_3d.glb_chunks(optimized)
        self.assertNotIn('CESIUM_RTC', gltf.get('extensions', {}))
        self.assertNotIn('CESIUM_RTC', gltf.get('extensionsUsed', []))
        view = gltf['bufferViews'][gltf['images'][0]['bufferView']]
        image = Image.open(io.BytesIO(opt_bin[view['byteOffset']:view['byteOffset'] + view['byteLength']]))
        self.assertEqual(image.size, (64, 32))

    def test_stripping_cesium_rtc_also_removes_it_from_extensions_required(self):
        # Strict glTF loaders (Blender) reject files whose extensionsRequired lists an unused extension.
        document = {
            'extensionsUsed': ['CESIUM_RTC', 'KHR_draco_mesh_compression'],
            'extensionsRequired': ['CESIUM_RTC', 'KHR_draco_mesh_compression'],
            'extensions': {'CESIUM_RTC': {'center': [1.0, 2.0, 3.0]}},
        }
        self.assertTrue(plateau_3d._strip_cesium_rtc(document))
        self.assertEqual(document['extensionsUsed'], ['KHR_draco_mesh_compression'])
        self.assertEqual(document['extensionsRequired'], ['KHR_draco_mesh_compression'])
        self.assertNotIn('extensions', document)

        only_required = {'extensionsRequired': ['CESIUM_RTC']}
        self.assertTrue(plateau_3d._strip_cesium_rtc(only_required))
        self.assertNotIn('extensionsRequired', only_required)


if __name__ == '__main__':
    unittest.main()
