"""Tests for gsi_tiles.collect_places bookkeeping, its default fetcher and the CLI."""
import email.message
import io
import json
import math
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from PIL import Image

from support import import_pipeline

gsi_tiles = import_pipeline('gsi_tiles')

CENTER = [135.50115, 34.66881]
BASE = 'https://cyberjapandata.gsi.go.jp/xyz'


def tile_bytes(rgb=(120, 160, 200), size=(256, 256), fmt='PNG') -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', size, rgb).save(buf, format=fmt)
    return buf.getvalue()


def place(*layers: str, name: str | None = '道頓堀') -> dict:
    spec = {'center': CENTER, 'layers': list(layers)}
    if name is not None:
        spec['name'] = name
    return spec


def centre_tile(zoom: int = 16) -> tuple[int, int]:
    xf, yf = gsi_tiles.fractional_tile(*CENTER, zoom=zoom)
    return math.floor(xf), math.floor(yf)


class RecordingFetcher:
    def __init__(self, responder):
        self.responder = responder
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        return self.responder(url)


class FakeHttpResponse:
    status = 200

    def __init__(self, body: bytes):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class DefaultFetcherTests(unittest.TestCase):
    def test_returns_status_and_body_and_sends_the_user_agent(self):
        seen = {}

        def fake_urlopen(request, timeout=None):
            seen.update(url=request.full_url, agent=request.get_header('User-agent'), timeout=timeout)
            return FakeHttpResponse(b'tile-bytes')

        with patch.object(gsi_tiles, 'urlopen', side_effect=fake_urlopen):
            self.assertEqual(gsi_tiles._default_fetcher(f'{BASE}/std/16/1/2.png'), (200, b'tile-bytes'))
        self.assertEqual(seen, {'url': f'{BASE}/std/16/1/2.png', 'agent': gsi_tiles.USER_AGENT, 'timeout': 25})

    def test_http_error_is_returned_as_its_status_with_no_body(self):
        error = HTTPError(f'{BASE}/ort_1928/16/1/2.png', 404, 'Not Found', email.message.Message(), io.BytesIO(b'missing'))
        with patch.object(gsi_tiles, 'urlopen', side_effect=error):
            self.assertEqual(gsi_tiles._default_fetcher(f'{BASE}/ort_1928/16/1/2.png'), (404, b''))


class CollectPlacesTests(unittest.TestCase):
    def test_requests_the_tile_grid_around_the_centre_in_row_order_and_keeps_the_raw_tiles(self):
        content = tile_bytes(fmt='JPEG')
        fetch = RecordingFetcher(lambda url: (200, content))
        with TemporaryDirectory() as temp:
            out = Path(temp)
            manifest = gsi_tiles.collect_places({'dotonbori': place('seamlessphoto')}, out, zoom=16, delay=0, fetcher=fetch)
            record = manifest['places']['dotonbori']
            layer = record['layers']['seamlessphoto']

            xf, yf = gsi_tiles.fractional_tile(*CENTER, zoom=16)
            x0, y0 = math.floor(xf - 0.5), math.floor(yf - 0.5)
            expected = [f'{BASE}/seamlessphoto/16/{x0 + dx}/{y0 + dy}.jpg' for dy in (0, 1) for dx in (0, 1)]
            self.assertEqual(fetch.urls, expected)
            self.assertEqual([tile['url'] for tile in layer['tiles']], expected)
            self.assertEqual([tile['http_status'] for tile in layer['tiles']], [200] * 4)
            self.assertEqual(layer['tiles'][3]['raw_file'], f'dotonbori/raw/seamlessphoto/16/{x0 + 1}/{y0 + 1}.jpg')
            for tile in layer['tiles']:
                self.assertEqual((out / tile['raw_file']).read_bytes(), content)

            west, south, east, north = record['bbox_west_south_east_north']
            self.assertTrue(west < CENTER[0] < east and south < CENTER[1] < north)
            self.assertEqual(record['bbox_west_south_east_north'], gsi_tiles.tile_bounds(x0, y0, 2, 2, zoom=16))
            self.assertEqual((record['name'], record['center_lon_lat']), ('道頓堀', CENTER))
            self.assertEqual(layer['period'], gsi_tiles.GSI_TILES['seamlessphoto'][0])
            self.assertTrue(layer['target_pixel_has_image'])
            with Image.open(out / layer['mosaic_file']) as mosaic:
                self.assertEqual(mosaic.size, (512, 512))
            self.assertEqual(manifest['attribution'], gsi_tiles.ATTRIBUTION)
            self.assertEqual(json.loads((out / 'manifest.json').read_text(encoding='utf-8')), manifest)

    def test_grid_size_and_zoom_are_configurable_and_name_defaults_to_the_place_id(self):
        fetch = RecordingFetcher(lambda url: (200, tile_bytes()))
        with TemporaryDirectory() as temp:
            manifest = gsi_tiles.collect_places(
                {'spot': place('std', name=None)}, Path(temp), zoom=14, width_tiles=1, height_tiles=1, delay=0, fetcher=fetch,
            )
            x, y = centre_tile(14)
            self.assertEqual(fetch.urls, [f'{BASE}/std/14/{x}/{y}.png'])
            self.assertEqual(manifest['zoom'], 14)
            self.assertEqual(manifest['places']['spot']['name'], 'spot')
            with Image.open(Path(temp) / 'spot' / 'std.png') as mosaic:
                self.assertEqual(mosaic.size, (256, 256))

    def test_missing_tile_under_the_centre_is_reported_in_the_manifest(self):
        x, y = centre_tile()
        missing = f'{BASE}/ort_old10/16/{x}/{y}.png'
        fetch = RecordingFetcher(lambda url: (404, b'') if url == missing else (200, tile_bytes()))
        with TemporaryDirectory() as temp:
            out = Path(temp)
            layer = gsi_tiles.collect_places({'dotonbori': place('ort_old10')}, out, delay=0, fetcher=fetch)['places']['dotonbori']['layers']['ort_old10']
            self.assertEqual(layer['visible_fraction'], 0.75)
            self.assertFalse(layer['target_pixel_has_image'])
            self.assertEqual(layer['mosaic_file'], 'dotonbori/ort_old10.png')
            failed = [tile for tile in layer['tiles'] if tile['url'] == missing]
            self.assertEqual(failed, [{'url': missing, 'http_status': 404}])
            self.assertEqual(len(list((out / 'dotonbori' / 'raw').rglob('*.png'))), 3)

    def test_layer_with_no_tiles_at_all_has_no_mosaic_file(self):
        with TemporaryDirectory() as temp:
            out = Path(temp)
            layer = gsi_tiles.collect_places(
                {'dotonbori': place('ort_1928')}, out, delay=0, fetcher=lambda url: (404, b''),
            )['places']['dotonbori']['layers']['ort_1928']
            self.assertEqual((layer['mosaic_file'], layer['visible_fraction'], layer['target_pixel_has_image']), (None, 0.0, False))
            self.assertFalse((out / 'dotonbori' / 'ort_1928.png').exists())
            self.assertFalse((out / 'dotonbori' / 'raw').exists())

    def test_unusable_tile_content_is_recorded_as_an_error_and_not_kept(self):
        cases = {
            'unexpected tile size (128, 128)': lambda url: (200, tile_bytes(size=(128, 128))),
            'cannot identify image file': lambda url: (200, b'<html>maintenance</html>'),
        }
        for message, responder in cases.items():
            with self.subTest(message=message), TemporaryDirectory() as temp:
                out = Path(temp)
                layer = gsi_tiles.collect_places(
                    {'dotonbori': place('std')}, out, width_tiles=1, height_tiles=1, delay=0, fetcher=responder,
                )['places']['dotonbori']['layers']['std']
                tile = layer['tiles'][0]
                self.assertEqual(tile['http_status'], 200)
                self.assertIn(message, tile['error'])
                self.assertNotIn('raw_file', tile)
                self.assertIsNone(layer['mosaic_file'])
                self.assertFalse((out / 'dotonbori' / 'raw').exists())

    def test_connection_failure_is_recorded_per_tile_and_collection_continues(self):
        calls = []

        def flaky(url):
            calls.append(url)
            if len(calls) == 1:
                raise URLError('connection reset')
            return 200, tile_bytes()

        with TemporaryDirectory() as temp:
            layers = gsi_tiles.collect_places({'dotonbori': place('std', 'pale')}, Path(temp), delay=0, fetcher=flaky)['places']['dotonbori']['layers']
        self.assertEqual(len(calls), 8)
        first = layers['std']['tiles'][0]
        self.assertIn('connection reset', first['error'])
        self.assertNotIn('http_status', first)
        self.assertEqual(layers['std']['visible_fraction'], 0.75)
        self.assertEqual(layers['pale']['visible_fraction'], 1.0)

    def test_waits_between_tile_requests_only_when_a_delay_is_set(self):
        fetch = lambda url: (200, tile_bytes())
        with TemporaryDirectory() as temp, patch.object(gsi_tiles.time, 'sleep') as sleep:
            gsi_tiles.collect_places({'dotonbori': place('std')}, Path(temp), delay=0.25, fetcher=fetch)
            self.assertEqual([call.args for call in sleep.call_args_list], [(0.25,)] * 4)
            sleep.reset_mock()
            gsi_tiles.collect_places({'dotonbori': place('std')}, Path(temp), delay=0, fetcher=fetch)
            sleep.assert_not_called()

    def test_only_place_and_only_layers_update_an_existing_manifest_in_place(self):
        places = {'dotonbori': place('std', 'pale'), 'umeda': {'name': '梅田', 'center': [135.4959, 34.7025], 'layers': ['std']}}
        kwargs = {'width_tiles': 1, 'height_tiles': 1, 'delay': 0}
        with TemporaryDirectory() as temp:
            out = Path(temp)
            first = gsi_tiles.collect_places(places, out, fetcher=lambda url: (200, tile_bytes()), **kwargs)
            self.assertEqual(sorted(first['places']), ['dotonbori', 'umeda'])

            retry = RecordingFetcher(lambda url: (404, b''))
            second = gsi_tiles.collect_places(places, out, only_place='dotonbori', only_layers={'pale'}, fetcher=retry, **kwargs)
            x, y = centre_tile()
            self.assertEqual(retry.urls, [f'{BASE}/pale/16/{x}/{y}.png'])
            self.assertEqual(second['created_utc'], first['created_utc'])
            self.assertEqual(second['places']['umeda'], first['places']['umeda'])
            self.assertEqual(second['places']['dotonbori']['layers']['std'], first['places']['dotonbori']['layers']['std'])
            self.assertIsNone(second['places']['dotonbori']['layers']['pale']['mosaic_file'])
            self.assertEqual(json.loads((out / 'manifest.json').read_text(encoding='utf-8')), second)

    def test_only_place_without_an_existing_manifest_starts_a_new_one_with_that_place(self):
        places = {'dotonbori': place('std'), 'umeda': {'center': [135.4959, 34.7025], 'layers': ['std']}}
        with TemporaryDirectory() as temp:
            manifest = gsi_tiles.collect_places(
                places, Path(temp), only_place='umeda', width_tiles=1, height_tiles=1, delay=0, fetcher=lambda url: (200, tile_bytes()),
            )
            self.assertEqual(list(manifest['places']), ['umeda'])
            self.assertFalse((Path(temp) / 'dotonbori').exists())

    def test_full_run_replaces_an_existing_manifest(self):
        kwargs = {'width_tiles': 1, 'height_tiles': 1, 'delay': 0, 'fetcher': lambda url: (200, tile_bytes())}
        with TemporaryDirectory() as temp:
            out = Path(temp)
            gsi_tiles.collect_places({'umeda': {'center': [135.4959, 34.7025], 'layers': ['std']}}, out, **kwargs)
            manifest = gsi_tiles.collect_places({'dotonbori': place('std')}, out, **kwargs)
            self.assertEqual(list(manifest['places']), ['dotonbori'])
            self.assertEqual(list(json.loads((out / 'manifest.json').read_text(encoding='utf-8'))['places']), ['dotonbori'])


class CommandLineTests(unittest.TestCase):
    def test_cli_reads_places_and_passes_options_to_collect_places(self):
        places = {'dotonbori': place('std')}
        with TemporaryDirectory() as temp:
            root = Path(temp)
            places_path = root / 'places.json'
            places_path.write_text(json.dumps(places, ensure_ascii=False), encoding='utf-8')
            argv = ['gsi_tiles.py', str(places_path), '--out', str(root / 'out'), '--zoom', '15', '--only', 'dotonbori',
                    '--layers', 'std,,gazo1', '--delay', '0.5']
            with patch.object(sys, 'argv', argv), patch.object(gsi_tiles, 'collect_places') as collect:
                gsi_tiles.main()
            collect.assert_called_once_with(places, root / 'out', zoom=15, only_place='dotonbori', only_layers={'std', 'gazo1'}, delay=0.5)

    def test_cli_defaults_collect_every_place_and_layer_from_the_network_fetcher(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            places_path = root / 'places.json'
            places_path.write_text(json.dumps({'dotonbori': place('std')}, ensure_ascii=False), encoding='utf-8')
            out = root / 'out'
            with patch.object(sys, 'argv', ['gsi_tiles.py', str(places_path), '--out', str(out)]), \
                 patch.object(gsi_tiles, '_default_fetcher', side_effect=lambda url: (200, tile_bytes())) as fetch, \
                 patch.object(gsi_tiles.time, 'sleep') as sleep:
                gsi_tiles.main()
            self.assertEqual(fetch.call_count, 4)
            self.assertEqual([call.args for call in sleep.call_args_list], [(0.2,)] * 4)
            saved = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['zoom'], 16)
            self.assertEqual(saved['places']['dotonbori']['layers']['std']['mosaic_file'], 'dotonbori/std.png')
            self.assertTrue((out / 'dotonbori' / 'std.png').is_file())


if __name__ == '__main__':
    unittest.main()
