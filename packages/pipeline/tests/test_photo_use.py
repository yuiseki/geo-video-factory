"""photo_use: CC BY / CC BY-SA photos only help to place the others (registration); only CC0 and public domain
are painted. See .agents/skills/geo-video-materials/references/registration-only-photos.md."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from support import import_pipeline

photo_use = import_pipeline("photos.photo_use")
photo_store = import_pipeline("photos.photo_store")
rules = import_pipeline("photos.photo_catalog_rules")


def jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (90, 60, 30)).save(buf, format="JPEG")
    return buf.getvalue()


def row(licence, title="File:Ginza crossing.jpg", **extra):
    return dict({"source": "wikimedia_commons", "title": title, "license": licence, "license_url": "", "creator": "x"},
                **extra)


class Licences(unittest.TestCase):
    def test_registration_only_is_attribution_or_share_alike_and_nothing_else(self):
        for good in ("CC BY 4.0", "CC BY-SA 4.0", "CC BY-SA 2.0", "CC BY 2.0"):
            self.assertTrue(rules.is_registration_only(good), good)
        for bad in ("CC0", "Public domain", "CC BY-NC 2.0", "CC BY-ND 4.0", "CC BY-NC-SA 4.0", "GFDL", ""):
            self.assertFalse(rules.is_registration_only(bad), bad)


class Store(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        env = mock.patch.dict(os.environ, {"GEO_VIDEO_CACHE": self.root})
        env.start()
        self.addCleanup(env.stop)

    def put(self, r):
        return photo_store.put(r, jpeg())

    def test_a_registration_photo_goes_to_its_own_place_under_its_own_ref(self):
        ref = self.put(row("CC BY-SA 4.0", use="registration"))
        self.assertEqual(ref, "registration-commons:Ginza_crossing.jpg")
        self.assertTrue(photo_use.is_registration_ref(ref))
        self.assertIsNone(photo_store.path("commons:Ginza_crossing.jpg"))      # not found as a photo to paint
        self.assertIn("registration-commons", str(photo_store.path(ref)))

    def test_only_attribution_and_share_alike_are_taken_for_registration(self):
        for licence in ("CC0", "CC BY-NC 2.0"):
            with self.assertRaises(photo_store.BlockedPhoto):
                self.put(row(licence, use="registration"))

    def test_painting_takes_cc0_and_public_domain(self):
        for licence in ("CC0", "Public domain"):
            photo_use.check_paint(photo_store.path(self.put(row(licence, title=f"File:{licence}.jpg"))))

    def test_painting_refuses_attribution_and_registration_photos(self):
        by = photo_store.path(self.put(row("CC BY 4.0", title="File:By.jpg")))
        with self.assertRaises(photo_use.NotPaintable):
            photo_use.check_paint(by)
        reg = photo_store.path(self.put(row("CC BY 4.0", title="File:Reg.jpg", use="registration")))
        with self.assertRaises(photo_use.NotPaintable):
            photo_use.check_paint(reg)

    def test_a_link_to_a_stored_photo_is_judged_by_the_photo_it_points_at(self):
        reg = photo_store.path(self.put(row("CC BY-SA 4.0", use="registration")))
        link = Path(self.root) / "000_link.jpg"
        link.symlink_to(reg)
        with self.assertRaises(photo_use.NotPaintable):
            photo_use.check_paint(link)

    def test_a_projects_own_copy_outside_the_store_is_left_to_the_projects_records(self):
        own = Path(self.root) / "own.jpg"
        own.write_bytes(jpeg())
        photo_use.check_paint(own)


if __name__ == "__main__":
    unittest.main()
