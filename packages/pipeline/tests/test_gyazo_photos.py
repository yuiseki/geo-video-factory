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


def jpeg_with_exif(lat, lon, heading, taken="2026:11:27 14:52:15", focal=16):
    import io
    from PIL import Image
    img = Image.new("RGB", (8, 6), (90, 60, 30))
    exif = img.getexif()
    exif[0x0110] = "Pixel 7"
    sub = exif.get_ifd(0x8769)
    sub[0x9003] = taken
    sub[0xA405] = focal
    gps = exif.get_ifd(0x8825)

    def dms(v):
        d = int(v); m = int((v - d) * 60); return (float(d), float(m), round(((v - d) * 60 - m) * 60, 4))
    gps.update({1: "N", 2: dms(lat), 3: "E", 4: dms(lon), 17: float(heading), 16: "T"})
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


class OriginalExif(unittest.TestCase):
    """gyazo get may return no EXIF for a photo just uploaded (and the upload time as its time), while the original
    image keeps it all: the original's EXIF is what counts."""

    def test_the_originals_exif_is_read(self):
        e = gz.exif_of(jpeg_with_exif(35.681236, 139.767125, 350.0))
        self.assertAlmostEqual(e["lat"], 35.681236, places=5)
        self.assertAlmostEqual(e["lon"], 139.767125, places=5)
        self.assertEqual((e["heading"], e["focal_35mm"], e["model"]), (350.0, 16.0, "Pixel 7"))
        self.assertEqual(e["taken"], "2026-11-27T14:52:15")

    def test_the_originals_exif_wins_over_what_the_api_returned(self):
        item = dict(ITEM, metadata={"desc": "#publish_as_cc0", "exif_normalized":
                                    {"latitude": 35.0, "longitude": 139.0, "time": "2026-11-27T05:59:00Z"}})
        row = gz.with_exif(gz.record(item, creator="x"), gz.exif_of(jpeg_with_exif(35.681236, 139.767125, 25.0,
                                                                                taken="2026:11:27 18:30:00")))
        self.assertAlmostEqual(row["coordinates"][1], 35.681236, places=5)
        self.assertEqual((row["heading"], row["date"], row["time_of_day"]), (25.0, "2026-11-27", "dusk"))

    def test_an_original_without_exif_leaves_the_row_as_it_was(self):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (4, 4)).save(buf, "JPEG")
        row = gz.record(ITEM, creator="x")
        self.assertEqual(gz.with_exif(dict(row), gz.exif_of(buf.getvalue())), row)


class Reread(unittest.TestCase):
    def test_rows_collected_before_take_the_exif_of_their_stored_originals(self):
        import os
        from unittest import mock
        root = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"GEO_VIDEO_CACHE": root}):
            row = gz.record(ITEM, creator="x")
            row["photo"] = photo_store.put(row, jpeg_with_exif(35.681236, 139.767125, 76.0))
            path = Path(root) / "gyazo.json"
            gz.write(path, [row])
            self.assertEqual(gz.reread(path), {"rows": 1, "changed": 1})
            again = gz.read(path)[0]
        self.assertEqual(again["heading"], 76.0)
        self.assertAlmostEqual(again["coordinates"][1], 35.681236, places=5)


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
