import sys
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from video import shot_effects
from geo import photo_geo


class PipelineTests(unittest.TestCase):
    def test_camera_views_does_not_mutate_input(self):
        cam = {'center': [135.5, 34.6], 'zoom': 14.0, 'bearing': 10}
        start, end = shot_effects.camera_views(cam, 'reveal_context')
        self.assertEqual(cam['zoom'], 14.0)
        self.assertEqual(start['pitch'], 45)
        self.assertEqual(end['pitch'], 25)
        self.assertLess(end['zoom'], start['zoom'])

    def test_geographic_transition_keys(self):
        keys = shot_effects.geographic_transition([135.5, 34.6], [139.7, 35.6])
        self.assertEqual(len(keys), 4)
        self.assertEqual(keys[0]['t'], 0)
        self.assertEqual(keys[-1]['t'], 1)

    def test_linked_photo_overlay_shape(self):
        ov = photo_geo.linked_photo(
            'assets/a.jpg',
            '道頓堀',
            [135.501, 34.668],
            credit='CC BY 4.0',
            subject={'at': [135.502, 34.669], 'name': '戎橋'},
        )
        self.assertEqual(ov['type'], 'photo_marker')
        self.assertEqual(ov['at'], [135.501, 34.668])
        self.assertEqual(ov['cameraLabel'], '戎橋')


if __name__ == '__main__':
    unittest.main()
