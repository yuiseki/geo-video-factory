import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from support import import_pipeline

ffmpeg_ops = import_pipeline('video.ffmpeg_ops')


def _probe_json(
    *,
    duration='120.0',
    width=1920,
    height=1080,
    fps='24/1',
    v_codec='h264',
    pix_fmt='yuv420p',
    a_codec='aac',
    sample_rate='48000',
    channels=2,
):
    streams = [
        {
            'codec_type': 'video',
            'codec_name': v_codec,
            'width': width,
            'height': height,
            'r_frame_rate': fps,
            'avg_frame_rate': fps,
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
    return json.dumps({'format': {'duration': duration, 'size': '1024'}, 'streams': streams})


class FfmpegOpsTests(unittest.TestCase):
    def test_ensure_safe_output_path_rejects_same_source_and_existing_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / 'a.mp4'
            b = root / 'b.mp4'
            out = root / 'out.mp4'
            a.write_bytes(b'a')
            b.write_bytes(b'b')
            out.write_bytes(b'old')

            with self.assertRaises(ValueError):
                ffmpeg_ops.ensure_safe_output_path([a, b], b, overwrite=True)

            with self.assertRaises(FileExistsError):
                ffmpeg_ops.ensure_safe_output_path([a], out, overwrite=False)

            ffmpeg_ops.ensure_safe_output_path([a], out, overwrite=True)
            ffmpeg_ops.ensure_safe_output_path([a], root / 'fresh.mp4', overwrite=False)

    def test_probe_streams_and_concat_compatibility(self):
        p1 = _probe_json(width=1920, height=1080, v_codec='h264', sample_rate='48000')
        p2 = _probe_json(width=1280, height=720, v_codec='hevc', sample_rate='44100')
        with patch.object(ffmpeg_ops, 'run_cmd', return_value=SimpleNamespace(returncode=0, stdout=p1, stderr='')):
            m1 = ffmpeg_ops.probe_streams(Path('a.mp4'))
        with patch.object(ffmpeg_ops, 'run_cmd', return_value=SimpleNamespace(returncode=0, stdout=p2, stderr='')):
            m2 = ffmpeg_ops.probe_streams(Path('b.mp4'))

        self.assertEqual(m1['width'], 1920)
        self.assertEqual(m1['fps'], 24.0)
        self.assertEqual(m1['sample_rate'], 48000)

        ok, reasons = ffmpeg_ops.check_concat_compatible([m1, dict(m1)])
        self.assertTrue(ok)
        self.assertEqual(reasons, [])

        ok2, reasons2 = ffmpeg_ops.check_concat_compatible([m1, m2])
        self.assertFalse(ok2)
        self.assertTrue(any('resolution' in r for r in reasons2))
        self.assertTrue(any('video_codec' in r for r in reasons2))
        self.assertTrue(any('sample_rate' in r for r in reasons2))

    def test_build_trim_command_lossless_default_and_reencode(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'in.mp4'
            src.write_bytes(b'v')
            out = root / 'cut.mp4'

            cmd = ffmpeg_ops.build_trim_command(src, out, start=5.0, end=20.0)
            self.assertEqual(cmd[:3], ['ffmpeg', '-hide_banner', '-nostdin'])
            self.assertIn('-n', cmd)
            self.assertIn('-ss', cmd)
            self.assertIn('-to', cmd)
            self.assertIn('copy', cmd)
            self.assertIn('-avoid_negative_ts', cmd)

            cmd_re = ffmpeg_ops.build_trim_command(
                src, out, start=2.5, duration=10.0, lossless=False, overwrite=True
            )
            self.assertIn('-y', cmd_re)
            self.assertIn('-t', cmd_re)
            self.assertIn('libx264', cmd_re)
            self.assertIn('yuv420p', cmd_re)
            self.assertIn('aac', cmd_re)

            with self.assertRaises(ValueError):
                ffmpeg_ops.build_trim_command(src, out, start=-1.0, end=5.0)
            with self.assertRaises(ValueError):
                ffmpeg_ops.build_trim_command(src, out, start=10.0, end=10.0)
            with self.assertRaises(ValueError):
                ffmpeg_ops.build_trim_command(src, out, start=1.0, end=5.0, duration=3.0)

    def test_format_concat_list_and_build_concat_command(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a'b.mp4"
            b = root / 'c.mp4'
            lst = root / 'list.txt'
            out = root / 'joined.mp4'
            a.write_bytes(b'a')
            b.write_bytes(b'b')

            text = ffmpeg_ops.format_concat_list([a, b])
            self.assertIn("a'\\''b.mp4'", text)
            self.assertIn("c.mp4'", text)

            cmd = ffmpeg_ops.build_concat_command([a, b], out, list_path=lst)
            self.assertIn('-f', cmd)
            self.assertIn('concat', cmd)
            self.assertIn('-safe', cmd)
            self.assertIn('copy', cmd)
            self.assertIn('-n', cmd)

            with self.assertRaises(ValueError):
                ffmpeg_ops.build_concat_command([a], out, list_path=lst)

    def test_build_reframe_command_crop_and_blur(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'wide.mp4'
            src.write_bytes(b'v')
            out = root / 'short.mp4'

            crop_cmd = ffmpeg_ops.build_reframe_command(src, out, mode='crop')
            vf = crop_cmd[crop_cmd.index('-vf') + 1]
            self.assertIn('scale=1080:1920:force_original_aspect_ratio=increase', vf)
            self.assertIn('crop=1080:1920', vf)
            self.assertIn('yuv420p', crop_cmd)
            self.assertIn('+faststart', crop_cmd)

            blur_cmd = ffmpeg_ops.build_reframe_command(src, out, mode='blur', overwrite=True)
            fc = blur_cmd[blur_cmd.index('-filter_complex') + 1]
            self.assertIn('split=2', fc)
            self.assertIn('boxblur=20:5', fc)
            self.assertIn('overlay=(W-w)/2:(H-h)/2', fc)
            self.assertIn('0:a?', blur_cmd)

            with self.assertRaises(ValueError):
                ffmpeg_ops.build_reframe_command(src, out, mode='stretch')

    def test_loudnorm_two_pass_builders_parser_and_runner(self):
        stderr = (
            '[Parsed_loudnorm_0 @ 0x1]\n'
            '{\n'
            '  "input_i" : "-18.40",\n'
            '  "input_tp" : "-2.10",\n'
            '  "input_lra" : "7.20",\n'
            '  "input_thresh" : "-28.80",\n'
            '  "target_offset" : "0.40"\n'
            '}\n'
        )
        stats = ffmpeg_ops.parse_loudnorm_stats(stderr)
        self.assertEqual(stats['measured_I'], '-18.40')
        self.assertEqual(stats['offset'], '0.40')

        with self.assertRaises(ValueError):
            ffmpeg_ops.parse_loudnorm_stats('no loudnorm json')

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'ep.mp4'
            src.write_bytes(b'v')
            out = root / 'ep_norm.mp4'

            p1 = ffmpeg_ops.build_loudnorm_pass1_command(src, target_i=-14.0, target_tp=-1.5, target_lra=11.0)
            self.assertIn('loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json', p1)
            self.assertEqual(p1[-2:], ['null', '-'])

            p2 = ffmpeg_ops.build_loudnorm_pass2_command(
                src, out, stats, target_i=-14.0, target_tp=-1.5, target_lra=11.0
            )
            af = p2[p2.index('-af') + 1]
            self.assertIn('measured_I=-18.40', af)
            self.assertIn('linear=true', af)
            self.assertIn('copy', p2)
            self.assertIn('48000', p2)

            with patch.object(ffmpeg_ops, 'run_cmd') as run_mock:
                plan = ffmpeg_ops.normalize_loudness(src, out, dry_run=True)
            run_mock.assert_not_called()
            self.assertTrue(plan['dry_run'])
            self.assertIn('pass1_command', plan)

            with patch.object(
                ffmpeg_ops,
                'run_cmd',
                side_effect=[
                    SimpleNamespace(returncode=0, stdout='', stderr=stderr),
                    SimpleNamespace(returncode=0, stdout='', stderr=''),
                ],
            ) as run_mock:
                res = ffmpeg_ops.normalize_loudness(src, out, dry_run=False)
            self.assertEqual(run_mock.call_count, 2)
            self.assertEqual(res['measured']['measured_I'], '-18.40')

    def test_build_duck_bgm_command_with_fade_out_and_validation(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            voice = root / 'voice.mp4'
            bgm = root / 'bgm.wav'
            out = root / 'mixed.mp4'
            voice.write_bytes(b'v')
            bgm.write_bytes(b'b')

            cmd = ffmpeg_ops.build_duck_bgm_command(
                voice, bgm, out,
                bgm_volume=0.35,
                threshold=0.04,
                ratio=8.0,
                attack_ms=15.0,
                release_ms=350.0,
                fade_out_start=118.0,
                fade_out_duration=2.0,
            )
            self.assertIn('-stream_loop', cmd)
            self.assertIn('-shortest', cmd)
            self.assertIn('copy', cmd)
            fc = cmd[cmd.index('-filter_complex') + 1]
            self.assertIn('sidechaincompress=threshold=0.04:ratio=8:attack=15:release=350', fc)
            self.assertIn('afade=t=out:st=118:d=2', fc)
            self.assertIn('loudnorm=I=-14:TP=-1.5:LRA=11', fc)

            with self.assertRaises(ValueError):
                ffmpeg_ops.build_duck_bgm_command(voice, bgm, out, bgm_volume=0.0)
            with self.assertRaises(ValueError):
                ffmpeg_ops.build_duck_bgm_command(voice, bgm, out, ratio=0.5)

    def test_build_export_command_presets(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'src.mp4'
            src.write_bytes(b'v')
            out = root / 'dist.mp4'

            yt = ffmpeg_ops.build_export_command(src, out, preset='youtube_1080p')
            self.assertIn('libx264', yt)
            self.assertIn('yuv420p', yt)
            self.assertIn('192k', yt)
            self.assertIn('+faststart', yt)

            sh = ffmpeg_ops.build_export_command(src, out, preset='shorts_9x16', reframe_mode='blur')
            self.assertIn('-filter_complex', sh)
            self.assertIn('boxblur=20:5', sh[sh.index('-filter_complex') + 1])

            with self.assertRaises(ValueError):
                ffmpeg_ops.build_export_command(src, out, preset='unknown')

    def test_cli_dry_run_and_probe(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'ep.mp4'
            bgm = root / 'bgm.wav'
            out = root / 'out.mp4'
            src.write_bytes(b'v')
            bgm.write_bytes(b'b')

            with patch.object(ffmpeg_ops, 'run_cmd') as run_mock:
                code, text = ffmpeg_ops.run_cli([
                    'trim', str(src), '-o', str(out), '--start', '1', '--end', '5', '--dry-run', '--json',
                ])
                self.assertEqual(code, 0)
                data = json.loads(text)
                self.assertTrue(data['dry_run'])
                self.assertIn('command', data)

                code2, text2 = ffmpeg_ops.run_cli([
                    'duck-bgm', str(src), str(bgm), '-o', str(out), '--dry-run', '--json',
                ])
                self.assertEqual(code2, 0)
                self.assertIn('sidechaincompress', ' '.join(json.loads(text2)['command']))
                run_mock.assert_not_called()

            with patch.object(
                ffmpeg_ops, 'run_cmd',
                return_value=SimpleNamespace(returncode=0, stdout=_probe_json(), stderr=''),
            ):
                code3, text3 = ffmpeg_ops.run_cli(['probe', str(src), '--json'])
                self.assertEqual(code3, 0)
                self.assertEqual(json.loads(text3)['width'], 1920)


if __name__ == '__main__':
    unittest.main()
