import json
import math
import struct
import tempfile
import unittest
from pathlib import Path
from PIL import Image
import io

from support import import_pipeline

plateau_3d = import_pipeline('plateau_3d')


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

    def test_prepare_tiles_writes_local_manifest_and_preserves_model_metadata(self):
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


if __name__ == '__main__':
    unittest.main()
