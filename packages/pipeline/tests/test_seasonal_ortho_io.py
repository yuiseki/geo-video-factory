"""Tests for the network-facing half of seasonal_ortho, with every HTTP call replaced by a fake."""
import contextlib
import io
import json
import struct
import tempfile
import unittest
import urllib.error
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image
from pyproj import Transformer

from support import import_pipeline

seasonal_ortho = import_pipeline('seasonal_ortho')

# A 32x32 px raster of four 16x16 tiles, 10 m pixels, already in Web Mercator.
ORIGIN_X, ORIGIN_Y, RES = 15_440_000.0, 4_210_000.0, 10.0
GEO_TRANSFORM = [RES, 0.0, ORIGIN_X, 0.0, -RES, ORIGIN_Y]


def bbox_for_pixels(col0: int, row0: int, col1: int, row1: int) -> tuple[float, float, float, float]:
    """Degree bbox covering source pixels [col0, col1) x [row0, row1)."""
    to_deg = Transformer.from_crs('EPSG:3857', 'EPSG:4326', always_xy=True)
    west, north = to_deg.transform(ORIGIN_X + col0 * RES, ORIGIN_Y - row0 * RES)
    east, south = to_deg.transform(ORIGIN_X + col1 * RES, ORIGIN_Y - row1 * RES)
    return (west, south, east, north)


def make_cog(tiles: list[np.ndarray | None], *, bits: int = 8, predictor: int = 1) -> tuple[bytes, list[int], list[int]]:
    """Build a little-endian 2x2-tile Deflate TIFF. A None tile is stored as a zero-length (sparse) tile."""
    assert len(tiles) == 4
    template = next(t for t in tiles if t is not None)
    tile_h, tile_w, samples = template.shape
    compressed = []
    for tile in tiles:
        if tile is None:
            compressed.append(b'')
            continue
        encoded = tile.copy()
        if predictor == 2:
            encoded[:, 1:, :] = tile[:, 1:, :] - tile[:, :-1, :]
        compressed.append(zlib.compress(encoded.tobytes()))
    tags = [
        (256, 4, 1, tile_w * 2), (257, 4, 1, tile_h * 2), (258, 3, 1, bits), (259, 3, 1, 8),
        (277, 3, 1, samples), (317, 3, 1, predictor), (322, 4, 1, tile_w), (323, 4, 1, tile_h),
    ]
    arrays_offset = 8 + 2 + (len(tags) + 2) * 12 + 4
    data_offset = arrays_offset + 8 * len(tiles)
    offsets, counts, cursor = [], [], data_offset
    for blob in compressed:
        offsets.append(cursor if blob else 0)
        counts.append(len(blob))
        cursor += len(blob)
    tags += [(324, 4, 4, arrays_offset), (325, 4, 4, arrays_offset + 16)]
    buf = bytearray(struct.pack('<2sHI', b'II', 42, 8))
    buf += struct.pack('<H', len(tags))
    for tag in sorted(tags):
        buf += struct.pack('<HHII', *tag)
    buf += struct.pack('<I', 0)
    buf += struct.pack('<4I', *offsets) + struct.pack('<4I', *counts)
    buf += b''.join(compressed)
    return bytes(buf), offsets, counts


def constant_tile(value, samples: int = 1, dtype=np.uint8) -> np.ndarray:
    tile = np.empty((16, 16, samples), dtype=dtype)
    tile[...] = value
    return tile


class RangeServer:
    """Stands in for seasonal_ortho._http_range and records every requested byte range."""

    def __init__(self, blob: bytes):
        self.blob = blob
        self.requests: list[tuple[str, int, int]] = []

    def __call__(self, url: str, start: int, end_inclusive: int) -> bytes:
        self.requests.append((url, start, end_inclusive))
        return self.blob[start:end_inclusive + 1]


class FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self) -> bytes:
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class HttpHelperTests(unittest.TestCase):
    def test_http_range_sends_inclusive_byte_range_and_user_agent(self):
        with patch.object(seasonal_ortho.urllib.request, 'urlopen', return_value=FakeResponse(b'abc')) as urlopen:
            self.assertEqual(seasonal_ortho._http_range('https://cog.example/a.tif', 100, 199), b'abc')
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, 'https://cog.example/a.tif')
        self.assertEqual(request.get_header('Range'), 'bytes=100-199')
        self.assertEqual(request.get_header('User-agent'), seasonal_ortho.USER_AGENT)

    def test_urlopen_retry_returns_body_after_a_transient_failure(self):
        outcomes = [urllib.error.URLError('reset'), FakeResponse(b'ok')]
        with patch.object(seasonal_ortho.urllib.request, 'urlopen', side_effect=outcomes) as urlopen, \
             patch.object(seasonal_ortho.time, 'sleep') as sleep:
            body = seasonal_ortho._urlopen_retry(seasonal_ortho.urllib.request.Request('https://cog.example/a.tif'))
        self.assertEqual(body, b'ok')
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once()

    def test_urlopen_retry_raises_the_last_error_when_every_attempt_fails(self):
        errors = [urllib.error.URLError('first'), urllib.error.URLError('second'), TimeoutError('third')]
        with patch.object(seasonal_ortho.urllib.request, 'urlopen', side_effect=errors) as urlopen, \
             patch.object(seasonal_ortho.time, 'sleep'):
            with self.assertRaisesRegex(TimeoutError, 'third'):
                seasonal_ortho._urlopen_retry(seasonal_ortho.urllib.request.Request('https://cog.example/a.tif'))
        self.assertEqual(urlopen.call_count, 3)


class ReadCogMercatorBboxTests(unittest.TestCase):
    URL = 'https://cog.example/band.tif'

    def read(self, server, bbox, out_w, out_h):
        with patch.object(seasonal_ortho, '_http_range', side_effect=server):
            return seasonal_ortho.read_cog_mercator_bbox(self.URL, 3857, GEO_TRANSFORM, bbox, out_w, out_h)

    def test_single_band_tiles_land_in_their_own_quadrants(self):
        blob, _, _ = make_cog([constant_tile(v) for v in (10, 20, 30, 40)])
        out = self.read(RangeServer(blob), bbox_for_pixels(0, 0, 32, 32), 4, 4)
        self.assertEqual(out.shape, (4, 4))
        np.testing.assert_allclose(out, [[10, 10, 20, 20], [10, 10, 20, 20], [30, 30, 40, 40], [30, 30, 40, 40]], atol=1e-3)

    def test_only_tiles_intersecting_the_bbox_are_requested(self):
        blob, offsets, counts = make_cog([constant_tile(v) for v in (10, 20, 30, 40)])
        server = RangeServer(blob)
        out = self.read(server, bbox_for_pixels(4, 4, 12, 12), 2, 2)
        np.testing.assert_allclose(out, np.full((2, 2), 10.0), atol=1e-3)
        tile_requests = [r for r in server.requests if r[1] != 0]
        self.assertEqual(tile_requests, [(self.URL, offsets[0], offsets[0] + counts[0] - 1)])

    def test_sixteen_bit_band_with_horizontal_predictor_keeps_reflectance_values(self):
        ramp = np.tile(np.arange(16, dtype=np.uint16) * 300, (16, 1))[..., None]
        tiles = [constant_tile(v, dtype=np.uint16) for v in (1200, 3400, 5600)] + [ramp]
        blob, _, _ = make_cog(tiles, bits=16, predictor=2)
        out = self.read(RangeServer(blob), bbox_for_pixels(0, 0, 32, 32), 4, 4)
        np.testing.assert_allclose(out[:2, :2], 1200.0, atol=1e-2)
        np.testing.assert_allclose(out[:2, 2:], 3400.0, atol=1e-2)
        np.testing.assert_allclose(out[2:, :2], 5600.0, atol=1e-2)
        # The ramp tile increases left to right, which only survives if the predictor was undone in uint16.
        self.assertGreater(out[3, 3], out[3, 2] + 1000)
        self.assertLessEqual(out[3, 3], 4500.0)

    def test_rgb_tiles_come_back_as_uint8_height_width_three(self):
        colours = [(200, 10, 10), (10, 200, 10), (10, 10, 200), (90, 90, 90)]
        blob, _, _ = make_cog([constant_tile(c, samples=3) for c in colours], predictor=2)
        out = self.read(RangeServer(blob), bbox_for_pixels(0, 0, 32, 32), 2, 2)
        self.assertEqual(out.dtype, np.uint8)
        self.assertEqual(out.shape, (2, 2, 3))
        self.assertEqual(out.reshape(4, 3).tolist(), [list(c) for c in colours])

    def test_sparse_tile_reads_as_zero_without_a_request(self):
        blob, offsets, counts = make_cog([constant_tile(10), None, constant_tile(30), constant_tile(40)])
        server = RangeServer(blob)
        out = self.read(server, bbox_for_pixels(0, 0, 32, 32), 4, 4)
        np.testing.assert_allclose(out[:2, 2:], 0.0, atol=1e-3)
        np.testing.assert_allclose(out[:2, :2], 10.0, atol=1e-3)
        fetched = {(start, end) for _, start, end in server.requests if start != 0}
        self.assertEqual(fetched, {(offsets[i], offsets[i] + counts[i] - 1) for i in (0, 2, 3)})


def scene(scene_id: str, cloud: float, bbox: list[float], with_scl: bool = True) -> dict:
    assets = {name: {'href': f'https://scenes.example/{scene_id}/{name}.tif', 'proj:transform': [10, 0, 1, 0, -10, 2]}
              for name in ('red', 'nir', 'visual')}
    if with_scl:
        assets['scl'] = {'href': f'https://scenes.example/{scene_id}/scl.tif', 'proj:transform': [20, 0, 1, 0, -20, 2]}
    return {
        'id': scene_id, 'bbox': bbox, 'assets': assets,
        'properties': {'eo:cloud_cover': cloud, 'proj:epsg': 32654, 'datetime': f'2024-08-0{int(cloud) % 9 + 1}T01:30:00Z'},
    }


def scl_with_cloud_fraction(fraction: float) -> np.ndarray:
    scl = np.full((64, 64), 4, dtype=np.float32)
    scl.reshape(-1)[: int(round(64 * 64 * fraction))] = 9
    return scl


class SearchSentinel2SceneTests(unittest.TestCase):
    BBOX = (138.60, 35.20, 138.86, 35.48)
    COVERING = [138.0, 35.0, 139.2, 36.0]

    def search(self, features, scl_by_scene, **kwargs):
        def fake_read(href, epsg, transform, bbox, out_w, out_h):
            return scl_by_scene[href.split('/')[-2]]

        body = json.dumps({'features': features}).encode()
        with patch.object(seasonal_ortho, '_urlopen_retry', return_value=body) as urlopen, \
             patch.object(seasonal_ortho, 'read_cog_mercator_bbox', side_effect=fake_read) as read:
            try:
                result = seasonal_ortho.search_sentinel2_scene(self.BBOX, '2024-07-15T00:00:00Z/2024-08-31T23:59:59Z', **kwargs)
            finally:
                self.urlopen, self.read = urlopen, read
        return result

    def test_request_asks_stac_for_l2a_scenes_in_bbox_below_cloud_limit(self):
        self.search([scene('a', 3, self.COVERING)], {'a': scl_with_cloud_fraction(0)}, max_cloud=20.0)
        request = self.urlopen.call_args.args[0]
        self.assertEqual(request.full_url, seasonal_ortho.STAC_SEARCH_URL)
        body = json.loads(request.data)
        self.assertEqual(body['collections'], ['sentinel-2-l2a'])
        self.assertEqual(body['bbox'], list(self.BBOX))
        self.assertEqual(body['datetime'], '2024-07-15T00:00:00Z/2024-08-31T23:59:59Z')
        self.assertEqual(body['query'], {'eo:cloud_cover': {'lt': 20.0}})

    def test_scene_clearest_over_the_bbox_beats_scene_with_lower_tile_cloud_cover(self):
        features = [scene('low-tile-cloud', 2, self.COVERING), scene('clear-here', 12, self.COVERING)]
        chosen = self.search(features, {'low-tile-cloud': scl_with_cloud_fraction(0.6), 'clear-here': scl_with_cloud_fraction(0.05)})
        self.assertEqual(chosen['id'], 'clear-here')
        first = self.read.call_args_list[0].args
        self.assertEqual(first, ('https://scenes.example/low-tile-cloud/scl.tif', 32654, [20, 0, 1, 0, -20, 2], self.BBOX, 64, 64))

    def test_search_stops_reading_once_a_cloud_free_scene_is_found(self):
        features = [scene('b', 9, self.COVERING), scene('a', 1, self.COVERING)]
        chosen = self.search(features, {'a': scl_with_cloud_fraction(0), 'b': scl_with_cloud_fraction(0)})
        self.assertEqual(chosen['id'], 'a')
        self.assertEqual(self.read.call_count, 1)

    def test_scenes_not_covering_the_bbox_are_ignored(self):
        partial = scene('partial', 0, [138.0, 35.0, 138.7, 36.0])
        chosen = self.search([partial, scene('full', 30, self.COVERING)], {'full': scl_with_cloud_fraction(0.5)})
        self.assertEqual(chosen['id'], 'full')

    def test_no_covering_scene_is_an_error_naming_the_period(self):
        with self.assertRaisesRegex(RuntimeError, '2024-07-15'):
            self.search([scene('partial', 0, [138.0, 35.0, 138.7, 36.0])], {})
        with self.assertRaises(RuntimeError):
            self.search([], {})

    def test_without_scl_assets_the_lowest_cloud_cover_scene_is_returned(self):
        features = [scene('cloudier', 20, self.COVERING, with_scl=False), scene('clearer', 4, self.COVERING, with_scl=False)]
        chosen = self.search(features, {})
        self.assertEqual(chosen['id'], 'clearer')
        self.read.assert_not_called()


def png_tile(rgb: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', (256, 256), rgb).save(buf, format='PNG')
    return buf.getvalue()


class FakeGsiServer:
    """Scripted replacement for http.client.HTTPSConnection; outcomes are consumed per tile path."""

    def __init__(self, outcomes: dict[str, list]):
        self.outcomes = {path: list(items) for path, items in outcomes.items()}
        self.requested: list[str] = []
        self.hosts: list[str] = []

    def connect(self, host, timeout=None):
        self.hosts.append(host)
        server = self

        class Connection:
            def request(self, method, path, headers=None):
                server.requested.append(path)
                self.path = path

            def getresponse(self):
                queue = server.outcomes[self.path]
                outcome = queue.pop(0) if len(queue) > 1 else queue[0]
                if isinstance(outcome, Exception):
                    raise outcome
                status, body = outcome
                return SimpleNamespace(status=status, read=lambda: body)

            def close(self):
                pass

        return Connection()


class FetchGsiOrthoMosaicTests(unittest.TestCase):
    # At zoom 1 the world is 2x2 tiles, so this bbox needs all four.
    BBOX = (-90.0, -45.0, 90.0, 45.0)
    COLOURS = {(0, 0): (200, 0, 0), (1, 0): (0, 200, 0), (0, 1): (0, 0, 200), (1, 1): (200, 200, 0)}

    def outcomes(self):
        return {f'/xyz/seamlessphoto/1/{x}/{y}.jpg': [(200, png_tile(rgb))] for (x, y), rgb in self.COLOURS.items()}

    def fetch(self, server):
        with patch('http.client.HTTPSConnection', side_effect=server.connect), patch.object(seasonal_ortho.time, 'sleep'):
            return seasonal_ortho.fetch_gsi_ortho_mosaic(self.BBOX, zoom=1)

    def test_tiles_are_pasted_at_their_grid_position_and_bounds_snap_to_the_tile_grid(self):
        server = FakeGsiServer(self.outcomes())
        mosaic, bounds = self.fetch(server)
        self.assertEqual(mosaic.shape, (512, 512, 3))
        for (x, y), rgb in self.COLOURS.items():
            self.assertEqual(tuple(mosaic[y * 256 + 128, x * 256 + 128]), rgb)
        west, south, east, north = bounds
        self.assertAlmostEqual(west, -180.0)
        self.assertAlmostEqual(east, 180.0)
        self.assertAlmostEqual(north, 85.0511287798, places=6)
        self.assertAlmostEqual(south, -85.0511287798, places=6)
        self.assertEqual(sorted(server.requested), sorted(self.outcomes()))
        self.assertEqual(set(server.hosts), {'cyberjapandata.gsi.go.jp'})

    def test_a_dropped_connection_is_retried_and_the_mosaic_is_still_complete(self):
        outcomes = self.outcomes()
        outcomes['/xyz/seamlessphoto/1/1/0.jpg'].insert(0, ConnectionResetError('peer reset'))
        mosaic, _ = self.fetch(FakeGsiServer(outcomes))
        self.assertEqual(tuple(mosaic[128, 256 + 128]), self.COLOURS[(1, 0)])
        self.assertEqual(tuple(mosaic[256 + 128, 256 + 128]), self.COLOURS[(1, 1)])

    def test_a_tile_that_keeps_failing_raises_with_status_and_path(self):
        outcomes = self.outcomes()
        outcomes['/xyz/seamlessphoto/1/0/1.jpg'] = [(404, b'')]
        with self.assertRaisesRegex(RuntimeError, r'HTTP 404: /xyz/seamlessphoto/1/0/1\.jpg'):
            self.fetch(FakeGsiServer(outcomes))


class BuildVegetationMaskTests(unittest.TestCase):
    def test_mask_is_high_over_vegetation_low_over_bare_ground_and_bounded(self):
        red = np.full((40, 40), 1500, dtype=np.uint16)
        nir = np.full((40, 40), 1600, dtype=np.uint16)
        nir[:, 20:] = 6000  # NDVI 0.6 on the right half, 0.03 on the left
        mask = seasonal_ortho.build_vegetation_mask(red, nir)
        self.assertEqual(mask.shape, (40, 40))
        self.assertGreaterEqual(float(mask.min()), 0.0)
        self.assertLessEqual(float(mask.max()), 1.0 + 1e-6)
        self.assertLess(float(mask[20, 5]), 0.01)
        self.assertGreater(float(mask[20, 35]), 0.99)
        # The edge is feathered rather than a hard step.
        self.assertTrue(0.2 < float(mask[20, 20]) < 0.8)

    def test_empty_pixels_do_not_divide_by_zero(self):
        zeros = np.zeros((8, 8), dtype=np.uint16)
        mask = seasonal_ortho.build_vegetation_mask(zeros, zeros)
        self.assertTrue(np.all(np.isfinite(mask)))
        self.assertEqual(float(mask.max()), 0.0)


class MainTests(unittest.TestCase):
    BOUNDS = [138.70, 35.30, 138.80, 35.40]
    SIZE = (24, 16)  # width, height

    def run_main(self, out_dir, seasons, ortho_rgb, bands):
        """bands maps (scene id, asset name) to the array read_cog_mercator_bbox should return."""
        scenes = {dt: scene(name, 7, [138.0, 35.0, 139.2, 36.0]) for name, dt in seasons}

        def fake_read(href, epsg, transform, bbox, out_w, out_h):
            scene_id, asset = href.split('/')[-2], href.split('/')[-1].removesuffix('.tif')
            self.reads.append((scene_id, asset, bbox, out_w, out_h))
            return bands[(scene_id, asset)]

        self.reads = []
        argv = ['--bbox', '138.72, 35.32, 138.78, 35.38', '--zoom', '15', '--out-dir', str(out_dir)]
        for name, dt in seasons:
            argv += ['--season', f'{name}={dt}']
        with patch.object(seasonal_ortho, 'fetch_gsi_ortho_mosaic', return_value=(ortho_rgb, self.BOUNDS)) as fetch, \
             patch.object(seasonal_ortho, 'search_sentinel2_scene', side_effect=lambda bbox, dt, max_cloud: scenes[dt]) as search, \
             patch.object(seasonal_ortho, 'read_cog_mercator_bbox', side_effect=fake_read), \
             contextlib.redirect_stdout(io.StringIO()):
            self.fetch, self.search = fetch, search
            return seasonal_ortho.main(argv)

    def mean_rgb(self, path):
        with Image.open(path) as image:
            return np.asarray(image.convert('RGB'), dtype=np.float32).reshape(-1, 3).mean(axis=0)

    def test_summer_mask_is_shared_and_snow_is_painted_only_on_winter(self):
        w, h = self.SIZE
        ortho = np.full((h, w, 3), 60, dtype=np.uint8)
        flat = np.full((h, w), 1500, dtype=np.uint16)  # red == nir: nothing is vegetation
        white = np.full((h, w, 3), 250, dtype=np.uint8)
        bands = {
            ('summer', 'red'): flat, ('summer', 'nir'): flat, ('summer', 'visual'): white,
            ('winter', 'visual'): white, ('winter', 'scl'): np.full((h, w), 11, dtype=np.float32),
        }
        seasons = [('summer', '2024-07-15T00:00:00Z/2024-08-31T23:59:59Z'), ('winter', '2025-01-10T00:00:00Z/2025-02-20T23:59:59Z')]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'nested' / 'seasonal'
            self.assertEqual(self.run_main(out, seasons, ortho, bands), 0)

            self.fetch.assert_called_once_with((138.72, 35.32, 138.78, 35.38), zoom=15)
            # Sentinel-2 is sampled on the mosaic's real extent and size, not on the requested bbox.
            self.assertEqual({r[2:] for r in self.reads}, {(tuple(self.BOUNDS), w, h)})
            for call in self.search.call_args_list:
                self.assertEqual(call.args[0], tuple(self.BOUNDS))
            # Winter never reads its own red/nir: the summer vegetation mask is reused.
            self.assertNotIn(('winter', 'red'), [r[:2] for r in self.reads])
            self.assertIn(('winter', 'scl'), [r[:2] for r in self.reads])

            with Image.open(out / 'ortho_base.jpg') as base:
                self.assertEqual(base.size, (w, h))
            # No vegetation and no snow class: summer stays the dark ortho. Winter is covered in snow.
            self.assertLess(float(self.mean_rgb(out / 'summer.jpg').max()), 75)
            self.assertGreater(float(self.mean_rgb(out / 'winter.jpg').min()), 215)

            manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['bounds'], self.BOUNDS)
            self.assertEqual((manifest['width'], manifest['height'], manifest['gsiZoom']), (w, h, 15))
            self.assertEqual(list(manifest['seasons']), ['summer', 'winter'])
            self.assertEqual(manifest['seasons']['winter'], {
                'file': 'winter.jpg', 'sceneId': 'winter', 'datetime': '2024-08-08T01:30:00Z', 'cloudCover': 7,
            })

    def test_without_a_summer_scene_each_season_builds_its_own_vegetation_mask(self):
        w, h = self.SIZE
        ortho = np.full((h, w, 3), 120, dtype=np.uint8)
        bands = {
            ('autumn', 'red'): np.full((h, w), 800, dtype=np.uint16),
            ('autumn', 'nir'): np.full((h, w), 5000, dtype=np.uint16),  # NDVI 0.72: everything is vegetation
            ('autumn', 'visual'): np.full((h, w, 3), (200, 90, 30), dtype=np.uint8),
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self.run_main(out, [('autumn', '2024-11-01T00:00:00Z/2024-11-30T23:59:59Z')], ortho, bands)
            self.assertEqual(sorted(r[1] for r in self.reads), ['nir', 'red', 'visual'])
            red, green, blue = self.mean_rgb(out / 'autumn.jpg')
            # The grey ortho takes on the orange hue of the autumn scene.
            self.assertGreater(red, green + 25)
            self.assertGreater(green, blue + 25)
            self.assertEqual(list(json.loads((out / 'manifest.json').read_text(encoding='utf-8'))['seasons']), ['autumn'])

    def test_bbox_with_wrong_number_of_values_is_rejected_before_any_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(seasonal_ortho, 'fetch_gsi_ortho_mosaic') as fetch:
                with self.assertRaisesRegex(ValueError, 'bbox'):
                    seasonal_ortho.main(['--bbox', '138.7,35.3,138.8', '--out-dir', tmp, '--season', 'summer=2024-07-01/2024-08-01'])
            fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
