import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from support import import_pipeline

video_qa = import_pipeline('video_qa')


def _sample_ffprobe_json(
    *,
    duration='120.0',
    width=1920,
    height=1080,
    r_frame_rate='24/1',
    avg_frame_rate='24/1',
    v_codec='h264',
    pix_fmt='yuv420p',
    a_codec='aac',
    sample_rate='48000',
    channels=2,
    size='10485760',
):
    streams = [
        {
            'codec_type': 'video',
            'codec_name': v_codec,
            'width': width,
            'height': height,
            'r_frame_rate': r_frame_rate,
            'avg_frame_rate': avg_frame_rate,
            'pix_fmt': pix_fmt,
        }
    ]
    if a_codec is not None:
        streams.append(
            {
                'codec_type': 'audio',
                'codec_name': a_codec,
                'sample_rate': sample_rate,
                'channels': channels,
            }
        )
    return json.dumps(
        {
            'format': {'duration': duration, 'size': size},
            'streams': streams,
        }
    )


class VideoQaTests(unittest.TestCase):
    def test_parse_tiles_valid_and_invalid(self):
        self.assertEqual(video_qa.parse_tiles('4x3'), (4, 3))
        self.assertEqual(video_qa.parse_tiles('3x2'), (3, 2))
        for bad in ('0x3', '4x0', 'abc', '4*3', '-1x2'):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    video_qa.parse_tiles(bad)

    def test_ensure_safe_output_path_guards_same_path_and_existing_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'episode.mp4'
            src.write_bytes(b'video')
            out = root / 'contact.png'
            out.write_bytes(b'old')

            with self.assertRaises(ValueError):
                video_qa.ensure_safe_output_path(src, src, overwrite=True)

            with self.assertRaises(FileExistsError):
                video_qa.ensure_safe_output_path(src, out, overwrite=False)

            video_qa.ensure_safe_output_path(src, out, overwrite=True)
            video_qa.ensure_safe_output_path(src, root / 'new.png', overwrite=False)

    def test_probe_media_parses_video_audio_and_vfr_flag(self):
        payload = _sample_ffprobe_json(r_frame_rate='60/1', avg_frame_rate='24000/1001')
        with patch.object(video_qa, 'run_cmd', return_value=SimpleNamespace(returncode=0, stdout=payload, stderr='')):
            meta = video_qa.probe_media(Path('episode.mp4'))
        self.assertEqual(meta['duration'], 120.0)
        self.assertEqual(meta['width'], 1920)
        self.assertEqual(meta['height'], 1080)
        self.assertAlmostEqual(meta['fps'], 24000 / 1001, places=3)
        self.assertTrue(meta['vfr_suspected'])
        self.assertEqual(meta['video_codec'], 'h264')
        self.assertEqual(meta['pix_fmt'], 'yuv420p')
        self.assertEqual(meta['audio_codec'], 'aac')
        self.assertEqual(meta['channels'], 2)

    def test_measure_loudness_parses_stderr_json_and_handles_missing(self):
        stderr = (
            '[Parsed_loudnorm_0 @ 0x1] \n'
            '{\n'
            '  "input_i" : "-14.20",\n'
            '  "input_tp" : "-1.50",\n'
            '  "input_lra" : "6.80",\n'
            '  "input_thresh" : "-24.50",\n'
            '  "target_offset" : "0.20"\n'
            '}\n'
        )
        with patch.object(video_qa, 'run_cmd', return_value=SimpleNamespace(returncode=0, stdout='', stderr=stderr)):
            loud = video_qa.measure_loudness(Path('episode.mp4'))
        self.assertEqual(loud, {'lufs': -14.2, 'tp': -1.5, 'lra': 6.8})

        with patch.object(video_qa, 'run_cmd', return_value=SimpleNamespace(returncode=0, stdout='', stderr='no json')):
            self.assertEqual(video_qa.measure_loudness(Path('episode.mp4')), {})

    def test_evaluate_compliance_passes_valid_youtube_video(self):
        meta = {
            'duration': 600.0,
            'size_bytes': 120_000_000,
            'width': 1920,
            'height': 1080,
            'fps': 24.0,
            'vfr_suspected': False,
            'video_codec': 'h264',
            'pix_fmt': 'yuv420p',
            'audio_codec': 'aac',
            'channels': 2,
        }
        loud = {'lufs': -14.1, 'tp': -1.2, 'lra': 7.0}
        report = video_qa.evaluate_compliance(meta, loud, platform='youtube')
        self.assertTrue(report['ok'])
        self.assertEqual([r for r in report['rows'] if r['status'] == 'FAIL'], [])

    def test_evaluate_compliance_flags_bad_pix_fmt_loudness_and_aspect(self):
        meta = {
            'duration': 200.0,
            'size_bytes': 50_000_000,
            'width': 1920,
            'height': 1080,
            'fps': 24.0,
            'vfr_suspected': True,
            'video_codec': 'h264',
            'pix_fmt': 'yuv444p',
            'audio_codec': 'aac',
            'channels': 2,
        }
        loud = {'lufs': -23.0, 'tp': 0.2, 'lra': 10.0}
        report = video_qa.evaluate_compliance(meta, loud, platform='shorts')
        self.assertFalse(report['ok'])
        by_name = {r['name']: r['status'] for r in report['rows']}
        self.assertEqual(by_name['aspect'], 'FAIL')
        self.assertEqual(by_name['pix_fmt'], 'FAIL')
        self.assertEqual(by_name['loudness'], 'FAIL')
        self.assertEqual(by_name['true_peak'], 'FAIL')
        self.assertEqual(by_name['vfr'], 'WARN')
        self.assertEqual(by_name['duration'], 'WARN')

    def test_detect_content_anomalies_parses_black_freeze_and_silence(self):
        stderr = '\n'.join([
            '[blackdetect @ 0x1] black_start:0 black_end:15.0 black_duration:15.0',
            '[freezedetect @ 0x2] lavfi.freezedetect.freeze_start: 20.0',
            '[freezedetect @ 0x2] lavfi.freezedetect.freeze_duration: 35.0',
            '[silencedetect @ 0x3] silence_start: 10.0',
            '[silencedetect @ 0x3] silence_end: 70.0 | silence_duration: 60.0',
        ])
        with patch.object(video_qa, 'run_cmd', return_value=SimpleNamespace(returncode=0, stdout='', stderr=stderr)):
            rows = video_qa.detect_content_anomalies(Path('episode.mp4'), duration=100.0)
        by_name = {r['name']: r for r in rows}
        self.assertEqual(by_name['black']['status'], 'WARN')
        self.assertAlmostEqual(by_name['black']['actual_share'], 0.15, places=3)
        self.assertEqual(by_name['frozen']['status'], 'WARN')
        self.assertAlmostEqual(by_name['frozen']['max_seconds'], 35.0, places=2)
        self.assertEqual(by_name['silence']['status'], 'WARN')
        self.assertAlmostEqual(by_name['silence']['actual_share'], 0.60, places=3)

    def test_build_contact_sheet_computes_uniform_interval_timecode_and_safe_zone(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'episode.mp4'
            src.write_bytes(b'video')
            out = root / 'contact.png'

            with patch.object(video_qa, 'has_ffmpeg_filter', return_value=True), \
                 patch.object(video_qa, 'run_cmd', return_value=SimpleNamespace(returncode=0, stdout='', stderr='')) as run:
                result = video_qa.build_contact_sheet(
                    src,
                    out,
                    duration=120.0,
                    tiles=(4, 3),
                    safe='shorts',
                    overwrite=True,
                )

            cmd = run.call_args.args[0]
            self.assertEqual(cmd[0], 'ffmpeg')
            vf = cmd[cmd.index('-vf') + 1]
            self.assertIn('fps=12/120.000', vf)
            self.assertIn('pad=iw:ih+28:0:28:black', vf)
            self.assertIn('drawtext=', vf)
            self.assertIn('pts', vf)
            self.assertIn('drawbox=', vf)
            self.assertIn('tile=4x3', vf)
            self.assertEqual(result['output'], str(out))
            self.assertEqual(result['tiles'], '4x3')
            self.assertEqual(result['timecode_mode'], 'drawtext')

    def test_build_contact_sheet_falls_back_when_drawtext_filter_missing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'episode.mp4'
            src.write_bytes(b'video')
            out = root / 'contact.png'

            with patch.object(video_qa, 'has_ffmpeg_filter', return_value=False), \
                 patch.object(video_qa, 'run_cmd', return_value=SimpleNamespace(returncode=0, stdout='', stderr='')) as run:
                result = video_qa.build_contact_sheet(
                    src,
                    out,
                    duration=60.0,
                    tiles=(2, 2),
                    overwrite=True,
                )

            vf = run.call_args.args[0][run.call_args.args[0].index('-vf') + 1]
            self.assertNotIn('drawtext=', vf)
            self.assertIn('tile=2x2', vf)
            self.assertEqual(result['timecode_mode'], 'none')

    def test_build_contact_sheet_dry_run_skips_ffmpeg(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'episode.mp4'
            src.write_bytes(b'video')
            out = root / 'contact.png'

            with patch.object(video_qa, 'run_cmd') as run:
                result = video_qa.build_contact_sheet(
                    src,
                    out,
                    duration=60.0,
                    tiles=(3, 2),
                    dry_run=True,
                )

            run.assert_not_called()
            self.assertTrue(result['dry_run'])
            self.assertIn('command', result)

    def test_cli_json_and_exit_code_reflect_compliance(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'episode.mp4'
            src.write_bytes(b'video')

            ok_meta = {
                'duration': 60.0,
                'size_bytes': 10_000_000,
                'width': 1920,
                'height': 1080,
                'fps': 24.0,
                'vfr_suspected': False,
                'video_codec': 'h264',
                'pix_fmt': 'yuv420p',
                'audio_codec': 'aac',
                'channels': 2,
            }
            with patch.object(video_qa, 'probe_media', return_value=ok_meta), \
                 patch.object(video_qa, 'measure_loudness', return_value={'lufs': -14.0, 'tp': -1.5, 'lra': 6.0}):
                code, payload = video_qa.run_cli([str(src), '--platform', 'youtube', '--json'])
            self.assertEqual(code, 0)
            data = json.loads(payload)
            self.assertTrue(data['compliance']['ok'])

            bad_meta = dict(ok_meta, pix_fmt='yuv444p')
            with patch.object(video_qa, 'probe_media', return_value=bad_meta), \
                 patch.object(video_qa, 'measure_loudness', return_value={'lufs': -14.0, 'tp': -1.5, 'lra': 6.0}):
                code, payload = video_qa.run_cli([str(src), '--platform', 'youtube', '--json'])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(payload)['compliance']['ok'])

    def test_cli_storyboard_invokes_adaptive_storyboard(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'episode.mp4'
            src.write_bytes(b'video')
            sb = root / 'storyboard.jpg'
            ok_meta = {
                'duration': 60.0, 'size_bytes': 10_000_000, 'width': 1920, 'height': 1080,
                'fps': 24.0, 'vfr_suspected': False, 'video_codec': 'h264',
                'pix_fmt': 'yuv420p', 'audio_codec': 'aac', 'channels': 2,
            }
            fake_sb = {'outputs': [str(sb)], 'keyframes': 12, 'timeline': 'TIMELINE', 'timestamps': [0.0]}
            video_inspect = import_pipeline('video_inspect')
            with patch.object(video_qa, 'probe_media', return_value=ok_meta), \
                 patch.object(video_qa, 'measure_loudness', return_value={'lufs': -14.0, 'tp': -1.5, 'lra': 6.0}), \
                 patch.object(video_inspect, 'build_adaptive_storyboard', return_value=fake_sb) as mock_sb:
                code, payload = video_qa.run_cli([
                    str(src), '--platform', 'youtube', '--storyboard', str(sb), '--storyboard-budget', '16', '--json',
                ])
            self.assertEqual(code, 0)
            mock_sb.assert_called_once()
            self.assertEqual(json.loads(payload)['storyboard']['keyframes'], 12)


if __name__ == '__main__':
    unittest.main()
