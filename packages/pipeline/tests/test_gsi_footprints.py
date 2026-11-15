import io
import math
import struct
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from support import import_pipeline

gf = import_pipeline('gsi_footprints')


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _field(number: int, wire: int, payload: bytes) -> bytes:
    key = _varint((number << 3) | wire)
    if wire == 2:
        return key + _varint(len(payload)) + payload
    return key + payload


def _zigzag(n: int) -> int:
    return (n << 1) ^ (n >> 31)


def _square_geometry(x0: int, y0: int, size: int) -> list[int]:
    # MoveTo(1) x0,y0 ; LineTo(3) ; ClosePath(1). Exterior rings are clockwise in tile space (y down).
    cmds = [(1 << 3) | 1, _zigzag(x0), _zigzag(y0), (3 << 3) | 2,
            _zigzag(size), _zigzag(0), _zigzag(0), _zigzag(size), _zigzag(-size), _zigzag(0), (1 << 3) | 7]
    return cmds


def _tile(squares: list[tuple[int, int, int, int]], extent: int = 4096) -> bytes:
    """Build a BldA layer whose features are (x0, y0, size, vt_code) squares."""
    codes = sorted({code for *_, code in squares})
    layer = _field(15, 0, _varint(2)) + _field(1, 2, b'BldA')
    for x0, y0, size, code in squares:
        geometry = b''.join(_varint(v) for v in _square_geometry(x0, y0, size))
        feature = _field(2, 2, b''.join(_varint(v) for v in (0, codes.index(code)))) + _field(3, 0, _varint(3)) + _field(4, 2, geometry)
        layer += _field(2, 2, feature)
    layer += _field(3, 2, b'vt_code')
    for code in codes:
        layer += _field(4, 2, _field(4, 0, _varint(code)))
    layer += _field(5, 0, _varint(extent))
    return _field(3, 2, layer)


class MvtDecodeTest(unittest.TestCase):
    def test_decodes_polygon_features_with_properties(self):
        layers = gf.decode_mvt(_tile([(100, 200, 50, 3101), (1000, 1000, 80, 3102)]))
        self.assertIn('BldA', layers)
        features = layers['BldA']['features']
        self.assertEqual(len(features), 2)
        self.assertEqual(features[0]['properties'], {'vt_code': 3101})
        self.assertEqual(features[1]['properties'], {'vt_code': 3102})
        self.assertEqual(features[0]['type'], 3)
        ring = features[0]['rings'][0]
        self.assertEqual(ring[0], (100, 200))
        self.assertIn((150, 250), ring)

    def test_tile_rings_become_lonlat_polygons_with_exterior_first(self):
        z, x, y = 16, 58129, 25789
        feature = gf.decode_mvt(_tile([(0, 0, 4096, 3101)]))['BldA']['features'][0]
        polygons = gf.feature_polygons_lonlat(feature, z, x, y, 4096)
        self.assertEqual(len(polygons), 1)
        west, south, east, north = gf.tile_bbox(z, x, y)
        lons = [p[0] for p in polygons[0][0]]
        lats = [p[1] for p in polygons[0][0]]
        self.assertAlmostEqual(min(lons), west, places=9)
        self.assertAlmostEqual(max(lons), east, places=9)
        self.assertAlmostEqual(min(lats), south, places=9)
        self.assertAlmostEqual(max(lats), north, places=9)


class FetchFootprintsTest(unittest.TestCase):
    def test_merges_a_building_split_by_a_tile_seam_and_caches_tiles(self):
        z = 16
        x, y = 58129, 25789
        # A building straddling the seam between (x, y) and (x + 1, y), plus a lone house.
        tiles = {
            (x, y): _tile([(4000, 1000, 96, 3102), (500, 500, 60, 3101)]),
            (x + 1, y): _tile([(0, 1000, 120, 3102)]),
        }
        calls = []

        def fetch(url):
            calls.append(url)
            parts = url.rstrip('.pbf').split('/')
            key = (int(parts[-2]), int(parts[-1]))
            return tiles.get(key)

        w, s, e, n = gf.tile_bbox(z, x, y)
        e2 = gf.tile_bbox(z, x + 1, y)[2]
        bbox = [w + 1e-7, s + 1e-7, e2 - 1e-7, n - 1e-7]
        with TemporaryDirectory() as directory:
            features = gf.fetch_gsi_buildings(bbox, Path(directory), zoom=z, fetch=fetch)
            self.assertEqual(len(features), 2)
            codes = sorted(f['properties']['vt_code'] for f in features)
            self.assertEqual(codes, [3101, 3102])
            merged = next(f for f in features if f['properties']['vt_code'] == 3102)
            ring = merged['geometry']['coordinates'][0]
            span = max(p[0] for p in ring) - min(p[0] for p in ring)
            tile_width = e - w
            self.assertAlmostEqual(span, tile_width * (96 + 120) / 4096, delta=tile_width * 2 / 4096)
            self.assertTrue(all(f['id'].startswith('gsi/') for f in features))
            n_calls = len(calls)
            gf.fetch_gsi_buildings(bbox, Path(directory), zoom=z, fetch=fetch)
            self.assertEqual(len(calls), n_calls, 'second run must read the cached tiles')


def _dem_png(value_m: float) -> bytes:
    raw = int(round(value_m * 100))
    color = ((raw >> 16) & 255, (raw >> 8) & 255, raw & 255)
    image = Image.new('RGB', (256, 256), color)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


class DemSamplerTest(unittest.TestCase):
    def test_samples_gsi_dem_png_heights_and_treats_nodata_as_zero(self):
        def fetch(url):
            if '/14/' in url and url.endswith('.png'):
                return _dem_png(123.45)
            return None

        with TemporaryDirectory() as directory:
            sample = gf.dem_sampler([139.31, 35.75, 139.32, 35.76], Path(directory), fetch=fetch)
            self.assertAlmostEqual(sample(139.315, 35.755), 123.45, places=2)

        with TemporaryDirectory() as directory:
            below = gf.dem_sampler([139.31, 35.75, 139.32, 35.76], Path(directory), fetch=lambda url: _dem_png(-2.5))
            self.assertAlmostEqual(below(139.315, 35.755), -2.5, places=2, msg='below sea level: the 24-bit value is negative')

        nodata = Image.new('RGB', (256, 256), (128, 0, 0))
        buffer = io.BytesIO()
        nodata.save(buffer, format='PNG')
        with TemporaryDirectory() as directory:
            sample = gf.dem_sampler([139.31, 35.75, 139.32, 35.76], Path(directory), fetch=lambda url: buffer.getvalue())
            self.assertEqual(sample(139.315, 35.755), 0.0)


class OrthophotoTextureTest(unittest.TestCase):
    def test_mosaics_cached_photo_tiles_and_reports_tile_aligned_bounds(self):
        calls = []

        def fetch(url):
            calls.append(url)
            image = Image.new('RGB', (256, 256), (200, 60, 40))
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG')
            return buffer.getvalue()

        bbox = [139.3100, 35.7500, 139.3120, 35.7515]
        with TemporaryDirectory() as directory:
            image, bounds = gf.orthophoto_texture(bbox, Path(directory), zoom=18, fetch=fetch)
            tiles = gf.tiles_for_bbox(bbox, 18)
            columns = len({x for x, _ in tiles})
            rows = len({y for _, y in tiles})
            self.assertEqual(image.size, (columns * 256, rows * 256))
            self.assertLessEqual(bounds[0], bbox[0])
            self.assertGreaterEqual(bounds[3], bbox[3])
            self.assertGreater(image.getpixel((10, 10))[0], 150)
            n = len(calls)
            gf.orthophoto_texture(bbox, Path(directory), zoom=18, fetch=fetch)
            self.assertEqual(len(calls), n)


if __name__ == '__main__':
    unittest.main()
