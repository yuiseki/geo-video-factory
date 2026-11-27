"""build_atlas.paint_photo: a camera's photo is painted only when it is CC0 or public domain (photos/photo_use.py)."""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from photos import photo_store  # noqa: E402
from world_model import build_atlas as ba  # noqa: E402


def put(licence, title, **extra):
    buf = io.BytesIO()
    Image.new("RGB", (32, 24), (10, 20, 30)).save(buf, format="JPEG")
    row = dict({"source": "wikimedia_commons", "title": title, "license": licence, "license_url": ""}, **extra)
    return photo_store.put(row, buf.getvalue())


class PaintPhoto(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        env = mock.patch.dict(os.environ, {"GEO_VIDEO_CACHE": self.root})
        env.start()
        self.addCleanup(env.stop)

    def test_a_cc0_camera_is_painted(self):
        ref = put("CC0", "File:Wako.jpg")
        self.assertEqual(ba.paint_photo({"ref": ref, "photo": "gone.jpg"}), photo_store.path(ref))

    def test_a_registration_camera_stops_the_atlas(self):
        ref = put("CC BY-SA 4.0", "File:Wako_bysa.jpg", use="registration")
        link = Path(self.root) / "007_Wako_bysa.jpg"         # SfM's staged copy, as sfm_to_world names it
        link.symlink_to(photo_store.path(ref))
        with self.assertRaises(SystemExit):
            ba.paint_photo({"photo": str(link)})


if __name__ == "__main__":
    unittest.main()
