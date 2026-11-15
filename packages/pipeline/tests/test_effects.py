import unittest

from support import import_pipeline

shot_effects = import_pipeline('shot_effects')


class ShotEffectsTests(unittest.TestCase):
    def setUp(self):
        self.camera = {'center': [135.5, 34.6], 'zoom': 14.0, 'bearing': 10}

    def test_every_camera_effect_has_expected_invariants(self):
        hold = shot_effects.camera_views(self.camera, 'hold')
        self.assertEqual([hold[0]['pitch'], hold[1]['pitch']], [28, 28])
        track = shot_effects.camera_views(self.camera, 'track_river', river_dx=0.2)
        self.assertEqual(track[0]['center'], [135.3, 34.6])
        self.assertEqual(track[1]['center'], [135.7, 34.6])
        reveal = shot_effects.camera_views(self.camera, 'reveal_context')
        self.assertEqual(reveal[1]['zoom'], 13.4)
        approach = shot_effects.camera_views(self.camera, 'approach', zoom_step=0.25)
        self.assertEqual(approach[1]['zoom'], 14.25)
        quiet = shot_effects.camera_views(self.camera, 'quiet')
        self.assertEqual(quiet[0]['bearing'], quiet[1]['bearing'])

    def test_unknown_effect_is_rejected_without_mutation(self):
        original = dict(self.camera, center=list(self.camera['center']))
        with self.assertRaisesRegex(ValueError, 'unknown camera effect'):
            shot_effects.camera_views(self.camera, 'warp')
        self.assertEqual(self.camera, original)

    def test_photo_motion_is_deterministic_for_positive_and_negative_indices(self):
        self.assertEqual([shot_effects.photo_motion(i) for i in range(4)], ['in', 'out', 'up', 'down'])
        self.assertEqual(shot_effects.photo_motion(4), 'in')
        self.assertEqual(shot_effects.photo_motion(-1), 'down')

    def test_landmark_copies_coordinate(self):
        coordinate = [135.5, 34.6]
        label = shot_effects.landmark('地点', coordinate)
        coordinate[0] = 0
        self.assertEqual(label['at'], [135.5, 34.6])

    def test_geographic_transition_uses_custom_midpoint_and_holds_it(self):
        keys = shot_effects.geographic_transition(
            [135, 34], [140, 36], midpoint=[137, 35], hold=(0.2, 0.7), pitch=8,
        )
        self.assertEqual([k['t'] for k in keys], [0, 0.2, 0.7, 1])
        self.assertEqual(keys[1], keys[2] | {'t': 0.2})
        self.assertEqual(keys[1]['center'], [137, 35])


if __name__ == '__main__':
    unittest.main()
