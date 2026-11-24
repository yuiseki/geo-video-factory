"""Tests for the Wikimedia Commons / Openverse query helpers and their retry wrappers."""
import email.message
import io
import json
import unittest
import urllib.error
import urllib.parse

from support import import_pipeline

sources = import_pipeline('photos.photo_catalog_sources')

CC0_URL = 'https://creativecommons.org/publicdomain/zero/1.0/'


def http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = email.message.Message()
    if retry_after is not None:
        headers['Retry-After'] = retry_after
    return urllib.error.HTTPError('https://example.invalid/api', code, 'error', headers, io.BytesIO(b''))


class FakeResponse:
    def __init__(self, body: bytes, content_type: str | None = None):
        self._body = body
        self.headers = email.message.Message()
        if content_type is not None:
            self.headers['Content-Type'] = content_type

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ScriptedOpener:
    """Stands in for urlopen: each call pops the next outcome and raises it if it is an exception."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []
        self.timeouts = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        self.timeouts.append(timeout)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ScriptedFetch:
    """Stands in for fetch_json_with_retry: returns queued payloads and records the decoded query of each URL."""

    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.urls = []
        self.queries = []

    def __call__(self, url, sleep_fn=None):
        self.urls.append(url)
        parsed = urllib.parse.urlparse(url)
        self.queries.append({key: values[0] for key, values in urllib.parse.parse_qs(parsed.query).items()})
        return self.payloads.pop(0)


def no_sleep(_seconds):
    return None


class RetryWaitTests(unittest.TestCase):
    def test_wait_follows_the_delay_table_and_stays_at_its_last_entry(self):
        exc = urllib.error.URLError('down')
        self.assertEqual([sources._retry_wait_seconds(exc, attempt) for attempt in range(6)], [3, 8, 20, 45, 45, 45])
        self.assertEqual(sources._retry_wait_seconds(exc, 1, delays=(1, 2)), 2)

    def test_retry_after_of_a_429_overrides_the_table_within_1_to_60_seconds(self):
        self.assertEqual(sources._retry_wait_seconds(http_error(429, ' 12 '), 0), 12.0)
        self.assertEqual(sources._retry_wait_seconds(http_error(429, '0'), 0), 1.0)
        self.assertEqual(sources._retry_wait_seconds(http_error(429, '3600'), 0), 60.0)

    def test_retry_after_is_ignored_when_it_is_a_date_or_the_status_is_not_429(self):
        self.assertEqual(sources._retry_wait_seconds(http_error(429, 'Wed, 21 Oct 2026 07:28:00 GMT'), 1), 8)
        self.assertEqual(sources._retry_wait_seconds(http_error(503, '12'), 2), 20)
        self.assertEqual(sources._retry_wait_seconds(http_error(429), 0), 3)


class FetchJsonWithRetryTests(unittest.TestCase):
    def test_returns_decoded_json_and_identifies_itself_to_the_server(self):
        opener = ScriptedOpener(FakeResponse(json.dumps({'名前': '東京'}).encode('utf-8')))
        sleeps = []
        data = sources.fetch_json_with_retry('https://example.invalid/api?x=1', timeout=7, sleep_fn=sleeps.append, opener=opener)
        self.assertEqual(data, {'名前': '東京'})
        self.assertEqual(opener.requests[0].full_url, 'https://example.invalid/api?x=1')
        self.assertEqual(opener.requests[0].get_header('User-agent'), sources.USER_AGENT)
        self.assertEqual(opener.timeouts, [7])
        self.assertEqual(sleeps, [])

    def test_retries_throttling_and_server_errors_then_succeeds(self):
        opener = ScriptedOpener(http_error(429, '5'), http_error(503), FakeResponse(b'{"ok": true}'))
        sleeps = []
        data = sources.fetch_json_with_retry('https://example.invalid/api', sleep_fn=sleeps.append, opener=opener)
        self.assertEqual(data, {'ok': True})
        self.assertEqual(sleeps, [5.0, 8.0])
        self.assertEqual(len(opener.requests), 3)

    def test_client_errors_are_raised_at_once_without_waiting(self):
        opener = ScriptedOpener(http_error(404))
        sleeps = []
        with self.assertRaises(urllib.error.HTTPError) as caught:
            sources.fetch_json_with_retry('https://example.invalid/api', sleep_fn=sleeps.append, opener=opener)
        self.assertEqual(caught.exception.code, 404)
        self.assertEqual((len(opener.requests), sleeps), (1, []))

    def test_gives_up_with_the_last_http_error_after_max_retries(self):
        opener = ScriptedOpener(http_error(500), http_error(502), http_error(504))
        sleeps = []
        with self.assertRaises(urllib.error.HTTPError) as caught:
            sources.fetch_json_with_retry('https://example.invalid/api', max_retries=2, sleep_fn=sleeps.append, opener=opener)
        self.assertEqual(caught.exception.code, 504)
        self.assertEqual(sleeps, [3.0, 8.0])

    def test_connection_failures_are_retried_then_raised(self):
        recovered = ScriptedOpener(urllib.error.URLError('reset'), TimeoutError('slow'), FakeResponse(b'[]'))
        sleeps = []
        self.assertEqual(sources.fetch_json_with_retry('https://example.invalid/api', sleep_fn=sleeps.append, opener=recovered), [])
        self.assertEqual(sleeps, [3.0, 8.0])

        failing = ScriptedOpener(OSError('unreachable'), OSError('still unreachable'))
        with self.assertRaisesRegex(OSError, 'still unreachable'):
            sources.fetch_json_with_retry('https://example.invalid/api', max_retries=1, sleep_fn=no_sleep, opener=failing)
        self.assertEqual(failing.outcomes, [])


class DownloadBytesWithRetryTests(unittest.TestCase):
    def test_returns_body_and_content_type(self):
        opener = ScriptedOpener(FakeResponse(b'\xff\xd8jpeg', 'image/jpeg'))
        data, ctype = sources.download_bytes_with_retry('https://example.invalid/a.jpg', timeout=9, sleep_fn=no_sleep, opener=opener)
        self.assertEqual((data, ctype), (b'\xff\xd8jpeg', 'image/jpeg'))
        self.assertEqual(opener.requests[0].get_header('User-agent'), sources.USER_AGENT)
        self.assertEqual(opener.timeouts, [9])

    def test_missing_content_type_is_reported_as_empty_string(self):
        opener = ScriptedOpener(FakeResponse(b'data'))
        self.assertEqual(sources.download_bytes_with_retry('https://example.invalid/a', sleep_fn=no_sleep, opener=opener), (b'data', ''))

    def test_retries_server_errors_and_connection_failures_then_succeeds(self):
        opener = ScriptedOpener(http_error(502), urllib.error.URLError('reset'), FakeResponse(b'ok', 'image/png'))
        sleeps = []
        self.assertEqual(
            sources.download_bytes_with_retry('https://example.invalid/a.png', sleep_fn=sleeps.append, opener=opener),
            (b'ok', 'image/png'),
        )
        self.assertEqual(sleeps, [3.0, 8.0])

    def test_forbidden_is_raised_at_once_and_persistent_failures_after_max_retries(self):
        forbidden = ScriptedOpener(http_error(403))
        sleeps = []
        with self.assertRaises(urllib.error.HTTPError) as caught:
            sources.download_bytes_with_retry('https://example.invalid/a', sleep_fn=sleeps.append, opener=forbidden)
        self.assertEqual((caught.exception.code, sleeps), (403, []))

        throttled = ScriptedOpener(http_error(429, '2'), http_error(429, '2'))
        with self.assertRaises(urllib.error.HTTPError):
            sources.download_bytes_with_retry('https://example.invalid/a', max_retries=1, sleep_fn=sleeps.append, opener=throttled)
        self.assertEqual(sleeps, [2.0])

        offline = ScriptedOpener(urllib.error.URLError('no route'))
        with self.assertRaises(urllib.error.URLError):
            sources.download_bytes_with_retry('https://example.invalid/a', max_retries=0, sleep_fn=sleeps.append, opener=offline)
        self.assertEqual(sleeps, [2.0])


class CommonsSearchTests(unittest.TestCase):
    def test_cc0_search_is_restricted_to_the_cc_zero_category_and_file_namespace(self):
        fetch = ScriptedFetch({'query': {'search': [{'title': 'File:A.jpg'}, {'title': 'File:B.jpg'}]}})
        titles = sources.query_commons_search('  渋谷 交差点 ', limit=10, sleep_fn=no_sleep, fetch_fn=fetch)
        self.assertEqual(titles, ['File:A.jpg', 'File:B.jpg'])
        self.assertTrue(fetch.urls[0].startswith('https://commons.wikimedia.org/w/api.php?'))
        self.assertEqual(fetch.queries[0], {
            'action': 'query', 'list': 'search', 'srsearch': '渋谷 交差点 incategory:"CC-Zero" filetype:bitmap',
            'srnamespace': '6', 'srlimit': '10', 'sroffset': '0', 'format': 'json',
        })

    def test_ccby_mode_searches_without_the_category_restriction(self):
        fetch = ScriptedFetch({'query': {'search': []}})
        self.assertEqual(sources.query_commons_search('Shibuya', license_mode='ccby_nosa', sleep_fn=no_sleep, fetch_fn=fetch), [])
        self.assertEqual(fetch.queries[0]['srsearch'], 'Shibuya filetype:bitmap')

    def test_follows_continuation_until_the_limit_and_never_asks_for_more_than_needed(self):
        first = {'query': {'search': [{'title': f'File:{i}.jpg'} for i in range(50)]}, 'continue': {'sroffset': 50}}
        second = {'query': {'search': [{'title': f'File:{i}.jpg'} for i in range(50, 60)]}, 'continue': {}}
        third = {'query': {'search': [{'title': 'File:60.jpg'}]}}
        fetch = ScriptedFetch(first, second, third)
        sleeps = []
        titles = sources.query_commons_search('station', limit=70, sleep_fn=sleeps.append, fetch_fn=fetch)
        self.assertEqual(titles, [f'File:{i}.jpg' for i in range(61)])
        self.assertEqual([(q['srlimit'], q['sroffset']) for q in fetch.queries], [('50', '0'), ('20', '50'), ('10', '60')])
        self.assertEqual(sleeps, [0.35, 0.35])

    def test_stops_when_the_limit_is_reached_even_if_more_results_exist(self):
        page = {'query': {'search': [{'title': 'File:A.jpg'}, {'title': 'File:B.jpg'}]}, 'continue': {'sroffset': 2}}
        fetch = ScriptedFetch(page)
        self.assertEqual(sources.query_commons_search('x', limit=2, sleep_fn=no_sleep, fetch_fn=fetch), ['File:A.jpg', 'File:B.jpg'])
        self.assertEqual(len(fetch.urls), 1)


class CommonsCategoryTests(unittest.TestCase):
    def test_category_prefix_is_added_only_when_missing(self):
        for given in ('Shibuya Crossing', 'Category:Shibuya Crossing'):
            with self.subTest(given=given):
                fetch = ScriptedFetch({'query': {'categorymembers': [{'title': 'File:A.jpg'}]}})
                self.assertEqual(sources.query_commons_category(given, limit=5, sleep_fn=no_sleep, fetch_fn=fetch), ['File:A.jpg'])
                self.assertEqual(fetch.queries[0], {
                    'action': 'query', 'list': 'categorymembers', 'cmtitle': 'Category:Shibuya Crossing',
                    'cmtype': 'file', 'cmlimit': '5', 'format': 'json',
                })

    def test_follows_cmcontinue_tokens_across_pages(self):
        first = {'query': {'categorymembers': [{'title': f'File:{i}.jpg'} for i in range(50)]}, 'continue': {'cmcontinue': 'file|TOKEN|1'}}
        second = {'query': {'categorymembers': [{'title': 'File:last.jpg'}]}}
        fetch = ScriptedFetch(first, second)
        sleeps = []
        titles = sources.query_commons_category('Tokyo', limit=120, sleep_fn=sleeps.append, fetch_fn=fetch)
        self.assertEqual(len(titles), 51)
        self.assertEqual(titles[-1], 'File:last.jpg')
        self.assertNotIn('cmcontinue', fetch.queries[0])
        self.assertEqual((fetch.queries[1]['cmcontinue'], fetch.queries[1]['cmlimit']), ('file|TOKEN|1', '50'))
        self.assertEqual(sleeps, [0.35])


class CommonsGeosearchTests(unittest.TestCase):
    def test_returns_titles_around_the_point_and_skips_entries_without_one(self):
        fetch = ScriptedFetch({'query': {'geosearch': [{'title': 'File:A.jpg'}, {'pageid': 9}, {'title': 'File:B.jpg'}]}})
        titles = sources.query_commons_geosearch(35.6595, 139.7005, radius_m=250, limit=40, sleep_fn=no_sleep, fetch_fn=fetch)
        self.assertEqual(titles, ['File:A.jpg', 'File:B.jpg'])
        self.assertEqual(fetch.queries[0], {
            'action': 'query', 'list': 'geosearch', 'gscoord': '35.6595|139.7005', 'gsradius': '250',
            'gsnamespace': '6', 'gslimit': '40', 'format': 'json',
        })

    def test_radius_and_limit_are_clamped_to_what_the_api_accepts(self):
        for radius, limit, expected in ((1, 0, ('10', '1')), (50000, 9999, ('10000', '500')), (300.9, 80, ('300', '80'))):
            with self.subTest(radius=radius, limit=limit):
                fetch = ScriptedFetch({})
                self.assertEqual(sources.query_commons_geosearch(0, 0, radius_m=radius, limit=limit, sleep_fn=no_sleep, fetch_fn=fetch), [])
                self.assertEqual((fetch.queries[0]['gsradius'], fetch.queries[0]['gslimit']), expected)


def commons_page(title='File:Shibuya.jpg', mime='image/jpeg', width=4000, height=3000, license_short='CC0', license_url=CC0_URL, **extra):
    info = {
        'mime': mime, 'width': width, 'height': height, 'size': 123456,
        'url': f'https://upload.example.invalid/{title}', 'descriptionurl': f'https://commons.example.invalid/{title}',
        'extmetadata': {'LicenseShortName': {'value': license_short}, 'LicenseUrl': {'value': license_url}},
    }
    info.update(extra.pop('info', {}))
    info['extmetadata'].update(extra.pop('meta', {}))
    return {'title': title, 'imageinfo': [info], **extra}


def details_payload(*pages):
    return {'query': {'pages': {str(index): page for index, page in enumerate(pages)}}}


class CommonsDetailsTests(unittest.TestCase):
    def test_builds_a_catalog_record_from_the_page_metadata(self):
        page = commons_page(
            info={'thumburl': 'https://upload.example.invalid/thumb/2560px-Shibuya.jpg'},
            meta={
                'Artist': {'value': '<a href="//commons.example.invalid/User:A">Photo&nbsp;Grapher</a>'},
                'ImageDescription': {'value': '<p>Scramble crossing\n at <b>night</b></p>'},
                'DateTimeOriginal': {'value': '2024-04-01 19:30:00'},
            },
            categories=[{'title': 'Category:Shibuya'}, {'ns': 14}, {'title': 'Category:Night in Tokyo'}],
            coordinates=[{'lat': 35.6595, 'lon': 139.7005}],
        )
        fetch = ScriptedFetch(details_payload(page))
        records = sources.fetch_commons_details(['File:Shibuya.jpg'], sleep_fn=no_sleep, fetch_fn=fetch)
        self.assertEqual(records, [{
            'source': 'wikimedia_commons',
            'title': 'File:Shibuya.jpg',
            'creator': 'Photo Grapher',
            'license': 'CC0',
            'license_url': CC0_URL,
            'description': 'Scramble crossing at night',
            'categories': 'Category:Shibuya | Category:Night in Tokyo',
            'datetime': '2024-04-01 19:30:00',
            'mime': 'image/jpeg',
            'download_url': 'https://upload.example.invalid/thumb/2560px-Shibuya.jpg',
            'original_url': 'https://upload.example.invalid/File:Shibuya.jpg',
            'landing_url': 'https://commons.example.invalid/File:Shibuya.jpg',
            'orig_width': 4000,
            'orig_height': 3000,
            'orig_bytes': 123456,
            'coordinates': [139.7005, 35.6595],
        }])
        self.assertEqual(fetch.queries[0]['titles'], 'File:Shibuya.jpg')
        self.assertEqual(fetch.queries[0]['prop'], 'imageinfo|coordinates|categories')
        self.assertEqual(fetch.queries[0]['iiurlwidth'], '2560')

    def test_record_without_optional_metadata_uses_the_original_url_and_no_coordinates(self):
        fetch = ScriptedFetch(details_payload(commons_page(coordinates=[{'globe': 'earth'}])))
        record = sources.fetch_commons_details(['File:Shibuya.jpg'], sleep_fn=no_sleep, fetch_fn=fetch)[0]
        self.assertEqual(record['download_url'], record['original_url'])
        self.assertEqual((record['creator'], record['description'], record['categories'], record['datetime']), ('Unknown', '', '', ''))
        self.assertIsNone(record['coordinates'])

    def test_long_text_fields_are_truncated(self):
        page = commons_page(
            meta={'Artist': {'value': 'a' * 500}, 'ImageDescription': {'value': 'd' * 500}, 'DateTimeOriginal': {'value': '1' * 500}},
            categories=[{'title': 'Category:' + 'c' * 500}],
        )
        record = sources.fetch_commons_details(['File:Shibuya.jpg'], sleep_fn=no_sleep, fetch_fn=ScriptedFetch(details_payload(page)))[0]
        self.assertEqual([len(record[key]) for key in ('creator', 'description', 'categories', 'datetime')], [120, 300, 400, 80])

    def test_pages_that_cannot_be_used_as_photos_are_left_out(self):
        pages = [
            {'title': 'File:Missing.jpg', 'missing': ''},
            commons_page('File:Clip.webm', mime='video/webm'),
            commons_page('File:Diagram.svg', mime='image/svg+xml'),
            commons_page('File:Small.jpg', width=1199, height=800),
            commons_page('File:Sharealike.jpg', license_short='CC BY-SA 4.0', license_url='https://creativecommons.org/licenses/by-sa/4.0'),
            commons_page('File:Attribution.jpg', license_short='CC BY 4.0', license_url='https://creativecommons.org/licenses/by/4.0'),
            commons_page('File:Tall.png', mime='image/png', width=800, height=1200),
            commons_page('File:Keep.webp', mime='image/webp'),
        ]
        records = sources.fetch_commons_details([p['title'] for p in pages], sleep_fn=no_sleep, fetch_fn=ScriptedFetch(details_payload(*pages)))
        self.assertEqual([r['title'] for r in records], ['File:Tall.png', 'File:Keep.webp'])

    def test_ccby_mode_keeps_attribution_licences_with_their_own_name_and_url(self):
        by_url = 'https://creativecommons.org/licenses/by/4.0'
        pages = [
            commons_page('File:Attribution.jpg', license_short='CC BY 4.0', license_url=by_url),
            commons_page('File:Sharealike.jpg', license_short='CC BY-SA 4.0', license_url='https://creativecommons.org/licenses/by-sa/4.0'),
            commons_page('File:Zero.jpg'),
        ]
        records = sources.fetch_commons_details(
            [p['title'] for p in pages], license_mode='ccby_nosa', sleep_fn=no_sleep, fetch_fn=ScriptedFetch(details_payload(*pages)),
        )
        self.assertEqual(
            [(r['title'], r['license'], r['license_url']) for r in records],
            [('File:Attribution.jpg', 'CC BY 4.0', by_url), ('File:Zero.jpg', 'CC0', CC0_URL)],
        )

    def test_a_licence_known_only_by_its_url_is_recorded_under_its_own_name(self):
        """Commons sometimes leaves LicenseShortName empty. An attribution licence must never be written down as CC0:
        the credit it requires would be dropped."""
        by_url = 'https://creativecommons.org/licenses/by/4.0'
        pages = [
            commons_page('File:ByUrlOnly.jpg', license_short='', license_url=by_url),
            commons_page('File:By2UrlOnly.jpg', license_short='', license_url='https://creativecommons.org/licenses/by/2.0/deed.en'),
            commons_page('File:ZeroUrlOnly.jpg', license_short='', license_url=CC0_URL),
            commons_page('File:ByNameOnly.jpg', license_short='CC BY 3.0', license_url=''),
            commons_page('File:ZeroNameOnly.jpg', license_short='CC0', license_url=''),
        ]
        records = sources.fetch_commons_details(
            [p['title'] for p in pages], license_mode='ccby_nosa', sleep_fn=no_sleep, fetch_fn=ScriptedFetch(details_payload(*pages)),
        )
        self.assertEqual(
            [(r['title'], r['license'], r['license_url']) for r in records],
            [
                ('File:ByUrlOnly.jpg', 'CC BY 4.0', by_url),
                ('File:By2UrlOnly.jpg', 'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0/deed.en'),
                ('File:ZeroUrlOnly.jpg', 'CC0', CC0_URL),
                ('File:ByNameOnly.jpg', 'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0/'),
                ('File:ZeroNameOnly.jpg', 'CC0', CC0_URL),
            ],
        )

    def test_an_attribution_licence_without_a_version_gets_no_invented_url(self):
        pages = [commons_page('File:ByBare.jpg', license_short='CC BY', license_url='')]
        records = sources.fetch_commons_details(
            ['File:ByBare.jpg'], license_mode='ccby_nosa', sleep_fn=no_sleep, fetch_fn=ScriptedFetch(details_payload(*pages)),
        )
        self.assertEqual([(r['license'], r['license_url']) for r in records], [('CC BY', '')])

    def test_titles_are_requested_in_batches_of_25(self):
        titles = [f'File:{i}.jpg' for i in range(60)]
        fetch = ScriptedFetch(details_payload(commons_page('File:0.jpg')), {}, details_payload(commons_page('File:50.jpg')))
        sleeps = []
        records = sources.fetch_commons_details(titles, sleep_fn=sleeps.append, fetch_fn=fetch)
        self.assertEqual([q['titles'].split('|') for q in fetch.queries], [titles[:25], titles[25:50], titles[50:]])
        self.assertEqual([r['title'] for r in records], ['File:0.jpg', 'File:50.jpg'])
        self.assertEqual(sleeps, [0.35, 0.35, 0.35])

    def test_no_titles_means_no_requests(self):
        fetch = ScriptedFetch()
        self.assertEqual(sources.fetch_commons_details([], sleep_fn=no_sleep, fetch_fn=fetch), [])
        self.assertEqual(fetch.urls, [])


def openverse_result(**overrides):
    result = {
        'id': 'abc-123', 'title': 'Shibuya at dusk', 'creator': 'someone', 'license': 'cc0', 'license_version': '1.0',
        'license_url': CC0_URL, 'source': 'Flickr', 'url': 'https://images.example.invalid/1.jpg',
        'foreign_landing_url': 'https://photos.example.invalid/1', 'width': 3000, 'height': 2000,
    }
    result.update(overrides)
    return result


class OpenverseTests(unittest.TestCase):
    def test_cc0_result_becomes_a_catalog_record(self):
        fetch = ScriptedFetch({'results': [openverse_result()]}, {'results': []})
        sleeps = []
        records = sources.query_openverse('渋谷 夕景', sleep_fn=sleeps.append, fetch_fn=fetch)
        self.assertEqual(records, [{
            'source': 'openverse/flickr', 'title': 'Shibuya at dusk', 'creator': 'someone', 'license': 'CC0 1.0',
            'license_url': CC0_URL, 'description': '', 'categories': '', 'datetime': '', 'mime': '',
            'download_url': 'https://images.example.invalid/1.jpg', 'original_url': 'https://images.example.invalid/1.jpg',
            'landing_url': 'https://photos.example.invalid/1', 'orig_width': 3000, 'orig_height': 2000,
            'orig_bytes': 0, 'coordinates': None,
        }])
        self.assertTrue(fetch.urls[0].startswith('https://api.openverse.org/v1/images/?'))
        self.assertEqual(fetch.queries[0], {'q': '渋谷 夕景', 'license': 'cc0', 'category': 'photograph', 'page_size': '20', 'page': '1'})
        # An empty page ends the paging before the third request.
        self.assertEqual([q['page'] for q in fetch.queries], ['1', '2'])
        self.assertEqual(sleeps, [0.35])

    def test_requests_exactly_the_given_number_of_pages_when_all_have_results(self):
        fetch = ScriptedFetch(*[{'results': [openverse_result(id=str(page))]} for page in range(2)])
        records = sources.query_openverse('x', pages=2, sleep_fn=no_sleep, fetch_fn=fetch)
        self.assertEqual(len(records), 2)
        self.assertEqual([q['page'] for q in fetch.queries], ['1', '2'])

    def test_cc0_mode_drops_results_whose_licence_is_not_cc0(self):
        results = [openverse_result(id='by', license='by'), openverse_result(id='sa', license='by-sa'),
                   openverse_result(id='none', license=None), openverse_result(id='zero', title=None, license=' CC0 ')]
        records = sources.query_openverse('x', pages=1, sleep_fn=no_sleep, fetch_fn=ScriptedFetch({'results': results}))
        self.assertEqual([(r['title'], r['license']) for r in records], [('zero', 'CC0 1.0')])

    def test_ccby_mode_asks_for_and_labels_attribution_licences(self):
        results = [
            openverse_result(id='by2', license='by', license_version='2.0', license_url=None),
            openverse_result(id='by-default', license='BY', license_version=None, license_url='https://licence.example.invalid/by'),
            openverse_result(id='sa', license='by-sa'),
            openverse_result(id='zero', license_url=None),
        ]
        fetch = ScriptedFetch({'results': results})
        records = sources.query_openverse('x', pages=1, license_mode='ccby_nosa', sleep_fn=no_sleep, fetch_fn=fetch)
        self.assertEqual(fetch.queries[0]['license'], 'cc0,by')
        self.assertEqual([(r['license'], r['license_url']) for r in records], [
            ('CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0/'),
            ('CC BY 4.0', 'https://licence.example.invalid/by'),
            ('CC0 1.0', CC0_URL),
        ])

    def test_results_without_image_url_or_below_1200_pixels_are_left_out(self):
        results = [
            openverse_result(id='no-url', url=None),
            openverse_result(id='small', width=1199, height=900),
            openverse_result(id='edge', title='edge', width=900, height=1200),
            openverse_result(id='unknown-size', title='unknown size', width=None, height=None),
        ]
        records = sources.query_openverse('x', pages=1, sleep_fn=no_sleep, fetch_fn=ScriptedFetch({'results': results}))
        self.assertEqual([(r['title'], r['orig_width'], r['orig_height']) for r in records], [('edge', 900, 1200), ('unknown size', 0, 0)])

    def test_rawpixel_is_skipped_unless_asked_for(self):
        results = [openverse_result(id='raw', source=' RawPixel '), openverse_result(id='other', source=None)]
        skipped = sources.query_openverse('x', pages=1, sleep_fn=no_sleep, fetch_fn=ScriptedFetch({'results': results}))
        self.assertEqual([r['source'] for r in skipped], ['openverse/unknown'])
        kept = sources.query_openverse('x', pages=1, skip_rawpixel=False, sleep_fn=no_sleep, fetch_fn=ScriptedFetch({'results': results}))
        self.assertEqual([r['source'] for r in kept], ['openverse/rawpixel', 'openverse/unknown'])

    def test_missing_optional_fields_fall_back_to_id_unknown_creator_and_image_url(self):
        result = openverse_result(title='', creator=None, foreign_landing_url=None)
        record = sources.query_openverse('x', pages=1, sleep_fn=no_sleep, fetch_fn=ScriptedFetch({'results': [result]}))[0]
        self.assertEqual((record['title'], record['creator'], record['landing_url']), ('abc-123', 'Unknown', result['url']))
        long_creator = openverse_result(creator='c' * 300)
        record = sources.query_openverse('x', pages=1, sleep_fn=no_sleep, fetch_fn=ScriptedFetch({'results': [long_creator]}))[0]
        self.assertEqual(len(record['creator']), 120)

    def test_query_openverse_cc0_never_returns_attribution_licences(self):
        results = [openverse_result(id='by', license='by'), openverse_result(id='zero'), openverse_result(id='raw', source='rawpixel')]
        fetch = ScriptedFetch({'results': results})
        records = sources.query_openverse_cc0('x', pages=1, sleep_fn=no_sleep, fetch_fn=fetch)
        self.assertEqual([r['license'] for r in records], ['CC0 1.0'])
        self.assertEqual(fetch.queries[0]['license'], 'cc0')
        with_rawpixel = sources.query_openverse_cc0('x', pages=1, skip_rawpixel=False, sleep_fn=no_sleep, fetch_fn=ScriptedFetch({'results': results}))
        self.assertEqual(len(with_rawpixel), 2)


if __name__ == '__main__':
    unittest.main()
