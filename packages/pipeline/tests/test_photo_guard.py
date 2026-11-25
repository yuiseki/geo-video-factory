import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from photos import photo_guard as pg


def _photo(path, seed, size=(640, 480)):
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 255, (12, 16, 3), dtype=np.uint8)          # coarse structure survives resizing
    Image.fromarray(small).resize(size, Image.BICUBIC).save(path, quality=92)
    return path


class Guard(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.blocked = _photo(self.dir / "sa.jpg", 1)
        self.list = self.dir / "blocklist.tsv"
        pg.write_blocklist(self.list, [pg.entry(self.blocked, "CC BY-SA 3.0", "File:Example.jpg", "share-alike")])

    def test_the_same_file_is_refused(self):
        with self.assertRaises(pg.BlockedPhoto):
            pg.check(self.blocked, self.list)

    def test_a_resized_recompressed_copy_is_refused(self):
        copy = self.dir / "copy.jpg"
        Image.open(self.blocked).resize((320, 240), Image.LANCZOS).save(copy, quality=70)
        with self.assertRaises(pg.BlockedPhoto):
            pg.check(copy, self.list)

    def test_another_photo_passes(self):
        other = _photo(self.dir / "cc0.jpg", 2)
        pg.check(other, self.list)
        self.assertEqual(pg.open_photo(other, self.list).size, (640, 480))

    def test_open_photo_refuses_before_reading(self):
        with self.assertRaises(pg.BlockedPhoto):
            pg.open_photo(self.blocked, self.list)

    def test_drop_blocked_keeps_only_the_others(self):
        other = _photo(self.dir / "cc0.jpg", 2)
        cams = {"a": {"photo": str(self.blocked)}, "b": {"photo": str(other)}}
        self.assertEqual(list(pg.drop_blocked(cams, self.list)), ["b"])

    def test_the_blocklist_is_one_sorted_row_per_photo(self):
        second = _photo(self.dir / "sa2.jpg", 3)
        rows = pg.read_blocklist(self.list) + [pg.entry(second, "CC BY-SA 4.0", "File:B.jpg", "share-alike")]
        pg.write_blocklist(self.list, rows + rows)                        # duplicates collapse
        lines = self.list.read_text().splitlines()
        self.assertEqual(lines[0].split("\t"), list(pg.COLUMNS))
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[1:], sorted(lines[1:]))

    def test_the_repository_blocklist_loads(self):
        rows = pg.read_blocklist()
        self.assertTrue(all(len(r["sha1"]) == 40 and len(r["dhash"]) == 16 for r in rows))


if __name__ == "__main__":
    unittest.main()
