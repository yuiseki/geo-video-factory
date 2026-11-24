import json
import struct
import unittest

from support import import_pipeline

bh = import_pipeline('buildings.building_heights')
gs = import_pipeline('buildings.glb_spatial')


def _glb(local_verts, batch_ids):
    binary = b''.join(struct.pack('<3f', *v) for v in local_verts)
    ids = bytes(batch_ids) + b'\0' * ((-len(batch_ids)) % 4)
    doc = {
        'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0}],
        'buffers': [{'byteLength': len(binary) + len(ids)}],
        'bufferViews': [
            {'buffer': 0, 'byteOffset': 0, 'byteLength': len(binary)},
            {'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(batch_ids)},
        ],
        'accessors': [
            {'bufferView': 0, 'componentType': 5126, 'count': len(local_verts), 'type': 'VEC3'},
            {'bufferView': 1, 'componentType': 5121, 'count': len(batch_ids), 'type': 'SCALAR'},
        ],
        'materials': [{'pbrMetallicRoughness': {}}],
        'meshes': [{'primitives': [{'attributes': {'POSITION': 0, '_BATCHID': 1}, 'material': 0}]}],
    }
    jc = json.dumps(doc, separators=(',', ':')).encode()
    jc += b' ' * ((-len(jc)) % 4)
    body = binary + ids
    return struct.pack('<4sII', b'glTF', 2, 12 + 8 + len(jc) + 8 + len(body)) + struct.pack('<I4s', len(jc), b'JSON') + jc + struct.pack('<I4s', len(body), b'BIN\0') + body


class ExtractHeightsTest(unittest.TestCase):
    def test_measures_each_feature_height_along_the_local_vertical(self):
        rtc = gs._ecef(139.33, 35.74)

        def local(lon, lat, h):
            p = gs._ecef(lon, lat, h)
            dx, dy, dz = (p[i] - rtc[i] for i in range(3))
            return (dx, dz, -dy)

        verts = [local(139.33, 35.74, 100), local(139.3301, 35.7401, 112.5),
                 local(139.331, 35.741, 100), local(139.3311, 35.7411, 106)]
        result = gs.extract_glb_feature_heights(_glb(verts, [0, 0, 1, 1]), list(rtc), ['a', 'b'])
        self.assertAlmostEqual(result['a']['height'], 12.5, delta=0.05)
        self.assertAlmostEqual(result['b']['height'], 6.0, delta=0.05)
        self.assertAlmostEqual(result['b']['lonlat'][0], 139.33105, places=4)


class HeightModelTest(unittest.TestCase):
    def test_footprint_area_in_square_meters(self):
        ring = [[139.33, 35.74], [139.3301, 35.74], [139.3301, 35.7401], [139.33, 35.7401], [139.33, 35.74]]
        self.assertAlmostEqual(bh.footprint_area_m2(ring), 9.04 * 11.09, delta=2)

    def test_calibration_uses_the_median_per_class_and_area_bin_and_keeps_the_prior_elsewhere(self):
        samples = [(3101, 100.0, h) for h in (6.0, 6.5, 7.0, 7.5, 50.0, 6.8, 6.2, 7.2, 6.9)]
        model = bh.calibrate_height_model(samples, min_samples=8)
        bin_index = bh.area_bin(100.0)
        self.assertAlmostEqual(model['heights']['3101'][bin_index], 6.9)
        self.assertEqual(model['counts']['3101'][bin_index], 9)
        self.assertEqual(model['heights']['3102'], bh.PRIOR_HEIGHTS['3102'])
        self.assertEqual(model['heights']['3101'][0], bh.PRIOR_HEIGHTS['3101'][0])

    def test_every_building_is_at_least_one_story_tall(self):
        model = {'heights': {'3111': [0.5] * len(bh.AREA_BINS)}, 'counts': {}}
        for props in ({'vt_code': 3111}, {'vt_code': 3101, 'height': '0'}, {'vt_code': 3101, 'building:levels': '0'}, {}):
            height, _ = bh.estimate_height(props, 12.0, model, 'gsi/x')
            self.assertGreaterEqual(height, bh.ONE_STORY_M)

    def test_measured_tags_win_over_the_model_and_the_source_is_recorded(self):
        model = bh.calibrate_height_model([])
        self.assertEqual(bh.estimate_height({'vt_code': 3101, 'height': '23.5'}, 90, model, 'a'), (23.5, 'osm:height'))
        self.assertEqual(bh.estimate_height({'vt_code': 3101, 'building:levels': '5'}, 90, model, 'a'), (5 * bh.STORY_M, 'osm:levels'))
        height, source = bh.estimate_height({'vt_code': 3102}, 400, model, 'a')
        self.assertEqual(source, 'model:3102')
        self.assertEqual(height, bh.estimate_height({'vt_code': 3102}, 400, model, 'a')[0], 'estimates are deterministic')
        prior = bh.PRIOR_HEIGHTS['3102'][bh.area_bin(400)]
        self.assertTrue(prior * 0.85 <= height <= prior * 1.15)

    def test_levels_below_one_are_not_storeys_and_fall_back_to_the_model(self):
        model = bh.calibrate_height_model([])
        for bad in ('0.8', '0', '-1', 'two'):
            height, source = bh.estimate_height({'vt_code': 3101, 'building:levels': bad}, 90, model, 'a')
            self.assertEqual(source, 'model:3101', bad)


if __name__ == '__main__':
    unittest.main()
