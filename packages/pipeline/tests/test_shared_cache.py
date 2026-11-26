import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import import_pipeline

shared_cache = import_pipeline("shared_cache")


class CacheRoot(unittest.TestCase):
    def test_the_environment_names_the_root(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"GEO_VIDEO_CACHE": d}):
            self.assertEqual(shared_cache.cache_root(), Path(d))
            self.assertEqual(shared_cache.plateau_raw_dir(), Path(d) / "plateau-raw")
            self.assertEqual(shared_cache.gsi_dir(), Path(d) / "gsi")
            self.assertEqual(shared_cache.plateau_pp_dir("0.1.0"), Path(d) / "plateau-pp" / "v0.1.0")

    def test_without_it_the_root_is_tmp_cache_of_the_repository(self):
        env = {k: v for k, v in os.environ.items() if k != "GEO_VIDEO_CACHE"}
        with mock.patch.dict(os.environ, env, clear=True):
            root = shared_cache.cache_root()
        self.assertEqual(root.parts[-2:], ("tmp", ".cache"))
        self.assertTrue((root.parent.parent / "packages" / "pipeline" / "shared_cache.py").exists())


class CachedFetch(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        return f"bytes of {url}".encode()

    def test_a_url_is_fetched_once_and_then_read_from_disk(self):
        cached = shared_cache.cached_fetch(self.fetch, self.dir)
        url = "https://example.test/tiles/a/b/53394611_bldg.b3dm"
        self.assertEqual(cached(url), b"bytes of " + url.encode())
        self.assertEqual(cached(url), b"bytes of " + url.encode())
        self.assertEqual(self.calls, [url])

    def test_another_fetcher_on_the_same_directory_reuses_the_bytes(self):
        url = "https://example.test/tileset.json"
        shared_cache.cached_fetch(self.fetch, self.dir)(url)
        again = shared_cache.cached_fetch(lambda u: self.fail("fetched again"), self.dir)
        self.assertEqual(again(url), b"bytes of " + url.encode())

    def test_files_are_named_by_the_url_hash_and_keep_the_extension(self):
        shared_cache.cached_fetch(self.fetch, self.dir)("https://example.test/x/1.b3dm?v=2")
        names = [p.name for p in self.dir.rglob("*") if p.is_file()]
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].endswith(".b3dm"), names)
        self.assertEqual(len(names[0].split(".")[0]), 20)

    def test_a_failed_fetch_leaves_nothing_behind(self):
        def broken(url):
            raise OSError("network down")
        with self.assertRaises(OSError):
            shared_cache.cached_fetch(broken, self.dir)("https://example.test/a.glb")
        self.assertEqual([p for p in self.dir.rglob("*") if p.is_file()], [])


if __name__ == "__main__":
    unittest.main()
