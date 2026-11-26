"""osm_crosswalks: OSM crossings as the crosswalks.json the scene builders draw zebra bars from."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import import_pipeline

oc = import_pipeline("world_model.osm_crosswalks")

ELEMENTS = [
    {"type": "node", "id": 1, "lon": 139.0, "lat": 35.0},
    {"type": "node", "id": 2, "lon": 139.0001, "lat": 35.0},
    {"type": "node", "id": 3, "lon": 139.0002, "lat": 35.0},
    {"type": "way", "id": 10, "nodes": [1, 2, 3], "tags": {"highway": "footway", "footway": "crossing", "crossing": "zebra"}},
    {"type": "way", "id": 11, "nodes": [1, 3], "tags": {"highway": "footway", "footway": "crossing", "crossing": "marked", "width": "6.5"}},
    {"type": "way", "id": 12, "nodes": [1, 3], "tags": {"highway": "footway", "footway": "crossing", "crossing": "unmarked"}},
    {"type": "way", "id": 13, "nodes": [1], "tags": {"highway": "footway", "footway": "crossing"}},
]


class Parse(unittest.TestCase):
    def test_marked_crossings_become_lines_from_end_to_end_with_their_width(self):
        cws = oc.from_overpass(ELEMENTS)
        self.assertEqual([c["osm"] for c in cws], [[10], [11]])            # unmarked and one-node ways left out
        self.assertEqual(cws[0]["line"], [[139.0, 35.0], [139.0002, 35.0]])
        self.assertEqual(cws[0]["width"], oc.DEFAULT_WIDTH)
        self.assertEqual(cws[1]["width"], 6.5)


class Fetch(unittest.TestCase):
    def test_a_box_is_asked_once_from_the_own_overpass_and_kept_in_the_shared_cache(self):
        calls = []

        def fetch(url, query):
            calls.append((url, query))
            return {"elements": ELEMENTS}

        with tempfile.TemporaryDirectory() as root, \
                mock.patch.dict(os.environ, {"GEO_VIDEO_CACHE": root, "OVERPASS_URL": "https://overpass.example/api"}):
            path = oc.crosswalks_file([139.0, 35.0, 139.01, 35.01], fetch=fetch)
            again = oc.crosswalks_file([139.0, 35.0, 139.01, 35.01], fetch=lambda u, q: self.fail("asked again"))
            doc = json.loads(Path(path).read_text())
            self.assertEqual(path, again)
            self.assertTrue(str(path).startswith(root))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "https://overpass.example/api")
        self.assertIn("ODbL", doc["source"])
        self.assertEqual(len(doc["crosswalks"]), 2)

    def test_no_public_server_is_ever_called(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit):
            oc.crosswalks_file([139.0, 35.0, 139.01, 35.01], fetch=lambda u, q: {"elements": []})


if __name__ == "__main__":
    unittest.main()
