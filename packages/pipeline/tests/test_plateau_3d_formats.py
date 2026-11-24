"""Tests for plateau_3d container parsing, metadata IDs, texture handling and the CLI wiring."""
import contextlib
import io
import json
import math
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from support import import_pipeline

plateau_3d = import_pipeline('plateau_3d')

BBOX = [139.75, 35.65, 139.85, 35.75]


def region(west, south, east, north):
    return [math.radians(west), math.radians(south), math.radians(east), math.radians(north), 0, 50]


COVERING_REGION = region(139.7, 35.6, 139.9, 35.8)


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack('<I4s', len(data), kind) + data


def glb_from_chunks(*chunks: bytes, version: int = 2) -> bytes:
    body = b''.join(chunks)
    return struct.pack('<4sII', b'glTF', version, 12 + len(body)) + body


def json_chunk(document) -> bytes:
    raw = json.dumps(document).encode()
    return chunk(b'JSON', raw + b' ' * ((-len(raw)) % 4))


def make_glb(document: dict, binary: bytes = b'') -> bytes:
    chunks = [json_chunk(document)]
    if binary:
        chunks.append(chunk(b'BIN\0', binary + b'\0' * ((-len(binary)) % 4)))
    return glb_from_chunks(*chunks)


def make_b3dm(glb: bytes, feature: bytes = b'', batch: bytes = b'', feature_bin: bytes = b'', batch_bin: bytes = b'') -> bytes:
    total = 28 + len(feature) + len(feature_bin) + len(batch) + len(batch_bin) + len(glb)
    header = struct.pack('<4sIIIIII', b'b3dm', 1, total, len(feature), len(feature_bin), len(batch), len(batch_bin))
    return header + feature + feature_bin + batch + batch_bin + glb


def image_bytes(size, fmt='PNG', colour=(120, 90, 40)) -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', size, colour).save(buffer, fmt)
    return buffer.getvalue()


def textured_glb(image: bytes, mime: str, **document_extra) -> bytes:
    document = {
        'asset': {'version': '2.0'}, 'buffers': [{'byteLength': len(image)}],
        'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(image)}],
        'images': [{'bufferView': 0, 'mimeType': mime}],
        **document_extra,
    }
    return make_glb(document, image)


def embedded_image(glb: bytes, index: int = 0) -> Image.Image:
    document, binary, _ = plateau_3d.glb_chunks(glb)
    view = document['bufferViews'][document['images'][index]['bufferView']]
    return Image.open(io.BytesIO(binary[view['byteOffset']:view['byteOffset'] + view['byteLength']]))


def metadata_glb(ids: list[str], offset_type: str | None = 'UINT32', count: int | None = None, drop_value_bytes: int = 0) -> bytes:
    """A GLB whose EXT_structural_metadata property table stores gml_id strings."""
    values = ''.join(ids).encode('utf-8')
    offsets = [0]
    for identifier in ids:
        offsets.append(offsets[-1] + len(identifier.encode('utf-8')))
    code = {'UINT8': 'B', 'UINT16': 'H', 'UINT32': 'I', None: 'I'}.get(offset_type, 'I')
    packed = struct.pack('<' + code * len(offsets), *offsets)
    values = values[:len(values) - drop_value_bytes]
    prop = {'values': 0, 'stringOffsets': 1}
    if offset_type is not None:
        prop['stringOffsetType'] = offset_type
    document = {
        'asset': {'version': '2.0'},
        'buffers': [{'byteLength': len(values) + len(packed)}],
        'bufferViews': [
            {'buffer': 0, 'byteOffset': 0, 'byteLength': len(values)},
            {'buffer': 0, 'byteOffset': len(values), 'byteLength': len(packed)},
        ],
        'extensions': {'EXT_structural_metadata': {'propertyTables': [
            {'count': 3, 'properties': {'height': {'values': 0}}},
            {'count': len(ids) if count is None else count, 'properties': {'gml_id': prop}},
        ]}},
    }
    return make_glb(document, values + packed)


class RegionAndTraversalTests(unittest.TestCase):
    def test_region_and_bbox_must_have_four_coordinates(self):
        with self.assertRaisesRegex(ValueError, 'four coordinates'):
            plateau_3d.region_intersects_bbox([0.1, 0.2, 0.3], [0, 0, 1, 1])
        with self.assertRaisesRegex(ValueError, 'four coordinates'):
            plateau_3d.region_intersects_bbox([0.1, 0.2, 0.3, 0.4], [0, 0, 1])

    def test_bbox_crossing_the_antimeridian_matches_regions_on_both_sides(self):
        bbox = [179.0, -1.0, -179.0, 1.0]
        self.assertTrue(plateau_3d.region_intersects_bbox(region(179.4, -0.5, 179.6, 0.5), bbox))
        self.assertTrue(plateau_3d.region_intersects_bbox(region(-179.6, -0.5, -179.4, 0.5), bbox))
        self.assertFalse(plateau_3d.region_intersects_bbox(region(-10.0, -0.5, 10.0, 0.5), bbox))
        self.assertFalse(plateau_3d.region_intersects_bbox(region(179.4, 2.0, 179.6, 3.0), bbox))

    def test_tileset_without_root_tile_is_rejected(self):
        for tileset in ({}, {'root': []}):
            with self.subTest(tileset=tileset), self.assertRaisesRegex(ValueError, 'missing root'):
                list(plateau_3d.iter_leaf_contents(tileset, BBOX))

    def test_leaf_content_without_uri_is_rejected_with_its_depth(self):
        tileset = {'root': {'boundingVolume': {'region': COVERING_REGION}, 'children': [{'content': {'boundingVolume': {}}}]}}
        with self.assertRaisesRegex(ValueError, 'depth 1 has no uri'):
            list(plateau_3d.iter_leaf_contents(tileset, BBOX))

    def test_legacy_url_key_and_identity_transform_are_accepted(self):
        tileset = {'root': {
            'transform': list(plateau_3d.IDENTITY), 'boundingVolume': {'region': COVERING_REGION},
            'content': {'url': 'legacy.b3dm'},
        }}
        self.assertEqual(
            list(plateau_3d.iter_leaf_contents(tileset, BBOX)),
            [{'uri': 'legacy.b3dm', 'region': COVERING_REGION, 'depth': 0}],
        )

    def test_content_bounding_region_narrows_the_tile_region(self):
        tileset = {'root': {'boundingVolume': {'region': COVERING_REGION}, 'children': [
            {'content': {'uri': 'east.b3dm', 'boundingVolume': {'region': region(139.86, 35.6, 139.9, 35.8)}}},
            {'content': {'uri': 'centre.b3dm', 'boundingVolume': {'region': region(139.79, 35.69, 139.81, 35.71)}}},
            {'children': []},
        ]}}
        selected = list(plateau_3d.iter_leaf_contents(tileset, BBOX))
        self.assertEqual([item['uri'] for item in selected], ['centre.b3dm'])
        self.assertEqual(selected[0]['region'], region(139.79, 35.69, 139.81, 35.71))


class B3dmParsingTests(unittest.TestCase):
    GLB = make_glb({'asset': {'version': '2.0'}})

    def test_empty_or_whitespace_tables_are_empty_objects_and_binary_tables_are_skipped(self):
        parsed = plateau_3d.parse_b3dm(make_b3dm(self.GLB, feature=b'    ', feature_bin=b'\x01\x02\x03\x04', batch_bin=b'\x05\x06\x07\x08'))
        self.assertEqual((parsed['feature_table'], parsed['batch_table']), ({}, {}))
        self.assertEqual(parsed['glb'], self.GLB)

    def test_malformed_payloads_are_rejected_with_the_reason(self):
        good = make_b3dm(self.GLB)
        cases = {
            'header is truncated': good[:27],
            'unsupported b3dm magic or version': b'i3dm' + good[4:],
            'unsupported b3dm magic or version ': good[:4] + struct.pack('<I', 2) + good[8:],
            'table lengths exceed payload length': struct.pack('<4sIIIIII', b'b3dm', 1, 32, 64, 0, 0, 0) + b'{}  ',
            'invalid feature table JSON': make_b3dm(self.GLB, feature=b'{"BATCH_LENGTH": '),
            'invalid batch table JSON': make_b3dm(self.GLB, batch=b'\xff\xfe{}'),
            'batch table JSON in b3dm must be an object': make_b3dm(self.GLB, batch=b'[1, 2]  '),
            'does not contain an embedded GLB': make_b3dm(b'not a glb at all'),
            'does not contain an embedded GLB ': make_b3dm(b''),
        }
        for message, payload in cases.items():
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message.strip()):
                plateau_3d.parse_b3dm(payload)


class GlbChunkTests(unittest.TestCase):
    def test_reads_json_binary_and_keeps_unknown_chunks_in_order(self):
        payload = glb_from_chunks(json_chunk({'asset': {'version': '2.0'}}), chunk(b'BIN\0', b'\x01\x02\x03\x04'), chunk(b'XTRA', b'abcd'))
        document, binary, chunks = plateau_3d.glb_chunks(payload)
        self.assertEqual(document, {'asset': {'version': '2.0'}})
        self.assertEqual(binary, b'\x01\x02\x03\x04')
        self.assertEqual([kind for kind, _ in chunks], [b'JSON', b'BIN\0', b'XTRA'])
        self.assertEqual(chunks[2][1], b'abcd')

    def test_glb_without_binary_chunk_has_empty_binary(self):
        self.assertEqual(plateau_3d.glb_chunks(make_glb({'asset': {}}))[1], b'')

    def test_malformed_glb_is_rejected_with_the_reason(self):
        good_json = json_chunk({'asset': {'version': '2.0'}})
        overlong = struct.pack('<I4s', 400, b'BIN\0') + b'\0' * 8
        cases = {
            'payload is not a GLB': b'glTF' + b'\0' * 8,
            'payload is not a GLB ': b'b3dm' + b'\0' * 40,
            'unsupported GLB version or declared length': glb_from_chunks(good_json, version=1),
            'unsupported GLB version or declared length ': glb_from_chunks(good_json) + b'\0\0\0\0',
            'truncated GLB chunk header': glb_from_chunks(good_json, b'\x04\0\0\0'),
            'truncated GLB chunk payload': glb_from_chunks(good_json, overlong),
            'exactly one JSON chunk': glb_from_chunks(chunk(b'BIN\0', b'\0' * 8)),
            'exactly one JSON chunk ': glb_from_chunks(good_json, good_json),
            'multiple BIN chunks': glb_from_chunks(good_json, chunk(b'BIN\0', b'\0' * 4), chunk(b'BIN\0', b'\0' * 4)),
        }
        for message, payload in cases.items():
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message.strip()):
                plateau_3d.glb_chunks(payload)


class GmlIdExtractionTests(unittest.TestCase):
    def test_batch_table_ids_win_and_are_returned_as_strings(self):
        self.assertEqual(plateau_3d.extract_gml_ids(b'not even a glb', {'gml_id': ['bldg-1', 42]}), ['bldg-1', '42'])

    def test_structural_metadata_strings_are_read_for_every_offset_width(self):
        ids = ['bldg-1', '建物-22', '']
        for offset_type in (None, 'UINT32', 'UINT16', 'UINT8'):
            with self.subTest(offset_type=offset_type):
                self.assertEqual(plateau_3d.extract_gml_ids(metadata_glb(ids, offset_type)), ids)

    def test_batch_table_without_id_list_falls_back_to_structural_metadata(self):
        glb = metadata_glb(['a', 'bc'])
        self.assertEqual(plateau_3d.extract_gml_ids(glb, {'gml_id': 'not-a-list', 'height': [1, 2]}), ['a', 'bc'])

    def test_glb_without_any_ids_gives_an_empty_list(self):
        self.assertEqual(plateau_3d.extract_gml_ids(make_glb({'asset': {'version': '2.0'}})), [])

    def test_unsupported_offset_type_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'string offset type: UINT64'):
            plateau_3d.extract_gml_ids(metadata_glb(['a'], 'UINT64'))

    def test_offsets_shorter_than_the_declared_count_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'string offsets are truncated'):
            plateau_3d.extract_gml_ids(metadata_glb(['a', 'b'], count=5))

    def test_offsets_pointing_past_the_values_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'string values are truncated'):
            plateau_3d.extract_gml_ids(metadata_glb(['abcd', 'efgh'], drop_value_bytes=3))

    def test_buffer_view_outside_the_binary_chunk_is_rejected(self):
        document = {
            'bufferViews': [{'byteOffset': 0, 'byteLength': 64}, {'byteOffset': 0, 'byteLength': 4}],
            'extensions': {'EXT_structural_metadata': {'propertyTables': [
                {'count': 1, 'properties': {'gml_id': {'values': 0, 'stringOffsets': 1}}},
            ]}},
        }
        with self.assertRaisesRegex(ValueError, 'outside the binary chunk'):
            plateau_3d.extract_gml_ids(make_glb(document, b'\0' * 8))


class TextureOptimizerTests(unittest.TestCase):
    def test_glb_without_images_or_rtc_is_returned_untouched(self):
        for payload in (make_glb({'asset': {'version': '2.0'}}), make_glb({'asset': {'version': '2.0'}}, b'\x01\x02\x03\x04')):
            self.assertEqual(plateau_3d._resize_glb_textures(payload, 1024), payload)

    def test_rtc_extension_is_removed_from_untextured_glb_and_geometry_bytes_are_kept(self):
        geometry = struct.pack('<3f', 1.0, 2.0, 3.0)
        document = {
            'asset': {'version': '2.0'}, 'buffers': [{'byteLength': len(geometry)}],
            'extensionsUsed': ['CESIUM_RTC'], 'extensions': {'CESIUM_RTC': {'center': [1, 2, 3]}},
        }
        payload = glb_from_chunks(json_chunk(document), chunk(b'BIN\0', geometry), chunk(b'XTRA', b'abcd'))
        stripped = plateau_3d._resize_glb_textures(payload, 1024)
        result, binary, chunks = plateau_3d.glb_chunks(stripped)
        self.assertEqual(result, {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': len(geometry)}]})
        self.assertEqual(binary, geometry)
        self.assertEqual([kind for kind, _ in chunks], [b'JSON', b'BIN\0', b'XTRA'])
        self.assertEqual(len(stripped) % 4, 0)

    def test_small_textures_are_left_byte_for_byte_identical(self):
        for fmt, mime in (('PNG', 'image/png'), ('WEBP', 'image/webp')):
            with self.subTest(mime=mime):
                payload = textured_glb(image_bytes((16, 8), fmt), mime)
                self.assertEqual(plateau_3d._resize_glb_textures(payload, 64), payload)

    def test_oversized_webp_texture_is_scaled_down_keeping_aspect_ratio(self):
        payload = textured_glb(image_bytes((200, 50), 'WEBP'), 'image/webp')
        resized = plateau_3d._resize_glb_textures(payload, 100)
        document, binary, _ = plateau_3d.glb_chunks(resized)
        image = embedded_image(resized)
        self.assertEqual((image.size, image.format), ((100, 25), 'WEBP'))
        # The declared buffer length must cover the relocated image.
        view = document['bufferViews'][0]
        self.assertLessEqual(view['byteOffset'] + view['byteLength'], document['buffers'][0]['byteLength'])
        self.assertLessEqual(document['buffers'][0]['byteLength'], len(binary))
        self.assertEqual(view['byteOffset'] % 4, 0)

    def test_images_stored_as_data_uris_are_ignored(self):
        texture = image_bytes((200, 100))
        document = {
            'asset': {'version': '2.0'}, 'buffers': [{'byteLength': len(texture)}],
            'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(texture)}],
            'images': [{'uri': 'data:image/png;base64,AAAA'}, {'bufferView': 0, 'mimeType': 'image/png'}],
        }
        resized = plateau_3d._resize_glb_textures(make_glb(document, texture), 50)
        result, _, _ = plateau_3d.glb_chunks(resized)
        self.assertEqual(result['images'][0], {'uri': 'data:image/png;base64,AAAA'})
        self.assertEqual(embedded_image(resized, 1).size, (50, 25))

    def test_undecodable_embedded_image_is_rejected(self):
        payload = textured_glb(b'this is not an image file', 'image/png')
        with self.assertRaisesRegex(ValueError, 'cannot decode embedded GLB image'):
            plateau_3d._resize_glb_textures(payload, 64)

    def test_image_buffer_view_outside_the_binary_chunk_is_rejected(self):
        document = {
            'asset': {'version': '2.0'}, 'bufferViews': [{'buffer': 0, 'byteOffset': 4, 'byteLength': 400}],
            'images': [{'bufferView': 0, 'mimeType': 'image/png'}],
        }
        with self.assertRaisesRegex(ValueError, 'outside the binary chunk'):
            plateau_3d._resize_glb_textures(make_glb(document, b'\0' * 16), 64)


class FakeHttpResponse:
    def __init__(self, body: bytes):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class DefaultFetchTests(unittest.TestCase):
    def test_default_fetch_sends_the_user_agent_and_returns_the_body(self):
        seen = {}

        def fake_urlopen(request, timeout=None):
            seen['url'] = request.full_url
            seen['agent'] = request.get_header('User-agent')
            seen['timeout'] = timeout
            return FakeHttpResponse(b'{"root": {}}')

        with patch.object(plateau_3d, 'urlopen', side_effect=fake_urlopen):
            self.assertEqual(plateau_3d._default_fetch('https://tiles.example/tileset.json'), b'{"root": {}}')
        self.assertEqual(seen, {'url': 'https://tiles.example/tileset.json', 'agent': plateau_3d.USER_AGENT, 'timeout': 90})

    def test_prepare_tiles_uses_the_default_fetch_when_no_fetcher_is_given(self):
        tileset = {'root': {'boundingVolume': {'region': COVERING_REGION}, 'content': {'uri': 'tile.glb'}}}
        resources = {
            'https://tiles.example/root.json': json.dumps(tileset).encode(),
            'https://tiles.example/tile.glb': make_glb({'asset': {'version': '2.0'}}),
        }
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(plateau_3d, '_default_fetch', side_effect=lambda url: resources[url]) as fetch:
            manifest = plateau_3d.prepare_tiles('https://tiles.example/root.json', BBOX, Path(directory), workers=1)
        self.assertEqual(manifest['tile_count'], 1)
        self.assertEqual(fetch.call_count, 2)


def single_tile_resources(content: bytes, uri: str = 'tile.b3dm', tile_region=COVERING_REGION) -> dict[str, bytes]:
    tileset = {'root': {'boundingVolume': {'region': tile_region}, 'content': {'uri': uri}}}
    return {'https://tiles.example/root.json': json.dumps(tileset).encode(), f'https://tiles.example/{uri}': content}


class PrepareTilesTests(unittest.TestCase):
    def prepare(self, resources, directory, **kwargs):
        return plateau_3d.prepare_tiles(
            'https://tiles.example/root.json', BBOX, Path(directory), fetcher=lambda url: resources[url], **kwargs,
        )

    def test_non_positive_texture_dimension_or_workers_are_rejected_before_fetching(self):
        def never(url):
            raise AssertionError('nothing may be fetched')

        with tempfile.TemporaryDirectory() as directory:
            for kwargs in ({'max_texture_dimension': 0}, {'workers': 0}, {'workers': -1}):
                with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, 'must be positive'):
                    plateau_3d.prepare_tiles('https://tiles.example/root.json', BBOX, Path(directory), fetcher=never, **kwargs)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_external_tilesets_are_followed_relative_to_their_own_url(self):
        glb = make_glb({'asset': {'version': '2.0'}})
        root = {'root': {'boundingVolume': {'region': COVERING_REGION}, 'children': [
            {'content': {'uri': 'area/nested.JSON'}},
            {'content': {'uri': 'direct.glb'}},
        ]}}
        nested = {'root': {'boundingVolume': {'region': COVERING_REGION}, 'children': [
            {'children': [{'content': {'uri': 'lod2/deep.glb'}}]},
        ]}}
        resources = {
            'https://tiles.example/root.json': json.dumps(root).encode(),
            'https://tiles.example/area/nested.JSON': json.dumps(nested).encode(),
            'https://tiles.example/area/lod2/deep.glb': glb,
            'https://tiles.example/direct.glb': glb,
        }
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.prepare(resources, directory)
            self.assertEqual(
                [(tile['source'], tile['depth']) for tile in manifest['tiles']],
                [('https://tiles.example/area/lod2/deep.glb', 3), ('https://tiles.example/direct.glb', 1)],
            )
            models = sorted(path.name for path in (Path(directory) / 'models').iterdir())
            self.assertEqual(models, sorted(Path(tile['glb']).name for tile in manifest['tiles']))
            self.assertEqual(len(set(models)), 2)

    def test_no_intersecting_leaf_is_an_error(self):
        resources = single_tile_resources(b'', tile_region=region(140.0, 36.0, 140.1, 36.1))
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, 'no leaf content intersects'):
            self.prepare(resources, directory)

    def test_content_that_is_neither_b3dm_nor_glb_is_rejected_with_its_url(self):
        resources = single_tile_resources(b'pnts' + b'\0' * 24, uri='points.pnts')
        with tempfile.TemporaryDirectory() as directory, \
             self.assertRaisesRegex(ValueError, r"unsupported 3D Tiles content at https://tiles\.example/points\.pnts: b'pnts'"):
            self.prepare(resources, directory)

    def test_rtc_center_that_is_not_three_numbers_is_rejected(self):
        glb = make_glb({'asset': {'version': '2.0'}})
        for centre in ([1, 2], [1, 2, 'three']):
            feature = json.dumps({'RTC_CENTER': centre}).encode()
            resources = single_tile_resources(make_b3dm(glb, feature=feature))
            with self.subTest(centre=centre), tempfile.TemporaryDirectory() as directory, \
                 self.assertRaisesRegex(ValueError, 'invalid RTC center in https://tiles.example/tile.b3dm'):
                self.prepare(resources, directory)

    def test_bare_glb_tile_keeps_its_rtc_center_in_the_manifest_and_loses_the_extension(self):
        document = {
            'asset': {'version': '2.0'}, 'extensionsUsed': ['CESIUM_RTC', 'KHR_materials_unlit'],
            'extensions': {'CESIUM_RTC': {'center': [10, 20.5, 30]}},
        }
        raw = make_glb(document)
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.prepare(single_tile_resources(raw, uri='tile.glb'), directory)
            tile = manifest['tiles'][0]
            written = (Path(directory) / tile['glb']).read_bytes()
        self.assertEqual(tile['rtc'], [10.0, 20.5, 30.0])
        self.assertEqual((tile['ids'], tile['feature_centroids']), ([], {}))
        self.assertEqual(tile['source'], 'https://tiles.example/tile.glb')
        self.assertEqual((tile['source_bytes'], tile['bytes']), (len(raw), len(written)))
        result, _, _ = plateau_3d.glb_chunks(written)
        self.assertNotIn('extensions', result)
        self.assertEqual(result['extensionsUsed'], ['KHR_materials_unlit'])
        self.assertEqual(manifest['total_bytes'], len(written))

    def test_tile_without_rtc_is_recorded_at_the_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.prepare(single_tile_resources(make_glb({'asset': {'version': '2.0'}}), uri='tile.glb'), directory)
        self.assertEqual(manifest['tiles'][0]['rtc'], [0.0, 0.0, 0.0])

    def test_textures_far_from_the_bbox_centre_get_the_far_limit(self):
        texture = image_bytes((64, 32))
        root = {'root': {'children': [
            {'boundingVolume': {'region': region(139.799, 35.699, 139.801, 35.701)}, 'content': {'uri': 'near.glb'}},
            {'boundingVolume': {'region': region(139.84, 35.74, 139.85, 35.75)}, 'content': {'uri': 'far.glb'}},
        ]}}
        resources = {
            'https://tiles.example/root.json': json.dumps(root).encode(),
            'https://tiles.example/near.glb': textured_glb(texture, 'image/png'),
            'https://tiles.example/far.glb': textured_glb(texture, 'image/png'),
        }
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.prepare(resources, directory, max_texture_dimension=64, far_texture_dimension=16)
            sizes = {
                Path(tile['source']).name: (tile['texture_limit'], embedded_image((Path(directory) / tile['glb']).read_bytes()).size)
                for tile in manifest['tiles']
            }
        self.assertEqual(sizes, {'near.glb': (64, (64, 32)), 'far.glb': (16, (16, 8))})
        self.assertEqual([Path(tile['source']).name for tile in manifest['tiles']], ['far.glb', 'near.glb'])

    def test_far_limit_defaults_to_1024_only_for_the_2048_default(self):
        far = region(139.84, 35.74, 139.85, 35.75)
        glb = make_glb({'asset': {'version': '2.0'}})
        for max_dimension, expected in ((2048, 1024), (512, 512)):
            with self.subTest(max_dimension=max_dimension), tempfile.TemporaryDirectory() as directory:
                manifest = self.prepare(single_tile_resources(glb, uri='far.glb', tile_region=far), directory, max_texture_dimension=max_dimension)
                self.assertEqual(manifest['tiles'][0]['texture_limit'], expected)
                self.assertEqual(manifest['texture_max_dimension'], max_dimension)


class CommandLineTests(unittest.TestCase):
    ARGV = ['plateau_3d.py', 'https://tiles.example/root.json', '--bbox', '139.7', '35.6', '139.9', '35.8']

    def test_orthophoto_and_citygml_inputs_are_passed_on_to_the_appearance_steps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ortho_path = root / 'ortho.png'
            Image.new('L', (4, 2), 128).save(ortho_path)
            citygml = [{'type': 'Feature', 'properties': {'gml_id': 'gml-9'}, 'geometry': None}]
            (root / 'citygml.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': citygml}), encoding='utf-8')
            osm = [{'type': 'Feature', 'properties': {}, 'geometry': None}]
            (root / 'osm.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': osm}), encoding='utf-8')
            prepared = {'tile_count': 1, 'tiles': [{'ids': ['gml-1']}]}
            proxied = {'tile_count': 3, 'tiles': [{'ids': ['gml-1']}, {'ids': [7]}, {}]}
            out = root / 'out'
            argv = [*self.ARGV, '--out', str(out), '--max-texture-dimension', '512', '--workers', '2', '--seed', 'asakusa',
                    '--orthophoto', str(ortho_path), '--citygml-geojson', str(root / 'citygml.geojson'), '--osm-geojson', str(root / 'osm.geojson')]
            stdout = io.StringIO()
            with patch.object(plateau_3d, 'prepare_tiles', return_value=prepared) as prepare, \
                 patch('building_appearance.apply_orthophoto_palette', return_value=prepared) as palette, \
                 patch('building_appearance.apply_citygml_colors', return_value=prepared) as colors, \
                 patch('building_appearance.build_osm_proxy_tiles', return_value=proxied) as proxy, \
                 patch.object(sys, 'argv', argv), contextlib.redirect_stdout(stdout):
                plateau_3d.main()

        bbox = [139.7, 35.6, 139.9, 35.8]
        prepare.assert_called_once_with('https://tiles.example/root.json', bbox, out, max_texture_dimension=512, workers=2)
        palette.assert_called_once_with(out, ortho_path, seed='asakusa')
        colors.assert_called_once_with(out, citygml)
        citygml_call, osm_call = proxy.call_args_list
        self.assertEqual(citygml_call.args, (citygml, bbox, out))
        self.assertEqual((citygml_call.kwargs['kind'], citygml_call.kwargs['seed']), ('citygml-proxy', 'asakusa'))
        self.assertEqual((citygml_call.kwargs['orthophoto'].mode, citygml_call.kwargs['orthophoto'].size), ('RGB', (4, 2)))
        self.assertEqual(osm_call.args, (osm, bbox, out))
        # IDs come from the manifest as it stands after the CityGML proxies were added.
        self.assertEqual(osm_call.kwargs['plateau_ids'], {'gml-1', '7'})
        self.assertIs(osm_call.kwargs['plateau_footprints'], citygml_call.args[0])
        self.assertIs(osm_call.kwargs['orthophoto'], citygml_call.kwargs['orthophoto'])
        self.assertEqual(json.loads(stdout.getvalue()), {'tile_count': 3})

    def test_without_optional_inputs_only_the_tiles_are_prepared_and_summarised(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared = {'format': 'geo-video-factory.plateau-3d/1', 'tile_count': 2, 'tiles': [{'ids': []}]}
            stdout = io.StringIO()
            with patch.object(plateau_3d, 'prepare_tiles', return_value=prepared) as prepare, \
                 patch('building_appearance.build_osm_proxy_tiles') as proxy, \
                 patch.object(sys, 'argv', [*self.ARGV, '--out', directory]), contextlib.redirect_stdout(stdout):
                plateau_3d.main()
        self.assertEqual(prepare.call_args.kwargs, {'max_texture_dimension': 2048, 'workers': 3})
        proxy.assert_not_called()
        self.assertEqual(json.loads(stdout.getvalue()), {'format': 'geo-video-factory.plateau-3d/1', 'tile_count': 2})

    def test_geojson_inputs_must_be_feature_collections(self):
        for flag in ('--osm-geojson', '--citygml-geojson'):
            for content in ([{'type': 'Feature'}], {'type': 'Feature', 'features': None}):
                with self.subTest(flag=flag, content=content), tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / 'input.geojson'
                    path.write_text(json.dumps(content), encoding='utf-8')
                    with patch.object(plateau_3d, 'prepare_tiles', return_value={'tiles': []}), \
                         patch('building_appearance.build_osm_proxy_tiles') as proxy, \
                         patch.object(sys, 'argv', [*self.ARGV, '--out', directory, flag, str(path)]), \
                         self.assertRaisesRegex(ValueError, f'{flag} must contain a GeoJSON FeatureCollection'):
                        plateau_3d.main()
                    proxy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
