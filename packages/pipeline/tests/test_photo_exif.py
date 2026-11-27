"""photo_exif: what a photo's own binary says about where and how it was taken."""
import math
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from PIL.TiffImagePlugin import IFDRational

from support import import_pipeline

pe = import_pipeline("photos.photo_exif")


def photo(f35=None, focal=None, gps=None, method=None, size=(4080, 3072)):
    path = Path(tempfile.mkdtemp()) / "p.jpg"
    img = Image.new("RGB", size)
    exif = img.getexif()
    sub = exif.get_ifd(0x8769)
    if f35 is not None:
        sub[0xA405] = f35
    if focal is not None:
        sub[0x920A] = IFDRational(int(focal * 100), 100)
    exif[0x8769] = sub
    if gps:
        lat, lon = gps
        g = exif.get_ifd(0x8825)
        def dms(v):
            d = int(v); m = int((v - d) * 60); s = (v - d - m / 60) * 3600
            return (IFDRational(d, 1), IFDRational(m, 1), IFDRational(int(s * 10000), 10000))
        g[1], g[2], g[3], g[4] = "N", dms(lat), "E", dms(lon)
        if method:
            g[27] = b"ASCII\0\0\0" + method.encode()
        exif[0x8825] = g
    img.save(path, exif=exif)
    return path


class Camera(unittest.TestCase):
    def test_the_35mm_equivalent_gives_the_focal_length_by_the_diagonal(self):
        c = pe.camera_from_exif(photo(f35=28, focal=4.2, gps=(35.7, 139.77)))
        self.assertAlmostEqual(c["fx"], 28 * math.hypot(4080, 3072) / math.hypot(36, 24), places=1)
        self.assertEqual(c["fx_from"], "FocalLengthIn35mmFilm 28 mm on the diagonal")

    def test_without_a_35mm_equivalent_the_focal_length_is_left_to_be_searched(self):
        c = pe.camera_from_exif(photo(f35=0, focal=4.7, gps=(35.7, 139.77)))
        self.assertIsNone(c["fx"])
        self.assertIn("search", c["fx_from"])

    def test_the_position_and_how_it_was_found_set_how_far_to_search(self):
        c = pe.camera_from_exif(photo(f35=28, gps=(35.707262, 139.772696), method="network"))
        self.assertAlmostEqual(c["lon"], 139.772696, places=5)
        self.assertAlmostEqual(c["lat"], 35.707262, places=5)
        self.assertEqual(c["gps_method"], "network")
        self.assertEqual(c["search_radius_m"], pe.SEARCH_RADIUS["network"])
        self.assertGreaterEqual(pe.SEARCH_RADIUS["network"], 500.0)     # network fixes measured 190 to 360 m off

    def test_a_photo_without_a_position_says_so(self):
        with self.assertRaises(ValueError):
            pe.camera_from_exif(photo(f35=28))


if __name__ == "__main__":
    unittest.main()
