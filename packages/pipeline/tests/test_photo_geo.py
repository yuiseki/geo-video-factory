import unittest
from unittest.mock import patch

from support import import_pipeline

photo_geo = import_pipeline('geo.photo_geo')


class FakeExif:
    def __init__(self, gps):
        self.gps = gps

    def get_ifd(self, key):
        self.key = key
        return self.gps


class FakeImage:
    def __init__(self, gps):
        self.gps = gps

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def getexif(self):
        return FakeExif(self.gps)


class PhotoGeoTests(unittest.TestCase):
    def test_exif_coordinates_converts_dms_and_hemispheres(self):
        gps = {1: 'S', 2: (34, 30, 0), 3: 'W', 4: (135, 15, 0)}
        with patch.object(photo_geo.Image, 'open', return_value=FakeImage(gps)):
            self.assertEqual(photo_geo.exif_coordinates('photo.jpg'), [-135.25, -34.5])

    def test_exif_coordinates_rejects_missing_and_invalid_positions(self):
        with patch.object(photo_geo.Image, 'open', return_value=FakeImage({})):
            with self.assertRaisesRegex(ValueError, 'No EXIF GPS'):
                photo_geo.exif_coordinates('missing.jpg')
        gps = {1: 'N', 2: (91, 0, 0), 3: 'E', 4: (135, 0, 0)}
        with patch.object(photo_geo.Image, 'open', return_value=FakeImage(gps)):
            with self.assertRaisesRegex(ValueError, 'Invalid EXIF GPS'):
                photo_geo.exif_coordinates('invalid.jpg')

    def test_linked_photo_copies_inputs_and_supports_bridge(self):
        position = [135.5, 34.6]
        subject = {'at': [135.6, 34.7], 'name': '看板'}
        bridge = {'at': [135.4, 34.5], 'name': '橋'}
        overlay = photo_geo.linked_photo('a.jpg', '写真', position, credit='yuiseki', subject=subject, bridge=bridge)
        position[0] = subject['at'][0] = bridge['at'][0] = 0
        self.assertEqual(overlay['at'], [135.5, 34.6])
        self.assertEqual(overlay['cameraAt'], [135.6, 34.7])
        self.assertEqual(overlay['bridgeAt'], [135.4, 34.5])


if __name__ == '__main__':
    unittest.main()
