import json
import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from support import import_pipeline

cp = import_pipeline('buildings.city_proxy')
bh = import_pipeline('buildings.building_heights')
gs = import_pipeline('buildings.glb_spatial')
p3 = import_pipeline('buildings.plateau_3d')
fa = import_pipeline('buildings.facade_archetypes')

BBOX = [139.30, 35.74, 139.34, 35.77]
LAT0 = 35.755
KX = 111_320.0 * math.cos(math.radians(LAT0))
KY = 110_950.0


def rect(lon, lat, w_m, h_m):
    dx, dy = w_m / KX, h_m / KY
    return [[lon, lat], [lon + dx, lat], [lon + dx, lat + dy], [lon, lat + dy], [lon, lat]]


def feature(identifier, ring, **props):
    return {'type': 'Feature', 'id': identifier, 'properties': {'vt_code': 3101, **props}, 'geometry': {'type': 'Polygon', 'coordinates': [ring]}}


def read(directory, manifest):
    tile = next(t for t in manifest['tiles'] if t['kind'] == 'city-proxy')
    document, binary, _ = p3.glb_chunks((Path(directory) / tile['glb']).read_bytes())
    attrs = document['meshes'][0]['primitives'][0]['attributes']
    values = {name: gs._accessor_values(document, binary, index) for name, index in attrs.items()}
    return tile, document, values


def up_heights(tile, positions):
    rtc = tile['rtc']
    lam, phi = math.radians(139.32), math.radians(LAT0)
    up = (math.cos(phi) * math.cos(lam), math.cos(phi) * math.sin(lam), math.sin(phi))
    out = []
    for x, y, z in positions:
        ecef = (rtc[0] + x, rtc[1] - z, rtc[2] + y)
        out.append(math.sqrt(sum(c * c for c in ecef)))
    return out


class CityProxyTest(unittest.TestCase):
    def build(self, features, **kwargs):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        kwargs.setdefault('ground', lambda lon, lat: 100.0)
        manifest = cp.build_city_proxy_tile(features, BBOX, Path(directory.name), **kwargs)
        return directory.name, manifest

    def test_all_buildings_share_one_mesh_with_per_vertex_color_and_wall_coordinates(self):
        features = [feature(f'gsi/{i}', rect(139.31 + i * 0.001, 35.75, 12, 9)) for i in range(5)]
        directory, manifest = self.build(features)
        tile, document, values = read(directory, manifest)
        self.assertEqual(len(document['meshes']), 1)
        self.assertEqual(len(document['meshes'][0]['primitives']), 1)
        self.assertEqual(len(document['materials']), 1)
        self.assertTrue({'POSITION', 'NORMAL', 'COLOR_0', 'TEXCOORD_0', '_BATCHID', '_STYLE'} <= set(values))
        self.assertEqual(sorted({int(round(v[0])) for v in values['_BATCHID']}), [0, 1, 2, 3, 4])
        self.assertEqual(tile['ids'], [f'gsi/{i}' for i in range(5)])
        self.assertEqual(manifest['city_proxy_building_count'], 5)

    def test_a_small_rectangular_house_gets_a_pitched_roof_and_the_estimated_total_height(self):
        directory, manifest = self.build([feature('gsi/house', rect(139.32, 35.75, 11, 8))])
        tile, _, values = read(directory, manifest)
        record = json.loads((Path(directory) / tile['buildings']).read_text())['buildings'][0]
        self.assertIn(record['roof'], ('gable', 'hip'))
        sloped = [n for n in values['NORMAL'] if 0.3 < abs(n[1]) < 0.97]
        self.assertTrue(sloped, 'a pitched roof has faces that are neither walls nor flat')
        top = max(v[1] for v in values['TEXCOORD_0'])
        self.assertAlmostEqual(top, record['height'] + cp.GROUND_SINK_M, delta=0.01)

    def test_a_large_sturdy_building_keeps_a_flat_roof(self):
        directory, manifest = self.build([feature('gsi/rc', rect(139.32, 35.75, 40, 25), vt_code=3102)])
        tile, _, values = read(directory, manifest)
        record = json.loads((Path(directory) / tile['buildings']).read_text())['buildings'][0]
        self.assertEqual(record['roof'], 'flat')
        self.assertEqual(record['source'], 'model:3102')
        self.assertFalse([n for n in values['NORMAL'] if 0.3 < abs(n[1]) < 0.97])

    def test_buildings_stand_on_the_ground_and_are_at_least_one_story(self):
        features = [feature('gsi/a', rect(139.32, 35.75, 4, 4), vt_code=3111)]
        directory, manifest = self.build(features, ground=lambda lon, lat: 150.0)
        tile, _, values = read(directory, manifest)
        record = json.loads((Path(directory) / tile['buildings']).read_text())['buildings'][0]
        self.assertGreaterEqual(record['height'], bh.ONE_STORY_M)
        self.assertAlmostEqual(record['ground'], 150.0 - cp.GROUND_SINK_M, delta=0.01)
        self.assertGreaterEqual(min(v[1] for v in values['TEXCOORD_0']), 0.0)

    def test_skips_footprints_that_plateau_already_models_and_uses_osm_tags(self):
        plateau_house = rect(139.31, 35.75, 10, 10)
        tagged = rect(139.33, 35.75, 20, 15)
        features = [feature('gsi/p', plateau_house), feature('gsi/t', tagged, vt_code=3102)]
        osm = [feature('way/1', tagged, height='31')]
        centroid = [139.31 + 5 / KX, 35.75 + 5 / KY]
        directory, manifest = self.build(features, plateau_centroids=[centroid], osm_features=osm)
        tile, _, _ = read(directory, manifest)
        self.assertEqual(tile['ids'], ['gsi/t'])
        record = json.loads((Path(directory) / tile['buildings']).read_text())['buildings'][0]
        self.assertEqual((record['height'], record['source']), (31.0, 'osm:height'))

    def test_a_fragment_inside_a_large_osm_building_does_not_take_its_tags(self):
        # a small GSI piece inside a tower complex's OSM outline became a 180 m needle
        tower = rect(139.33, 35.75, 100, 80)
        piece = rect(139.33 + 10 / KX, 35.75 + 10 / KY, 15, 15)
        same = rect(139.32, 35.75, 20, 20)
        features = [feature('gsi/piece', piece, vt_code=3102), feature('gsi/same', same, vt_code=3102)]
        osm = [feature('way/tower', tower, height='180', **{'building:levels': '35'}),
               feature('way/same', rect(139.32, 35.75, 21, 19), **{'building:levels': '4'})]
        directory, manifest = self.build(features, osm_features=osm)
        tile, _, _ = read(directory, manifest)
        records = {r['id']: r for r in json.loads((Path(directory) / tile['buildings']).read_text())['buildings']}
        self.assertTrue(records['gsi/piece']['source'].startswith('model:'))
        self.assertEqual((records['gsi/same']['height'], records['gsi/same']['source']), (12.0, 'osm:levels'))

    def test_a_small_footprint_never_becomes_a_needle(self):
        # whatever the tags say, a 5 m x 5 m footprint is not 180 m tall (buildings.plausibility)
        piece = rect(139.32, 35.75, 5, 5)
        osm = [feature('way/mast', rect(139.32, 35.75, 5.2, 5.2), height='180')]
        directory, manifest = self.build([feature('gsi/piece', piece, vt_code=3102)], osm_features=osm)
        tile, _, _ = read(directory, manifest)
        record = json.loads((Path(directory) / tile['buildings']).read_text())['buildings'][0]
        self.assertLessEqual(record['height'], 12 * 5 + 1)
        self.assertTrue(record['source'].endswith('+capped'))

    def test_roof_color_comes_from_the_orthophoto_and_walls_differ_from_it(self):
        image = Image.new('RGB', (400, 300), (40, 120, 40))
        west, south, east, north = BBOX
        ring = rect(139.32, 35.75, 30, 30)
        x0 = int((ring[0][0] - west) / (east - west) * 400) - 2
        x1 = int((ring[1][0] - west) / (east - west) * 400) + 2
        y1 = int((north - ring[0][1]) / (north - south) * 300) + 2
        y0 = int((north - ring[2][1]) / (north - south) * 300) - 2
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                image.putpixel((x, y), (180, 40, 30))
        directory, manifest = self.build([feature('gsi/red', ring, vt_code=3102)], orthophoto=image)
        tile, _, values = read(directory, manifest)
        roof = [c for c, n in zip(values['COLOR_0'], values['NORMAL']) if n[1] > 0.97]
        wall = [c for c, n in zip(values['COLOR_0'], values['NORMAL']) if abs(n[1]) < 0.1]
        self.assertTrue(all(c[0] > 2 * c[2] for c in roof), 'roof keeps the red of the photo')
        self.assertNotEqual(roof[0], wall[0])

    def test_records_the_roof_photo_and_its_bounds_in_local_meters(self):
        bounds = [139.31, 35.745, 139.33, 35.765]
        directory, manifest = self.build([feature('gsi/a', rect(139.32, 35.75, 10, 10))], roof_texture=('roof.jpg', bounds))
        tile = next(t for t in manifest['tiles'] if t['kind'] == 'city-proxy')
        self.assertEqual(tile['roof_texture']['image'], 'roof.jpg')
        minx, miny, maxx, maxy = tile['roof_texture']['bounds_m']
        self.assertAlmostEqual(maxx - minx, 0.02 * KX, delta=1)
        self.assertAlmostEqual(maxy - miny, 0.02 * KY, delta=1)
        self.assertAlmostEqual(minx, (139.31 - 139.32) * KX, delta=1)

    def test_the_facade_kind_guessed_from_the_roof_is_recorded_and_sent_to_the_renderer(self):
        features = [feature('gsi/h', rect(139.31, 35.75, 11, 8)), feature('gsi/w', rect(139.33, 35.75, 60, 40), building='warehouse')]
        directory, manifest = self.build(features, osm_features=[feature('way/9', rect(139.33, 35.75, 60, 40), building='warehouse')])
        tile, _, values = read(directory, manifest)
        records = {r['id']: r for r in json.loads((Path(directory) / tile['buildings']).read_text())['buildings']}
        self.assertEqual(records['gsi/h']['facade'], 'house')
        self.assertEqual(records['gsi/w']['facade'], 'factory')
        styles = {int(round(v[0])) for v in values['_STYLE']}
        self.assertEqual(styles, {fa.STYLE_CODES['house'], fa.STYLE_CODES['factory']})

    def test_wall_hex_carries_the_facade_style_in_its_alpha(self):
        self.assertRegex(cp.wall_hex('a', 30.0), r'^#[0-9a-f]{6}ff$')
        self.assertRegex(cp.wall_hex('a', 6.0), r'^#[0-9a-f]{6}c8$')


class CityShadowTest(unittest.TestCase):
    def test_shadows_fall_away_from_the_sun_lie_on_the_ground_and_do_not_double_up(self):
        tall = feature('gsi/tall', rect(139.32, 35.75, 20, 20), vt_code=3102, height='30')
        twin = feature('gsi/twin', rect(139.32 + 22 / KX, 35.75, 20, 20), vt_code=3102, height='30')
        with TemporaryDirectory() as directory:
            manifest = cp.build_city_proxy_tile([tall, twin], BBOX, Path(directory), ground=lambda lon, lat: 100.0,
                                                osm_features=[tall, twin])
            tile = next(t for t in manifest['tiles'] if t['kind'] == 'city-shadow')
            self.assertEqual(tile['frame'], 'enu')
            document, binary, _ = p3.glb_chunks((Path(directory) / tile['glb']).read_bytes())
            positions = gs._accessor_values(document, binary, document['meshes'][0]['primitives'][0]['attributes']['POSITION'])
            east = [x for x, _, _ in positions]
            north = [-z for _, _, z in positions]
            heights = [y for _, y, _ in positions]
            self.assertTrue(all(abs(h - (100.0 + cp.SHADOW_LIFT_M)) < 1e-3 for h in heights))
            x0 = (139.32 - (BBOX[0] + BBOX[2]) / 2) * KX
            y0 = (35.75 - (BBOX[1] + BBOX[3]) / 2) * KY
            # the shadow reaches 30 m x SHADOW_PER_M beyond the north-east corner of the pair
            self.assertAlmostEqual(max(north) - (y0 + 20), 30 * cp.SHADOW_PER_M[1], delta=0.5)
            self.assertAlmostEqual(max(east) - (x0 + 42), 30 * cp.SHADOW_PER_M[0], delta=0.5)
            area = 0.0
            for i in range(0, len(positions), 3):
                (ax, _, az), (bx, _, bz), (cx, _, cz) = positions[i:i + 3]
                area += abs((bx - ax) * (cz - az) - (cx - ax) * (bz - az)) / 2
            sweep = (42 + 30 * cp.SHADOW_PER_M[0]) * (20 + 30 * cp.SHADOW_PER_M[1])
            self.assertLess(area, sweep, 'overlapping shadows are merged, not stacked')


if __name__ == '__main__':
    unittest.main()
