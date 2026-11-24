import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

from support import import_pipeline

storyboard = import_pipeline('storyboard')
video_inspect = import_pipeline('video_inspect')


def _solid_sig(val: int, size: int = 1000) -> bytes:
    return bytes([val]) * size


class VideoInspectTests(unittest.TestCase):
    def test_parse_and_format_time(self):
        self.assertAlmostEqual(storyboard.parse_time(12.5), 12.5)
        self.assertAlmostEqual(storyboard.parse_time('01:23.5'), 83.5)
        self.assertAlmostEqual(storyboard.parse_time('1:02:03'), 3723.0)
        self.assertEqual(storyboard.format_time(83.5, decimals=1), '01:23.5')
        self.assertEqual(storyboard.format_time(3723.25, decimals=2, with_hours=True), '1:02:03.25')
        with self.assertRaises(ValueError):
            storyboard.parse_time('-5')

    def test_parse_crop_valid_and_invalid(self):
        self.assertEqual(storyboard.parse_crop('0.5,0,0.5,0.5'), (0.5, 0.0, 0.5, 0.5))
        self.assertIsNone(storyboard.parse_crop(None))
        for bad in ('0.5,0.5,0.5', '1.2,0,0.2,0.2', '0.8,0,0.5,0.5', '0,0,0,0.5'):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    storyboard.parse_crop(bad)

    def test_select_keyframes_captures_flash_episode_and_hard_cut(self):
        sigs = [_solid_sig(10)] * 10
        sigs[4] = _solid_sig(200)
        sigs[8] = _solid_sig(240)
        sigs[9] = _solid_sig(240)

        selected = storyboard.select_keyframes(sigs, budget=6)
        indices = [s.index for s in selected]
        self.assertIn(0, indices)
        self.assertIn(4, indices)
        self.assertIn(8, indices)
        cut_frame = next(s for s in selected if s.index == 8)
        self.assertTrue(cut_frame.cut)
        self.assertEqual(cut_frame.same_until, 9)

    def test_select_keyframes_respects_budget_on_gradual_changes(self):
        sigs = [_solid_sig((i * 15) % 250) for i in range(40)]
        selected = storyboard.select_keyframes(sigs, budget=8)
        self.assertLessEqual(len(selected), 8)
        self.assertGreaterEqual(len(selected), 2)
        self.assertEqual(selected[0].index, 0)

    def test_choose_grid_and_compose_storyboard_keeps_caption_above_tile(self):
        layout = storyboard.choose_grid(16 / 9, count=4, per_sheet=16, max_edge=1556)
        self.assertGreater(layout.tile_w, 0)
        self.assertGreater(layout.tile_h, 0)
        self.assertEqual(layout.label_h, storyboard.LABEL_HEIGHT)

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / 'board.jpg'
            tiles = [(Image.new('RGB', (320, 180), (40, 120, 200)), f'#{i + 1} 00:0{i}.0') for i in range(4)]
            storyboard.compose_storyboard(tiles, layout, out, overwrite=True)
            self.assertTrue(out.exists())
            with Image.open(out) as rendered:
                self.assertEqual(rendered.size, (layout.width, layout.height))
                caption_px = rendered.getpixel((layout.gutter + 2, layout.gutter + 2))
                tile_px = rendered.getpixel((layout.gutter + layout.tile_w // 2, layout.gutter + layout.label_h + layout.tile_h // 2))
                self.assertLess(max(caption_px), 30)
                self.assertGreater(tile_px[2], 150)

    def test_format_timeline_describes_cut_and_unchanged_spans(self):
        selected = [
            storyboard.SelectedFrame(index=0, change=0.0, cut=False, same_until=2),
            storyboard.SelectedFrame(index=3, change=0.85, cut=True, same_until=3),
        ]
        times = [0.0, 1.0, 2.0, 3.0]
        text = storyboard.format_timeline(selected, times)
        self.assertIn('00:00.0  SEEN #1 (storyboard 1)  start; unchanged until 00:02.0', text)
        self.assertIn('00:03.0  SEEN #2 (storyboard 1)  cut (new scene)', text)

    def test_zoom_and_frame_cli_with_mocked_ffmpeg(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'clip.mp4'
            src.write_bytes(b'fake')
            zoom_out = root / 'zoom.jpg'
            frame_out = root / 'frame.png'

            info = {'width': 1920, 'height': 1080, 'duration': 20.0, 'fps': 30.0}
            dummy_img = Image.new('RGB', (160, 90), (10, 80, 160))

            with patch.object(video_inspect, '_probe_video', return_value=info), \
                 patch.object(video_inspect, '_extract_frame_image', return_value=dummy_img):
                rc_zoom = video_inspect.main([
                    'zoom', str(src), '--start', '2.0', '--end', '4.0',
                    '--fps', '2', '--out', str(zoom_out), '--json',
                ])
                rc_frame = video_inspect.main([
                    'frame', str(src), '--t', '3.0', '--crop', '0.5,0,0.5,0.5',
                    '--out', str(frame_out), '--json',
                ])
            self.assertEqual(rc_zoom, 0)
            self.assertEqual(rc_frame, 0)
            self.assertTrue(zoom_out.exists())
            self.assertTrue(frame_out.exists())


if __name__ == '__main__':
    unittest.main()
