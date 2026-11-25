import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from photos import commons_area_catalog as cac
from photos.photo_catalog_rules import is_cc0_or_public_domain


def _q(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))


class Licences(unittest.TestCase):
    def test_cc0_and_public_domain_pass(self):
        for short in ("CC0", "CC0 1.0", "Public domain", "PD-self", "PDM-owner", "Public Domain Mark 1.0"):
            self.assertTrue(is_cc0_or_public_domain(short), short)

    def test_attribution_and_share_alike_do_not(self):
        for short in ("CC BY 2.0", "CC BY-SA 4.0", "CC BY-NC 2.0", "GFDL", ""):
            self.assertFalse(is_cc0_or_public_domain(short), short)


class Grid(unittest.TestCase):
    def test_circles_cover_the_box(self):
        bbox = (139.6, 35.6, 139.8, 35.7)
        centres = cac.grid_centres(bbox, spacing_km=4.0)
        self.assertGreater(len(centres), 4)
        for lon in (139.6, 139.65, 139.7, 139.8):
            for lat in (35.6, 35.65, 35.7):
                d = min(cac.distance_km((lon, lat), c) for c in centres)
                self.assertLessEqual(d, cac.radius_for(4.0) + 1e-6)


class Search(unittest.TestCase):
    def test_both_statements_are_searched_and_pages_followed(self):
        seen = []

        def fetch(url, sleep_fn=None):
            q = _q(url)
            seen.append(q["srsearch"])
            off = int(q.get("sroffset", 0))
            if off == 0:
                return {"query": {"search": [{"title": f"File:{q['srsearch'][:5]}-a.jpg"}]}, "continue": {"sroffset": 1}}
            return {"query": {"search": [{"title": f"File:{q['srsearch'][:5]}-b.jpg"}]}}

        titles = cac.search_circle((139.7, 35.66), 3.0, fetch_fn=fetch, sleep_fn=lambda s: None)
        self.assertEqual(len(titles), 4)
        self.assertTrue(any("P275=Q6938433" in s for s in seen))
        self.assertTrue(any("P6216=Q19652" in s for s in seen))
        # a radius with a decimal point ("2.97km") is silently ignored by CirrusSearch, which then searches
        # the whole of Commons: whole metres only
        self.assertTrue(all("nearcoord:3000m,35.66,139.7" in s for s in seen))

    def test_a_full_circle_is_reported_from_the_total_before_paging(self):
        calls = []

        def fetch(url, sleep_fn=None):
            calls.append(url)
            return {"query": {"searchinfo": {"totalhits": 12000}, "search": [{"title": "File:x.jpg"}]},
                    "continue": {"sroffset": 500}}

        with self.assertRaises(cac.CircleFull):
            cac.search_circle((139.7, 35.66), 3.0, fetch_fn=fetch, sleep_fn=lambda s: None)
        self.assertEqual(len(calls), 1)

    def test_a_search_that_stops_at_the_limit_is_full_even_without_a_total(self):
        def fetch(url, sleep_fn=None):
            q = _q(url)
            off = int(q.get("sroffset", 0))
            more = {"continue": {"sroffset": off + 1}} if off + 1 < 5 else {}
            return {"query": {"search": [{"title": f"File:x{off}.jpg"}]}, **more}

        with self.assertRaises(cac.CircleFull):
            cac.search_circle((139.7, 35.66), 3.0, fetch_fn=fetch, sleep_fn=lambda s: None, max_offset=5)


class Catalog(unittest.TestCase):
    def test_inside_keeps_points_in_the_polygon(self):
        square = [[(139.0, 35.0), (140.0, 35.0), (140.0, 36.0), (139.0, 36.0), (139.0, 35.0)]]
        self.assertTrue(cac.inside((139.5, 35.5), square))
        self.assertFalse(cac.inside((140.5, 35.5), square))

    def test_rows_are_one_per_line_sorted_and_unique(self):
        rows = [{"title": "File:b.jpg", "license": "CC0"}, {"title": "File:a.jpg", "license": "CC0"},
                {"title": "File:b.jpg", "license": "CC0"}]
        out = Path(tempfile.mkdtemp()) / "c.jsonl"
        cac.write_catalog(out, rows)
        lines = out.read_text().splitlines()
        self.assertEqual([json.loads(x)["title"] for x in lines], ["File:a.jpg", "File:b.jpg"])


if __name__ == "__main__":
    unittest.main()
