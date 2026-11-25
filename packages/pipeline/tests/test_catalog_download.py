import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from photos import catalog_download as cd


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
    def test_files_and_a_manifest_with_their_sources(self):
        out = Path(tempfile.mkdtemp())
        flyover = out
        photos = out / "assets/photos/test_set"
        bodies = {"https://x/near.jpg": _jpeg((200, 0, 0)), "https://x/near2.jpg": _jpeg((0, 0, 200))}
        manifest = cd.download(ROWS[::2], photos, out / "m.json", flyover, fetch=lambda url: bodies[url],
                               sleep=lambda s: None)
        self.assertEqual(len(manifest["photos"]), 2)
        first = manifest["photos"][0]
        self.assertTrue((flyover / first["local_path"]).is_file())
        self.assertEqual(first["license"], "CC0")
        self.assertTrue(first["local_path"].startswith("assets/photos/test_set/001_"))
        self.assertEqual(json.loads((out / "m.json").read_text())["photos"][1]["creator"], "C")

    def test_a_picture_already_on_disk_is_not_kept_twice(self):
        out = Path(tempfile.mkdtemp())
        photos = out / "assets/photos/test_set"
        same = _jpeg((200, 0, 0))
        known = {cd.picture_hash(same)}
        manifest = cd.download(ROWS[:1], photos, out / "m.json", out, fetch=lambda url: same,
                               sleep=lambda s: None, known=known)
        self.assertEqual(manifest["photos"][0]["status"], "same picture already on disk")
        self.assertNotIn("local_path", manifest["photos"][0])

    def test_a_file_already_downloaded_is_not_fetched_again(self):
        out = Path(tempfile.mkdtemp())
        photos = out / "assets/photos/test_set"
        calls = []

        def fetch(url):
            calls.append(url)
            return _jpeg((200, 0, 0))

        cd.download(ROWS[:1], photos, out / "m.json", out, fetch=fetch, sleep=lambda s: None)
        m = cd.download(ROWS[:1], photos, out / "m.json", out, fetch=fetch, sleep=lambda s: None)
        self.assertEqual(len(calls), 1)
        self.assertEqual(m["photos"][0]["status"], "downloaded")

    def test_a_failed_download_is_recorded_not_hidden(self):
        out = Path(tempfile.mkdtemp())

        def fetch(url):
            raise OSError("boom")

        manifest = cd.download(ROWS[:1], out / "p", out / "m.json", out, fetch=fetch, sleep=lambda s: None)
        self.assertTrue(manifest["photos"][0]["status"].startswith("failed"))


if __name__ == "__main__":
    unittest.main()
