"""photo_store: photos kept once per machine, by where they come from, shared by every project."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from support import import_pipeline

photo_store = import_pipeline("photos.photo_store")


def jpeg(size=(64, 48), colour=(120, 80, 40)):
    buf = io.BytesIO()
    img = Image.new("RGB", size, colour)
    img.paste((250, 250, 250), (0, 0, size[0] // 2, size[1] // 2))
    img.save(buf, "JPEG", quality=95)
    return buf.getvalue()


COMMONS = {"source": "wikimedia_commons", "title": "File:Shibuya crossing (123).jpg",
           "landing_url": "https://commons.wikimedia.org/wiki/File:Shibuya_crossing_(123).jpg",
           "license": "CC0", "creator": "someone", "coordinates": [139.7, 35.66],
           "local_path": "assets/photos/x/001_a.jpg", "status": "downloaded"}


class Keys(unittest.TestCase):
    def test_commons_is_known_by_its_file_name_however_it_was_found(self):
        self.assertEqual(photo_store.photo_ref(COMMONS), "commons:Shibuya_crossing_(123).jpg")
        old = {"title": "File:Shibuya crossing (123).jpg"}                  # older manifests left source empty
        self.assertEqual(photo_store.photo_ref(old), "commons:Shibuya_crossing_(123).jpg")
        via_openverse = {"source": "openverse/wikimedia", "title": "Shibuya crossing (123)",
                         "landing_url": "https://commons.wikimedia.org/w/index.php?curid=4",
                         "original_url": "https://upload.wikimedia.org/wikipedia/commons/c/cf/Shibuya_crossing_%28123%29.jpg"}
        self.assertEqual(photo_store.photo_ref(via_openverse), "commons:Shibuya_crossing_(123).jpg")

    def test_flickr_rawpixel_and_wordpress_by_their_photo_ids(self):
        self.assertEqual(photo_store.photo_ref({"source": "openverse/flickr",
                         "landing_url": "https://www.flickr.com/photos/32740887@N04/4461558752"}), "flickr:4461558752")
        self.assertEqual(photo_store.photo_ref({"source": "openverse/rawpixel",
                         "landing_url": "https://www.rawpixel.com/image/5917595/image-public-domain-free-city"}), "rawpixel:5917595")
        self.assertEqual(photo_store.photo_ref({"source": "openverse/wordpress",
                         "landing_url": "https://wordpress.org/photos/photo/631640d951/"}), "wordpress:631640d951")

    def test_a_row_that_names_no_photo_is_refused_loudly(self):
        with self.assertRaises(ValueError):
            photo_store.photo_ref({"source": "somewhere", "title": "x"})


class Store(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        env = mock.patch.dict(os.environ, {"GEO_VIDEO_CACHE": self.root})
        env.start()
        self.addCleanup(env.stop)
        guard = mock.patch.object(photo_store, "blocked", return_value=None)
        self.guard = guard.start()
        self.addCleanup(guard.stop)

    def test_a_photo_is_kept_under_photos_source_with_its_sources_beside_it(self):
        ref = photo_store.put(COMMONS, jpeg())
        path = photo_store.path(ref)
        self.assertTrue(str(path).startswith(str(Path(self.root) / "photos" / "commons")))
        self.assertEqual(path.suffix, ".jpg")
        meta = json.loads((path.parent / "meta.json").read_text())
        self.assertEqual((meta["ref"], meta["license"], meta["creator"]), (ref, "CC0", "someone"))
        self.assertEqual((meta["width"], meta["height"]), (64, 48))
        self.assertIn("sha1", meta)
        self.assertNotIn("local_path", meta)          # where one project kept it says nothing about the photo
        self.assertNotIn("status", meta)

    def test_the_same_photo_from_another_project_is_not_kept_twice_and_the_larger_copy_wins(self):
        small = photo_store.put(COMMONS, jpeg((64, 48)))
        big = photo_store.put(dict(COMMONS, local_path="elsewhere.jpg"), jpeg((128, 96)))
        self.assertEqual(small, big)
        self.assertEqual(json.loads((photo_store.path(big).parent / "meta.json").read_text())["width"], 128)
        photo_store.put(COMMONS, jpeg((32, 24)))
        self.assertEqual(json.loads((photo_store.path(big).parent / "meta.json").read_text())["width"], 128)
        self.assertEqual(len(list((Path(self.root) / "photos" / "commons").iterdir())), 1)

    def test_a_photo_on_the_blocklist_is_never_stored(self):
        self.guard.return_value = "share-alike"
        with self.assertRaises(photo_store.BlockedPhoto):
            photo_store.put(COMMONS, jpeg())
        self.assertFalse((Path(self.root) / "photos").exists())

    def test_an_unknown_ref_has_no_path(self):
        self.assertIsNone(photo_store.path("commons:Nowhere.jpg"))


    def test_importing_a_manifest_stores_its_photos_and_writes_each_ref_in_the_same_layout(self):
        flyover = Path(tempfile.mkdtemp())
        (flyover / "assets/photos/x").mkdir(parents=True)
        (flyover / "assets/photos/x/001_a.jpg").write_bytes(jpeg())
        rows = [COMMONS, dict(COMMONS, title="File:Gone.jpg", local_path="assets/photos/x/002_gone.jpg"),
                {"title": "File:Not downloaded.jpg", "status": "failed"}]
        manifest = flyover / "m.json"
        manifest.write_text(json.dumps({"summary": {}, "photos": rows}, ensure_ascii=False, indent=1) + "\n")
        counts = photo_store.import_manifest(manifest, flyover)
        self.assertEqual((counts["stored"], counts["missing"]), (1, 1))
        doc = json.loads(manifest.read_text())
        self.assertEqual(doc["photos"][0]["photo"], "commons:Shibuya_crossing_(123).jpg")
        self.assertNotIn("photo", doc["photos"][1])
        self.assertEqual(manifest.read_text(), json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
        self.assertIsNotNone(photo_store.path(doc["photos"][0]["photo"]))


    def test_a_manifest_row_finds_its_photo_in_the_store_or_where_the_project_kept_it(self):
        ref = photo_store.put(COMMONS, jpeg())
        self.assertEqual(photo_store.photo_file({"photo": ref, "local_path": "x.jpg"}, "/project"), photo_store.path(ref))
        self.assertEqual(photo_store.photo_file({"local_path": "assets/x.jpg"}, "/project"), Path("/project/assets/x.jpg"))


    def test_a_file_is_known_by_its_ref_inside_the_store_and_by_its_bytes_outside_it(self):
        data = jpeg()
        ref = photo_store.put(COMMONS, data)
        self.assertEqual(photo_store.ref_of_file(photo_store.path(ref)), ref)
        copy = Path(tempfile.mkdtemp()) / "001_copy.jpg"                  # a project's or an SfM run's copy
        copy.write_bytes(data)
        self.assertEqual(photo_store.ref_of_file(copy), ref)
        other = copy.with_name("other.jpg")
        other.write_bytes(jpeg(colour=(1, 2, 3)))
        self.assertIsNone(photo_store.ref_of_file(other))

    def test_a_camera_reads_its_photo_from_the_store_when_it_names_one(self):
        ref = photo_store.put(COMMONS, jpeg())
        self.assertEqual(photo_store.camera_photo({"ref": ref, "photo": "/gone/elsewhere.jpg"}), photo_store.path(ref))
        self.assertEqual(photo_store.camera_photo({"photo": "/somewhere/a.jpg"}), Path("/somewhere/a.jpg"))

    def test_refs_are_written_into_a_cams_file_for_the_photos_the_store_has(self):
        data = jpeg()
        ref = photo_store.put(COMMONS, data)
        d = Path(tempfile.mkdtemp())
        (d / "a.jpg").write_bytes(data)
        (d / "b.jpg").write_bytes(jpeg(colour=(9, 9, 9)))
        cams = d / "cams.json"
        cams.write_text(json.dumps({"a": {"photo": str(d / "a.jpg")}, "b": {"photo": str(d / "b.jpg")}}))
        self.assertEqual(photo_store.add_refs(cams), {"named": 1, "not in the store": 1})
        out = json.loads(cams.read_text())
        self.assertEqual(out["a"]["ref"], ref)
        self.assertNotIn("ref", out["b"])
        self.assertEqual(out["a"]["photo"], str(d / "a.jpg"))           # the old path stays, for older readers


    def test_every_copy_the_store_has_seen_still_leads_to_the_photo_kept(self):
        small, big = jpeg((64, 48)), jpeg((128, 96))
        ref = photo_store.put(COMMONS, small)
        photo_store.put(COMMONS, big)                       # the larger copy replaces the smaller one
        d = Path(tempfile.mkdtemp())
        (d / "small.jpg").write_bytes(small)
        self.assertEqual(photo_store.ref_of_file(d / "small.jpg"), ref)
        tiny = jpeg((32, 24))
        photo_store.put(COMMONS, tiny)                      # a smaller one seen later is not kept, but known
        (d / "tiny.jpg").write_bytes(tiny)
        self.assertEqual(photo_store.ref_of_file(d / "tiny.jpg"), ref)


    def test_a_camera_keeps_the_copy_it_was_calibrated_on_when_the_store_kept_a_larger_one(self):
        small, big = jpeg((64, 48)), jpeg((128, 96))
        ref = photo_store.put(COMMONS, big)                        # the store keeps the larger copy
        d = Path(tempfile.mkdtemp())
        (d / "a.jpg").write_bytes(small)
        cam = {"ref": ref, "photo": str(d / "a.jpg"), "width": 64, "height": 48}
        self.assertEqual(photo_store.camera_photo(cam), d / "a.jpg")
        self.assertEqual(photo_store.camera_photo(dict(cam, width=128)), photo_store.path(ref))


if __name__ == "__main__":
    unittest.main()
