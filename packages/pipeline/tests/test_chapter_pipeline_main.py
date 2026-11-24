"""Tests for chapter_pipeline.main and the subprocess wrappers around it."""
import contextlib
import io
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from support import import_pipeline

chapter_pipeline = import_pipeline('chapter_pipeline')

LOUDNORM_STDERR = (
    '[Parsed_loudnorm_0 @ 0x1] \n'
    '{"input_i":"-23.1","input_tp":"-4.2","input_lra":"3.3","input_thresh":"-33.4","output_i":"-14.0","target_offset":"0.5"}\n'
)
NARRATED_SPEC = {'shots': [{'lines': ['こんにちは']}]}
SILENT_SPEC = {'shots': [{'camera': 'wide'}]}


class Project:
    """A throwaway project directory: manifest, chapter specs and a placeholder renderer entry."""

    def __init__(self, root: Path, chapters: list[dict], specs: dict[str, dict], **manifest_extra):
        self.root = root
        self.dir = root / 'project'
        self.dir.mkdir()
        self.renderer = root / 'render.js'
        self.renderer.write_text('', encoding='utf-8')
        self.out = root / 'out'
        for name, spec in specs.items():
            (self.dir / name).write_text(json.dumps(spec, ensure_ascii=False), encoding='utf-8')
        self.manifest = self.dir / 'chapters.json'
        self.manifest.write_text(json.dumps({'chapters': chapters, **manifest_extra}, ensure_ascii=False), encoding='utf-8')

    def argv(self, *extra: str) -> list[str]:
        return ['chapter_pipeline.py', str(self.manifest), '--out', str(self.out), '--renderer', str(self.renderer), *extra]


def two_chapter_project(root: Path, **manifest_extra) -> Project:
    chapters = [
        {'id': 'ch-1', 'title': '一章', 'spec': 'ch-1.json'},
        {'id': 'ch-2', 'title': "二章 it's", 'spec': 'ch-2.json'},
    ]
    return Project(root, chapters, {'ch-1.json': NARRATED_SPEC, 'ch-2.json': NARRATED_SPEC}, **manifest_extra)


class MainHarness:
    """Runs main() with the renderer, the card encoder, ffprobe and ffmpeg replaced by recording fakes."""

    def __init__(self, durations: dict[str, float] | None = None):
        self.durations = durations or {}
        self.rendered: list[tuple] = []
        self.cards: list[SimpleNamespace] = []
        self.commands: list[list[str]] = []
        self.stdout = ''
        self.stderr = ''

    def _render(self, item):
        self.rendered.append(item)
        dest = item[2]
        dest.mkdir(parents=True, exist_ok=True)
        video = dest / f'{dest.name}.mp4'
        video.write_bytes(f'rendered {dest.name}'.encode())
        return video

    def _card(self, title, number, image, video, series, fps, seconds, size=None, font=None):
        self.cards.append(SimpleNamespace(title=title, number=number, image=image, video=video, series=series,
                                          fps=fps, seconds=seconds, size=size, font=font))
        Path(video).write_bytes(b'card')

    def _duration(self, path):
        return self.durations.get(Path(path).name, 1.0)

    def _run(self, args, **kwargs):
        self.commands.append(list(args))
        return SimpleNamespace(stdout='', stderr=LOUDNORM_STDERR)

    def main(self, argv: list[str]) -> None:
        out, err = io.StringIO(), io.StringIO()
        try:
            with patch.object(sys, 'argv', argv), \
                 patch.object(chapter_pipeline, 'render', side_effect=self._render), \
                 patch.object(chapter_pipeline, 'card', side_effect=self._card), \
                 patch.object(chapter_pipeline, 'duration', side_effect=self._duration), \
                 patch.object(chapter_pipeline, 'run', side_effect=self._run), \
                 contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                chapter_pipeline.main()
        finally:
            self.stdout, self.stderr = out.getvalue(), err.getvalue()


class ChapterPipelineMainTests(unittest.TestCase):
    def test_main_renders_each_chapter_and_joins_them_with_cards_between(self):
        with TemporaryDirectory() as temp:
            project = two_chapter_project(Path(temp).resolve(), series='都市史', cardSeconds=3.0, fps=30, size='1280x720', font='Manifest.ttc')
            harness = MainHarness({'ch-1.mp4': 10.0, 'ch-2.mp4': 20.0, 'card-01.mp4': 3.0, 'episode.mp4': 33.0})
            harness.main(project.argv())
            jobs = project.out / 'jobs'

            self.assertEqual([item[0] for item in harness.rendered], [0, 1])
            index, spec, dest, cache, check_overlap, project_root, renderer, opts = harness.rendered[1]
            self.assertEqual((spec, dest, cache, check_overlap), (project.dir / 'ch-2.json', jobs / 'ch-2', None, False))
            self.assertEqual((project_root, renderer), (project.dir, project.renderer))
            self.assertEqual(opts, {'fps': 30, 'size': '1280x720', 'no_voice': False})

            # One title card, in front of the second chapter only.
            self.assertEqual(len(harness.cards), 1)
            card = harness.cards[0]
            self.assertEqual((card.title, card.number, card.series), ("二章 it's", 1, '都市史'))
            self.assertEqual((card.fps, card.seconds, card.size, card.font), (30, 3.0, (1280, 720), 'Manifest.ttc'))
            self.assertEqual((card.image, card.video), (jobs / 'card-01.png', jobs / 'card-01.mp4'))

            concat = project.out / 'concat.txt'
            self.assertEqual(concat.read_text(encoding='utf-8').splitlines(), [
                f"file '{(jobs / 'ch-1' / 'ch-1.mp4').as_posix()}'",
                f"file '{(jobs / 'card-01.mp4').as_posix()}'",
                f"file '{(jobs / 'ch-2' / 'ch-2.mp4').as_posix()}'",
            ])

            measure, join = harness.commands
            self.assertEqual(measure[measure.index('-i') + 1], str(concat))
            self.assertEqual(measure[measure.index('-af') + 1], 'loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json')
            self.assertEqual(measure[-3:], ['-f', 'null', '-'])
            self.assertEqual(join[join.index('-i') + 1], str(concat))
            self.assertEqual(join[join.index('-c:v') + 1], 'copy')
            self.assertEqual(
                join[join.index('-af') + 1],
                'loudnorm=I=-14:TP=-1.5:LRA=11:measured_I=-23.1:measured_TP=-4.2:measured_LRA=3.3:measured_thresh=-33.4:offset=0.5:linear=true',
            )
            self.assertEqual(join[-1], str(project.out / 'episode.mp4'))

            timeline = json.loads((project.out / 'chapters.json').read_text(encoding='utf-8'))
            self.assertEqual(timeline, [{'title': '一章', 'start': 0.0}, {'title': "二章 it's", 'start': 13.0}])
            self.assertIn('33.00s', harness.stdout)

    def test_command_line_options_override_the_manifest_and_reach_the_renderer(self):
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            project = two_chapter_project(root, fps=30, size='1280x720', font='Manifest.ttc')
            cache = root / 'voice-cache'
            cache.mkdir()
            harness = MainHarness()
            harness.main(project.argv('--fps', '12', '--size', '640x360', '--font', str(root / 'Cli.ttc'),
                                      '--voice-cache', str(cache), '--check-label-overlap', '--workers', '1'))
            for item in harness.rendered:
                self.assertEqual(item[3], cache)
                self.assertTrue(item[4])
                self.assertEqual(item[7], {'fps': 12, 'size': '640x360', 'no_voice': False})
            card = harness.cards[0]
            self.assertEqual((card.fps, card.size, card.font, card.seconds), (12, (640, 360), root / 'Cli.ttc', 2.5))

    def test_defaults_apply_when_neither_manifest_nor_command_line_sets_them(self):
        with TemporaryDirectory() as temp:
            project = two_chapter_project(Path(temp).resolve())
            harness = MainHarness()
            harness.main(project.argv())
            self.assertEqual(harness.rendered[0][7], {'fps': 24, 'size': '1920x1080', 'no_voice': False})
            self.assertEqual((harness.cards[0].series, harness.cards[0].size, harness.cards[0].font), ('', (1920, 1080), None))

    def test_no_voice_allows_chapters_without_narration(self):
        with TemporaryDirectory() as temp:
            chapters = [{'id': 'draft', 'title': '下書き', 'spec': 'draft.json'}]
            project = Project(Path(temp).resolve(), chapters, {'draft.json': SILENT_SPEC})
            harness = MainHarness()
            harness.main(project.argv('--no-voice'))
            self.assertTrue(harness.rendered[0][7]['no_voice'])
            self.assertEqual(harness.cards, [])
            self.assertEqual(len((project.out / 'concat.txt').read_text(encoding='utf-8').splitlines()), 1)

    def test_chapter_without_narration_is_rejected_unless_no_voice(self):
        with TemporaryDirectory() as temp:
            chapters = [{'id': 'ok', 'title': '一', 'spec': 'ok.json'}, {'id': 'silent', 'title': '二', 'spec': 'silent.json'}]
            project = Project(Path(temp).resolve(), chapters, {'ok.json': NARRATED_SPEC, 'silent.json': SILENT_SPEC})
            harness = MainHarness()
            with self.assertRaisesRegex(ValueError, 'chapter 1: narrated shots are required'):
                harness.main(project.argv())
            self.assertEqual(harness.rendered, [])

    def test_chapter_spec_with_bgm_is_rejected(self):
        with TemporaryDirectory() as temp:
            chapters = [{'id': 'music', 'title': '一', 'spec': 'music.json'}]
            project = Project(Path(temp).resolve(), chapters, {'music.json': {**NARRATED_SPEC, 'bgm': {'file': 'song.mp3'}}})
            with self.assertRaisesRegex(ValueError, 'does not mix BGM'):
                MainHarness().main(project.argv())

    def test_missing_chapter_spec_raises_file_not_found_with_its_path(self):
        with TemporaryDirectory() as temp:
            chapters = [{'id': 'gone', 'title': '一', 'spec': 'gone.json'}]
            project = Project(Path(temp).resolve(), chapters, {})
            with self.assertRaises(FileNotFoundError) as caught:
                MainHarness().main(project.argv())
            self.assertEqual(caught.exception.args[0], project.dir / 'gone.json')

    def test_existing_output_directory_is_never_overwritten(self):
        with TemporaryDirectory() as temp:
            project = two_chapter_project(Path(temp).resolve())
            project.out.mkdir()
            (project.out / 'episode.mp4').write_bytes(b'previous')
            harness = MainHarness()
            with self.assertRaises(FileExistsError):
                harness.main(project.argv())
            self.assertEqual((project.out / 'episode.mp4').read_bytes(), b'previous')
            self.assertEqual(harness.rendered, [])

    def test_invalid_size_is_rejected_before_the_output_directory_is_created(self):
        with TemporaryDirectory() as temp:
            project = two_chapter_project(Path(temp).resolve())
            with self.assertRaisesRegex(ValueError, 'invalid size'):
                MainHarness().main(project.argv('--size', '1080p'))
            self.assertFalse(project.out.exists())

    def test_usage_errors_exit_with_status_2_and_create_nothing(self):
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            project = two_chapter_project(root)
            cases = {
                'workers must be between 1 and 4': project.argv('--workers', '5'),
                'workers must be between': project.argv('--workers', '0'),
                'renderer not built': [*project.argv()[:4], '--renderer', str(root / 'missing.js')],
                'voice cache must be an existing directory': project.argv('--voice-cache', str(root / 'no-cache')),
            }
            for message, argv in cases.items():
                with self.subTest(message=message):
                    harness = MainHarness()
                    with self.assertRaises(SystemExit) as caught:
                        harness.main(argv)
                    self.assertEqual(caught.exception.code, 2)
                    self.assertIn(message, harness.stderr)
                    self.assertFalse(project.out.exists())
                    self.assertEqual(harness.rendered, [])

    def test_invalid_chapter_ids_are_reported_as_usage_errors(self):
        bad_manifests = {
            'chapter ids must be unique': [{'id': 'a', 'title': '一', 'spec': 'a.json'}, {'id': 'a', 'title': '二', 'spec': 'a.json'}],
            'chapter ids must be alphanumeric': [{'id': '../escape', 'title': '一', 'spec': 'a.json'}],
            'manifest must contain chapters': [],
        }
        for message, chapters in bad_manifests.items():
            with self.subTest(message=message), TemporaryDirectory() as temp:
                project = Project(Path(temp).resolve(), chapters, {'a.json': NARRATED_SPEC})
                harness = MainHarness()
                with self.assertRaises(SystemExit) as caught:
                    harness.main(project.argv())
                self.assertEqual(caught.exception.code, 2)
                self.assertIn(message, harness.stderr)
                self.assertFalse(project.out.exists())


class ChapterReuseTests(unittest.TestCase):
    def previous_run(self, root: Path, specs: dict[str, dict]) -> Path:
        previous = root / 'previous'
        for chapter_id, spec in specs.items():
            job = previous / 'jobs' / chapter_id
            job.mkdir(parents=True)
            (job / f'{chapter_id}.mp4').write_bytes(f'previous {chapter_id}'.encode())
            (job / 'spec.json').write_text(json.dumps(spec, ensure_ascii=False), encoding='utf-8')
        return previous

    def test_unchanged_chapter_is_copied_from_previous_run_and_changed_one_is_rendered(self):
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            project = two_chapter_project(root)
            previous = self.previous_run(root, {'ch-1': NARRATED_SPEC, 'ch-2': {'shots': [{'lines': ['古い台本']}]}})
            harness = MainHarness()
            harness.main(project.argv('--reuse-from', str(previous)))

            self.assertEqual([item[2].name for item in harness.rendered], ['ch-2'])
            jobs = project.out / 'jobs'
            self.assertEqual((jobs / 'ch-1' / 'ch-1.mp4').read_bytes(), b'previous ch-1')
            self.assertEqual(json.loads((jobs / 'ch-1' / 'spec.json').read_text(encoding='utf-8')), NARRATED_SPEC)
            self.assertEqual((jobs / 'ch-2' / 'ch-2.mp4').read_bytes(), b'rendered ch-2')
            # The joined order is unaffected by which chapters were reused.
            lines = (project.out / 'concat.txt').read_text(encoding='utf-8').splitlines()
            self.assertEqual([Path(line[6:-1]).name for line in lines], ['ch-1.mp4', 'card-01.mp4', 'ch-2.mp4'])
            self.assertIn('rendering 1 chapters with 3 workers (1 reused)', harness.stdout)

    def test_rerender_forces_a_reusable_chapter_by_id_or_index(self):
        for selector in ('ch-1', ' 0 ,'):
            with self.subTest(selector=selector), TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                project = two_chapter_project(root)
                previous = self.previous_run(root, {'ch-1': NARRATED_SPEC, 'ch-2': NARRATED_SPEC})
                harness = MainHarness()
                harness.main(project.argv('--reuse-from', str(previous), '--rerender', selector))
                self.assertEqual([item[2].name for item in harness.rendered], ['ch-1'])
                self.assertEqual((project.out / 'jobs' / 'ch-2' / 'ch-2.mp4').read_bytes(), b'previous ch-2')

    def test_when_every_chapter_is_reused_the_renderer_is_not_started(self):
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            project = two_chapter_project(root)
            previous = self.previous_run(root, {'ch-1': NARRATED_SPEC, 'ch-2': NARRATED_SPEC})
            harness = MainHarness()
            harness.main(project.argv('--reuse-from', str(previous)))
            self.assertEqual(harness.rendered, [])
            self.assertTrue((project.out / 'chapters.json').is_file())
            self.assertEqual(len(harness.commands), 2)


class SubprocessWrapperTests(unittest.TestCase):
    def test_run_returns_captured_output_and_raises_on_nonzero_exit(self):
        done = chapter_pipeline.run([sys.executable, '-c', 'print("probe ok")'], capture_output=True, text=True)
        self.assertEqual(done.stdout.strip(), 'probe ok')
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            chapter_pipeline.run([sys.executable, '-c', 'raise SystemExit(3)'])
        self.assertEqual(caught.exception.returncode, 3)

    def test_parse_loudnorm_rejects_braces_that_are_not_json(self):
        with self.assertRaisesRegex(ValueError, 'invalid JSON'):
            chapter_pipeline.parse_loudnorm('[Parsed_loudnorm_0] {input_i: broken}')

    def test_render_copies_voice_cache_and_spec_next_to_the_output(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            spec = root / 'chapter.json'
            spec.write_text('{"shots": []}', encoding='utf-8')
            cache = root / 'cache'
            (cache / 'f1').mkdir(parents=True)
            (cache / 'f1' / 'line.wav').write_bytes(b'wav')
            dest = root / 'jobs' / 'ch-1'
            seen = {}

            def fake_node(cmd, **kwargs):
                # The renderer must find the cache in place when it starts.
                seen['cache_ready'] = (dest / 'voice-cache' / 'f1' / 'line.wav').read_bytes()
                seen['cmd'] = cmd
                (dest / 'ch-1.mp4').write_bytes(b'video')
                return SimpleNamespace(returncode=0)

            probe = SimpleNamespace(stdout=json.dumps({'streams': [{'codec_type': 'audio'}, {'codec_type': 'video'}]}))
            with patch.object(chapter_pipeline.subprocess, 'run', side_effect=fake_node), \
                 patch.object(chapter_pipeline, 'run', return_value=probe), \
                 contextlib.redirect_stdout(io.StringIO()):
                chapter_pipeline.render((3, spec, dest, cache, False, root, root / 'render.js'))
            self.assertEqual(seen['cache_ready'], b'wav')
            self.assertEqual((dest / 'spec.json').read_text(encoding='utf-8'), '{"shots": []}')
            self.assertEqual(seen['cmd'], [
                'node', str(root / 'render.js'), str(spec), '--project', str(root), '--out', str(dest),
                '--size', '1920x1080', '--fps', '24', '--raw-audio',
            ])

    def test_render_reports_nonzero_renderer_exit_with_the_log_path(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            spec = root / 'chapter.json'
            spec.write_text('{}', encoding='utf-8')
            dest = root / 'jobs' / 'ch-9'

            def fake_node(cmd, **kwargs):
                kwargs['stdout'].write('renderer crashed\n')
                return SimpleNamespace(returncode=1)

            with patch.object(chapter_pipeline.subprocess, 'run', side_effect=fake_node), \
                 patch.object(chapter_pipeline, 'run') as probe:
                with self.assertRaisesRegex(RuntimeError, r'chapter 9 failed.*ch-9\.log'):
                    chapter_pipeline.render((9, spec, dest, None, False, root, root / 'render.js'))
            probe.assert_not_called()
            self.assertEqual((root / 'jobs' / 'ch-9.log').read_text(encoding='utf-8'), 'renderer crashed\n')


def make_clip(path: Path, colour: str, seconds: float) -> None:
    subprocess.run(
        [
            'ffmpeg', '-nostdin', '-v', 'error', '-y',
            '-f', 'lavfi', '-i', f'color=c={colour}:s=160x90:r=24',
            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
            '-t', str(seconds), '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-ar', '48000', '-ac', '2', str(path),
        ],
        check=True,
    )


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg and ffprobe are required')
class JoinWithRealFfmpegTests(unittest.TestCase):
    def test_measure_and_join_commands_produce_a_playable_episode(self):
        """Only the renderer and the card drawing are faked; concat, loudnorm and ffprobe are real."""
        def fake_render(item):
            dest = item[2]
            dest.mkdir(parents=True)
            video = dest / f'{dest.name}.mp4'
            make_clip(video, 'blue', 1.0)
            return video

        def fake_card(title, number, image, video, series, fps, seconds, size=None, font=None):
            make_clip(video, 'black', seconds)

        with TemporaryDirectory() as temp:
            project = two_chapter_project(Path(temp).resolve(), cardSeconds=0.5)
            with patch.object(sys, 'argv', project.argv()), \
                 patch.object(chapter_pipeline, 'render', side_effect=fake_render), \
                 patch.object(chapter_pipeline, 'card', side_effect=fake_card), \
                 contextlib.redirect_stdout(io.StringIO()):
                chapter_pipeline.main()

            episode = project.out / 'episode.mp4'
            probe = json.loads(subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type:format=duration', '-of', 'json', str(episode)],
                check=True, capture_output=True, text=True,
            ).stdout)
            self.assertEqual(sorted(s['codec_type'] for s in probe['streams']), ['audio', 'video'])
            self.assertAlmostEqual(float(probe['format']['duration']), 2.5, delta=0.2)
            timeline = json.loads((project.out / 'chapters.json').read_text(encoding='utf-8'))
            self.assertEqual([entry['title'] for entry in timeline], ['一章', "二章 it's"])
            self.assertEqual(timeline[0]['start'], 0.0)
            self.assertAlmostEqual(timeline[1]['start'], 1.5, delta=0.15)


if __name__ == '__main__':
    unittest.main()
