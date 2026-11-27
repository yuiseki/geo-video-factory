"""gyazo_photos: the owner's Gyazo photos tagged #publish_as_cc0, kept out of the repository (gyazo.json is ignored:
a Gyazo id opens the photo), used only when a step is given --include-gyazo."""
import json
import tempfile
import unittest
from pathlib import Path

from support import import_pipeline

gz = import_pipeline("photos.gyazo_photos")
photo_store = import_pipeline("photos.photo_store")

ITEM = {"image_id": "gyazo-test-photo-id", "permalink_url": "https://gyazo.com/gyazo-test-photo-id",
        "url": "https://i.gyazo.com/gyazo-test-photo-id.jpg", "access_policy": "anyone",
        "metadata": {"app": "Gyazo Android", "desc": "#publish_as_cc0",
                     "exif_normalized": {"latitude": 35.6983, "longitude": 139.7731, "time": "2026-11-23T06:10:00.000Z"}}}


class Record(unittest.TestCase):
    def test_a_tagged_photo_is_a_cc0_row_with_its_place_and_local_time(self):
        row = gz.record(ITEM, creator="the owner")
        self.assertEqual(row["license"], "CC0")
        self.assertEqual(row["creator"], "the owner")
        self.assertEqual(row["coordinates"], [139.7731, 35.6983])
        self.assertEqual(row["date"], "2026-11-23")
        self.assertEqual(row["time_of_day"], "day")               # 15:10 in Tokyo (photo_catalog_rules)
        self.assertEqual(photo_store.photo_ref(row), "gyazo:gyazo-test-photo-id")

    def test_a_photo_without_the_tag_or_not_public_is_refused(self):
        self.assertIsNone(gz.record(dict(ITEM, metadata=dict(ITEM["metadata"], desc="lunch")), creator="x"))
        self.assertIsNone(gz.record(dict(ITEM, access_policy="owner"), creator="x"))

    def test_a_photo_without_a_place_has_no_coordinates(self):
        item = dict(ITEM, metadata=dict(ITEM["metadata"], exif_normalized=None))
        self.assertIsNone(gz.record(item, creator="x")["coordinates"])


class Merge(unittest.TestCase):
    def test_the_search_result_lends_its_tag_to_a_detail_without_one(self):
        got = {"image_id": "gyazo-test-photo-id", "access_policy": "anyone", "url": "u", "permalink_url": "p",
               "metadata": {"desc": "", "exif_normalized": {"latitude": 35.0, "longitude": 139.0, "time": "2026-11-23T03:00:00Z"},
                            "exif": {"GPS Image Direction": "123.45", "Focal Length in 35mm Film": "26"}}}
        row = gz.record(gz.merge(ITEM, got), creator="x")
        self.assertIsNotNone(row)
        self.assertEqual((row["heading"], row["focal_35mm"]), (123.45, 26.0))

    def test_no_heading_when_exif_has_none(self):
        self.assertIsNone(gz.record(ITEM, creator="x")["heading"])


class Near(unittest.TestCase):
    def test_only_the_rows_within_the_radius_of_a_centre(self):
        rows = [{"coordinates": [139.7731, 35.6983]}, {"coordinates": [139.7750, 35.6983]}, {"coordinates": None}]
        self.assertEqual(len(gz.near(rows, (139.7731, 35.6983), 100)), 1)     # the second is about 170 m east
        self.assertEqual(len(gz.near(rows, (139.7731, 35.6983), 300)), 2)


class File(unittest.TestCase):
    def test_rows_are_written_one_per_line_sorted_and_read_back(self):
        path = Path(tempfile.mkdtemp()) / "gyazo.json"
        rows = [dict(gz.record(ITEM, creator="x"), photo="gyazo:b"), dict(gz.record(ITEM, creator="x"), photo="gyazo:a")]
        gz.write(path, rows)
        lines = path.read_text().splitlines()
        self.assertEqual([json.loads(l.rstrip(","))["photo"] for l in lines[1:-1]], ["gyazo:a", "gyazo:b"])
        self.assertEqual([r["photo"] for r in gz.read(path)], ["gyazo:a", "gyazo:b"])
        self.assertEqual(gz.read(path.with_name("missing.json")), [])


if __name__ == "__main__":
    unittest.main()
