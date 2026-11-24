import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch

from support import import_pipeline

chapter_pipeline = import_pipeline('video.chapter_pipeline')


class ChapterPipelineTests(unittest.TestCase):
    def test_duration_reads_ffprobe_number(self):
        with patch.object(chapter_pipeline, 'run', return_value=SimpleNamespace(stdout='12.345\n')) as run:
            self.assertEqual(chapter_pipeline.duration(Path('chapter.mp4')), 12.345)
        self.assertEqual(run.call_args.args[0][0], 'ffprobe')

    def test_card_draws_title_and_invokes_ffmpeg_with_requested_duration(self):
        class FakeImage:
            def save(self, path):
                Path(path).write_bytes(b'image')

        class FakeDraw:
            def __init__(self):
                self.texts = []

            def text(self, position, text, **kwargs):
                self.texts.append(text)

            def line(self, *args, **kwargs):
                pass

        draw = FakeDraw()
        with TemporaryDirectory() as temp:
            image, video = Path(temp) / 'card.png', Path(temp) / 'card.mp4'
            with patch.object(chapter_pipeline.Image, 'new', return_value=FakeImage()), \
                 patch.object(chapter_pipeline.ImageDraw, 'Draw', return_value=draw), \
                 patch.object(chapter_pipeline.ImageFont, 'truetype', return_value=object()), \
                 patch.object(chapter_pipeline, 'find_font', return_value='font.ttc'), \
                 patch.object(chapter_pipeline, 'run') as run:
                chapter_pipeline.card('水辺の文化', 2, image, video, '都市史', 24, 2.5)
            self.assertEqual(draw.texts, ['都市史', '第 2 章', '水辺の文化'])
            command = run.call_args.args[0]
            self.assertEqual(command[0], 'ffmpeg')
            self.assertEqual(command[command.index('-t') + 1], '2.5')
            self.assertEqual(command[-1], str(video))

    def test_validate_chapter_ids_accepts_safe_unique_names(self):
        chapter_pipeline.validate_chapter_ids([{'id': 'intro-1'}, {'id': 'chapter_2'}])

    def test_validate_chapter_ids_rejects_empty_duplicate_or_unsafe_names(self):
        for chapters in [[], [{'id': 'same'}, {'id': 'same'}], [{'id': '../escape'}], [{'title': 'missing'}]]:
            with self.subTest(chapters=chapters):
                with self.assertRaises((ValueError, KeyError)):
                    chapter_pipeline.validate_chapter_ids(chapters)

    def test_parse_loudnorm_builds_second_pass_filter(self):
        stderr = 'noise\n{"input_i":"-20", "input_tp":"-2", "input_lra":"4", "input_thresh":"-30", "target_offset":"0.2"}\nend'
        filt = chapter_pipeline.parse_loudnorm(stderr)
        self.assertIn('measured_I=-20', filt)
        self.assertIn('offset=0.2', filt)
        self.assertTrue(filt.endswith('linear=true'))

    def test_parse_loudnorm_rejects_missing_or_incomplete_measurement(self):
        for stderr in ['no json', '{}', '{"input_i":"-20"}']:
            with self.subTest(stderr=stderr):
                with self.assertRaisesRegex(ValueError, 'loudnorm'):
                    chapter_pipeline.parse_loudnorm(stderr)

    def test_build_timeline_places_card_before_following_chapter(self):
        chapters = [{'title': '一章'}, {'title': '二章'}, {'title': '三章'}]
        timeline, total = chapter_pipeline.build_timeline(chapters, [10, 20, 30], [2.5, 3.0])
        self.assertEqual(timeline, [
            {'title': '一章', 'start': 0.0},
            {'title': '二章', 'start': 12.5},
            {'title': '三章', 'start': 35.5},
        ])
        self.assertEqual(total, 65.5)

    def test_build_timeline_validates_lengths_and_nonnegative_durations(self):
        with self.assertRaisesRegex(ValueError, 'duration'):
            chapter_pipeline.build_timeline([{'title': '一章'}], [], [])
        with self.assertRaisesRegex(ValueError, 'duration'):
            chapter_pipeline.build_timeline([{'title': '一章'}], [-1], [])

    def test_render_builds_command_checks_streams_and_returns_video(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            spec = root / 'chapter.json'
            spec.write_text('{}', encoding='utf-8')
            renderer = root / 'render.js'
            renderer.write_text('', encoding='utf-8')
            dest = root / 'jobs' / 'chapter-1'
            dest.parent.mkdir()

            def fake_node(cmd, **kwargs):
                self.assertEqual(cmd[:2], ['node', str(renderer)])
                self.assertIn('--raw-audio', cmd)
                self.assertEqual(kwargs['cwd'], root)
                (dest / 'chapter-1.mp4').write_bytes(b'video')
                return SimpleNamespace(returncode=0)

            probe = SimpleNamespace(stdout=json.dumps({'streams': [{'codec_type': 'video'}, {'codec_type': 'audio'}]}))
            item = (0, spec, dest, None, True, root, renderer)
            with patch.object(chapter_pipeline.subprocess, 'run', side_effect=fake_node), \
                 patch.object(chapter_pipeline, 'run', return_value=probe):
                video = chapter_pipeline.render(item)
            self.assertEqual(video, dest / 'chapter-1.mp4')

    def test_render_rejects_renderer_errors_and_missing_audio(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            spec = root / 'chapter.json'
            spec.write_text('{}', encoding='utf-8')
            renderer = root / 'render.js'
            renderer.write_text('', encoding='utf-8')

            for mode in ('logged-error', 'missing-audio'):
                with self.subTest(mode=mode):
                    dest = root / mode

                    def fake_node(cmd, **kwargs):
                        if mode == 'logged-error':
                            kwargs['stdout'].write('[page] broken\n')
                        (dest / f'{dest.name}.mp4').write_bytes(b'video')
                        return SimpleNamespace(returncode=0)

                    streams = [{'codec_type': 'video'}] if mode == 'missing-audio' else [
                        {'codec_type': 'video'}, {'codec_type': 'audio'},
                    ]
                    with patch.object(chapter_pipeline.subprocess, 'run', side_effect=fake_node), \
                         patch.object(chapter_pipeline, 'run', return_value=SimpleNamespace(stdout=json.dumps({'streams': streams}))):
                        error = RuntimeError if mode == 'logged-error' else ValueError
                        with self.assertRaises(error):
                            chapter_pipeline.render((0, spec, dest, None, False, root, renderer))

    def test_find_font_prefers_explicit_then_existing_candidate(self):
        with TemporaryDirectory() as temp:
            font = Path(temp) / 'custom.ttc'
            font.write_bytes(b'font')
            self.assertEqual(chapter_pipeline.find_font(str(font)), str(font))
            with patch.object(chapter_pipeline, 'FONT_CANDIDATES', (Path(temp) / 'missing.ttc', font)):
                self.assertEqual(chapter_pipeline.find_font(), str(font))
            with patch.object(chapter_pipeline, 'FONT_CANDIDATES', (Path(temp) / 'missing.ttc',)):
                with self.assertRaises(FileNotFoundError):
                    chapter_pipeline.find_font()

    def test_parse_size_and_format_concat_line(self):
        self.assertEqual(chapter_pipeline.parse_size('1280x720'), (1280, 720))
        for bad in ('1280', '0x720', '1920x-1', 'abc'):
            with self.assertRaises(ValueError):
                chapter_pipeline.parse_size(bad)
        line = chapter_pipeline.format_concat_line(Path('C:/work/out/ch-01.mp4'))
        self.assertEqual(line, "file 'C:/work/out/ch-01.mp4'\n")
        self.assertNotIn('\\', line)

    def test_can_reuse_chapter_checks_spec_match_and_rerender_override(self):
        with TemporaryDirectory() as temp:
            prev = Path(temp)
            job = prev / 'jobs' / 'ch-1'
            job.mkdir(parents=True)
            (job / 'ch-1.mp4').write_bytes(b'mp4')
            (job / 'spec.json').write_text('{"shots":[1]}', encoding='utf-8')
            self.assertTrue(chapter_pipeline.can_reuse_chapter(prev, 'ch-1', 0, '{"shots":[1]}', set()))
            self.assertFalse(chapter_pipeline.can_reuse_chapter(prev, 'ch-1', 0, '{"shots":[2]}', set()))
            self.assertFalse(chapter_pipeline.can_reuse_chapter(prev, 'ch-1', 0, '{"shots":[1]}', {'ch-1'}))
            self.assertFalse(chapter_pipeline.can_reuse_chapter(prev, 'ch-1', 0, '{"shots":[1]}', {'0'}))

    def test_render_forwards_no_voice_fps_and_size(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            spec = root / 'chapter.json'
            spec.write_text('{}', encoding='utf-8')
            renderer = root / 'render.js'
            renderer.write_text('', encoding='utf-8')
            dest = root / 'jobs' / 'ch-draft'
            dest.parent.mkdir()

            def fake_node(cmd, **kwargs):
                self.assertIn('--no-voice', cmd)
                self.assertEqual(cmd[cmd.index('--fps') + 1], '12')
                self.assertEqual(cmd[cmd.index('--size') + 1], '1280x720')
                (dest / 'ch-draft.mp4').write_bytes(b'video')
                return SimpleNamespace(returncode=0)

            probe = SimpleNamespace(stdout=json.dumps({'streams': [{'codec_type': 'video'}, {'codec_type': 'audio'}]}))
            item = (0, spec, dest, None, False, root, renderer, {'fps': 12, 'size': '1280x720', 'no_voice': True})
            with patch.object(chapter_pipeline.subprocess, 'run', side_effect=fake_node), \
                 patch.object(chapter_pipeline, 'run', return_value=probe):
                video = chapter_pipeline.render(item)
            self.assertEqual(video, dest / 'ch-draft.mp4')


if __name__ == '__main__':
    unittest.main()
