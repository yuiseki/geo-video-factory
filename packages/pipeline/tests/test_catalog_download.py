import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from photos import catalog_download as cd
from photos import photo_store


def _jpeg(colour):
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), colour).save(buf, "JPEG")
    return buf.getvalue()


ROWS = [
    {"title": "File:Near crossing.jpg", "coordinates": [139.7006, 35.6593], "license": "CC0", "creator": "A",
     "download_url": "https://x/near.jpg", "landing_url": "https://c/near", "source": "wikimedia_commons"},
    {"title": "File:Far away.jpg", "coordinates": [139.80, 35.70], "license": "CC0", "creator": "B",
     "download_url": "https://x/far.jpg", "landing_url": "https://c/far", "source": "wikimedia_commons"},
    {"title": "File:Also near (2).JPG", "coordinates": [139.7010, 35.6590], "license": "Public domain", "creator": "C",
     "download_url": "https://x/near2.jpg", "landing_url": "https://c/near2", "source": "wikimedia_commons"},
]


class Select(unittest.TestCase):
    def test_rows_within_the_radius(self):
        near = cd.within(ROWS, (139.700611, 35.65932), 600)
        self.assertEqual([r["title"] for r in near], ["File:Near crossing.jpg", "File:Also near (2).JPG"])


class Thumbnails(unittest.TestCase):
    def test_a_commons_thumbnail_is_asked_for_at_a_standard_width(self):
        url = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/X.jpg/2560px-X.jpg"
        self.assertEqual(cd.standard_thumb(url), "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/X.jpg/1920px-X.jpg")

    def test_other_urls_are_left_alone(self):
        self.assertEqual(cd.standard_thumb("https://live.staticflickr.com/1/2_o.jpg"), "https://live.staticflickr.com/1/2_o.jpg")


class Download(unittest.TestCase):
    """Photos go to the shared store (photos.photo_store); the manifest names each by its ref."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        env = mock.patch.dict(os.environ, {"GEO_VIDEO_CACHE": self.root})
        env.start()
        self.addCleanup(env.stop)
        guard = mock.patch("photos.photo_store.blocked", return_value=None)
        self.guard = guard.start()
        self.addCleanup(guard.stop)
        self.out = Path(tempfile.mkdtemp())

    def test_photos_go_to_the_store_and_the_manifest_keeps_their_sources_and_refs(self):
        bodies = {"https://x/near.jpg": _jpeg((200, 0, 0)), "https://x/near2.jpg": _jpeg((0, 0, 200))}
        manifest = cd.download(ROWS[::2], self.out / "m.json", fetch=lambda url: bodies[url], sleep=lambda s: None)
        first = manifest["photos"][0]
        self.assertEqual((first["status"], first["photo"]), ("downloaded", "commons:Near_crossing.jpg"))
        self.assertNotIn("local_path", first)
        self.assertTrue(photo_store.path(first["photo"]).is_file())
        self.assertEqual(first["license"], "CC0")
        self.assertEqual(json.loads((self.out / "m.json").read_text())["photos"][1]["creator"], "C")

    def test_a_picture_already_on_disk_is_not_kept_twice(self):
        same = _jpeg((200, 0, 0))
        manifest = cd.download(ROWS[:1], self.out / "m.json", fetch=lambda url: same, sleep=lambda s: None,
                               known={cd.picture_hash(same)})
        self.assertEqual(manifest["photos"][0]["status"], "same picture already on disk")
        self.assertNotIn("photo", manifest["photos"][0])

    def test_a_photo_already_in_the_store_is_not_fetched_again_by_any_project(self):
        calls = []

        def fetch(url):
            calls.append(url)
            return _jpeg((200, 0, 0))

        cd.download(ROWS[:1], self.out / "m.json", fetch=fetch, sleep=lambda s: None)
        m = cd.download(ROWS[:1], Path(tempfile.mkdtemp()) / "other.json", fetch=fetch, sleep=lambda s: None)
        self.assertEqual(len(calls), 1)
        self.assertEqual((m["photos"][0]["status"], m["photos"][0]["photo"]), ("in the store", "commons:Near_crossing.jpg"))

    def test_a_photo_on_the_blocklist_is_recorded_as_refused_and_not_stored(self):
        self.guard.return_value = "CC BY-SA, x: share-alike"
        m = cd.download(ROWS[:1], self.out / "m.json", fetch=lambda url: _jpeg((1, 2, 3)), sleep=lambda s: None)
        self.assertTrue(m["photos"][0]["status"].startswith("refused"))
        self.assertIsNone(photo_store.path("commons:Near_crossing.jpg"))

    def test_a_failed_download_is_recorded_not_hidden(self):
        def fetch(url):
            raise OSError("boom")

        manifest = cd.download(ROWS[:1], self.out / "m.json", fetch=fetch, sleep=lambda s: None)
        self.assertTrue(manifest["photos"][0]["status"].startswith("failed"))


if __name__ == "__main__":
    unittest.main()
