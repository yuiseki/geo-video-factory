"""Typed, deterministic FFmpeg command builders and safe execution wrappers.

Prevents agents from assembling raw FFmpeg shell strings by enforcing:
- safe output guards (never overwrite inputs, explicit overwrite opt-in)
- lossless stream copy by default where possible
- two-pass EBU R128 loudness normalization and sidechain BGM ducking
- vertical 9:16 reframing (crop / blur-pad) and platform export presets
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from fractions import Fraction
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

FFMPEG_BASE = ['ffmpeg', '-hide_banner', '-nostdin']
H264_AAC_ARGS = [
    '-c:v', 'libx264', '-crf', '18', '-preset', 'medium', '-pix_fmt', 'yuv420p',
    '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-movflags', '+faststart',
]
EXPORT_PRESETS: dict[str, dict[str, Any]] = {
    'youtube_1080p': {'width': 1920, 'height': 1080, 'video_codec': 'libx264', 'crf': 18,
                      'preset': 'medium', 'pix_fmt': 'yuv420p', 'audio_codec': 'aac',
                      'audio_bitrate': '192k', 'sample_rate': 48000},
    'shorts_9x16': {'width': 1080, 'height': 1920, 'video_codec': 'libx264', 'crf': 18,
                    'preset': 'medium', 'pix_fmt': 'yuv420p', 'audio_codec': 'aac',
                    'audio_bitrate': '192k', 'sample_rate': 48000},
}


def run_cmd(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=True, text=True)


def ensure_safe_output_path(sources: Sequence[Path], out: Path, *, overwrite: bool = False) -> None:
    resolved_out = out.resolve()
    for src in sources:
        if src.resolve() == resolved_out:
            raise ValueError(f'refusing to overwrite input file: {out}')
    if out.exists() and not overwrite:
        raise FileExistsError(f'output already exists (pass --overwrite to replace): {out}')


def _overwrite_flag(overwrite: bool) -> str:
    return '-y' if overwrite else '-n'


def _parse_rate(raw: str | None) -> float | None:
    if not raw or raw in ('0/0', 'N/A'):
        return None
    try:
        frac = Fraction(raw)
        return float(frac) if frac > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def probe_streams(path: Path) -> dict[str, Any]:
    proc = run_cmd(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)])
    data = json.loads(proc.stdout or '{}')
    fmt, streams = data.get('format') or {}, data.get('streams') or []
    video = next((s for s in streams if s.get('codec_type') == 'video'), None)
    audio = next((s for s in streams if s.get('codec_type') == 'audio'), None)
    r_fps = _parse_rate(video.get('r_frame_rate')) if video else None
    avg_fps = _parse_rate(video.get('avg_frame_rate')) if video else None
    return {
        'path': str(path),
        'duration': float(fmt['duration']) if fmt.get('duration') else 0.0,
        'size_bytes': int(fmt['size']) if fmt.get('size') else 0,
        'width': int(video['width']) if video and video.get('width') else None,
        'height': int(video['height']) if video and video.get('height') else None,
        'fps': avg_fps or r_fps,
        'video_codec': video.get('codec_name') if video else None,
        'pix_fmt': video.get('pix_fmt') if video else None,
        'audio_codec': audio.get('codec_name') if audio else None,
        'sample_rate': int(audio['sample_rate']) if audio and audio.get('sample_rate') else None,
        'channels': int(audio['channels']) if audio and audio.get('channels') else None,
    }


def check_concat_compatible(metas: Sequence[dict[str, Any]]) -> tuple[bool, list[str]]:
    if len(metas) < 2:
        return False, ['at least 2 inputs are required for concat']
    ref, reasons = metas[0], []
    for idx, cur in enumerate(metas[1:], start=1):
        if (cur.get('width'), cur.get('height')) != (ref.get('width'), ref.get('height')):
            reasons.append(f'input[{idx}] resolution mismatch: {cur.get("width")}x{cur.get("height")}')
        for key in ('video_codec', 'pix_fmt', 'audio_codec', 'sample_rate', 'channels'):
            if cur.get(key) != ref.get(key):
                reasons.append(f'input[{idx}] {key} mismatch: {cur.get(key)} != {ref.get(key)}')
        if ref.get('fps') and cur.get('fps') and abs(cur['fps'] - ref['fps']) > 0.05:
            reasons.append(f'input[{idx}] fps mismatch: {cur["fps"]:.3f} != {ref["fps"]:.3f}')
    return len(reasons) == 0, reasons


def build_trim_command(
    src: Path, out: Path, *, start: float = 0.0, end: float | None = None,
    duration: float | None = None, lossless: bool = True, overwrite: bool = False,
) -> list[str]:
    ensure_safe_output_path([src], out, overwrite=overwrite)
    if start < 0:
        raise ValueError(f'start must be >= 0, got {start}')
    if end is not None and duration is not None:
        raise ValueError('specify either end or duration, not both')
    if end is not None and end <= start:
        raise ValueError(f'end ({end}) must be greater than start ({start})')
    if duration is not None and duration <= 0:
        raise ValueError(f'duration must be > 0, got {duration}')

    cmd = [*FFMPEG_BASE, _overwrite_flag(overwrite)]
    if start > 0:
        cmd += ['-ss', f'{start:g}']
    cmd += ['-i', str(src)]
    if end is not None:
        cmd += ['-to', f'{end - start:g}' if start > 0 else f'{end:g}']
    elif duration is not None:
        cmd += ['-t', f'{duration:g}']
    cmd += ['-c', 'copy', '-avoid_negative_ts', 'make_zero'] if lossless else list(H264_AAC_ARGS)
    return [*cmd, str(out)]


def format_concat_list(inputs: Sequence[Path]) -> str:
    return ''.join(f"file '{str(p.resolve()).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n" for p in inputs)


def build_concat_command(
    inputs: Sequence[Path], out: Path, *, list_path: Path, lossless: bool = True, overwrite: bool = False,
) -> list[str]:
    if len(inputs) < 2:
        raise ValueError('concat requires at least 2 input files')
    ensure_safe_output_path(inputs, out, overwrite=overwrite)
    cmd = [*FFMPEG_BASE, _overwrite_flag(overwrite), '-f', 'concat', '-safe', '0', '-i', str(list_path)]
    cmd += ['-c', 'copy', '-movflags', '+faststart'] if lossless else list(H264_AAC_ARGS)
    return [*cmd, str(out)]


def build_reframe_command(
    src: Path, out: Path, *, width: int = 1080, height: int = 1920, mode: str = 'crop', overwrite: bool = False,
) -> list[str]:
    ensure_safe_output_path([src], out, overwrite=overwrite)
    if width <= 0 or height <= 0 or width % 2 != 0 or height % 2 != 0:
        raise ValueError(f'width and height must be positive even integers, got {width}x{height}')
    if mode not in ('crop', 'blur'):
        raise ValueError(f'unknown reframe mode "{mode}"; expected "crop" or "blur"')

    cmd = [*FFMPEG_BASE, _overwrite_flag(overwrite), '-i', str(src)]
    if mode == 'crop':
        vf = f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}'
        cmd += ['-vf', vf, '-map', '0:v:0', '-map', '0:a?']
    else:
        fc = (
            f'[0:v]split=2[bg][fg];'
            f'[bg]scale={width}:{height}:force_original_aspect_ratio=increase,'
            f'crop={width}:{height},boxblur=20:5[bgb];'
            f'[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[fgs];'
            f'[bgb][fgs]overlay=(W-w)/2:(H-h)/2[vout]'
        )
        cmd += ['-filter_complex', fc, '-map', '[vout]', '-map', '0:a?']
    return [*cmd, *H264_AAC_ARGS, str(out)]


def build_loudnorm_pass1_command(
    src: Path, *, target_i: float = -14.0, target_tp: float = -1.5, target_lra: float = 11.0,
) -> list[str]:
    af = f'loudnorm=I={target_i:g}:TP={target_tp:g}:LRA={target_lra:g}:print_format=json'
    return [*FFMPEG_BASE, '-i', str(src), '-map', '0:a:0', '-vn', '-af', af, '-f', 'null', '-']


def parse_loudnorm_stats(stderr: str) -> dict[str, str]:
    match = re.search(r'\{[^{}]*"input_i"[^{}]*\}', stderr or '', re.S)
    if not match:
        raise ValueError('failed to find loudnorm JSON block in ffmpeg stderr')
    raw = json.loads(match.group(0))
    return {
        'measured_I': str(raw['input_i']), 'measured_TP': str(raw['input_tp']),
        'measured_LRA': str(raw['input_lra']), 'measured_thresh': str(raw['input_thresh']),
        'offset': str(raw['target_offset']),
    }


def build_loudnorm_pass2_command(
    src: Path, out: Path, stats: dict[str, str], *, target_i: float = -14.0,
    target_tp: float = -1.5, target_lra: float = 11.0, audio_bitrate: str = '192k', overwrite: bool = False,
) -> list[str]:
    ensure_safe_output_path([src], out, overwrite=overwrite)
    af = (
        f'loudnorm=I={target_i:g}:TP={target_tp:g}:LRA={target_lra:g}'
        f':measured_I={stats["measured_I"]}:measured_TP={stats["measured_TP"]}'
        f':measured_LRA={stats["measured_LRA"]}:measured_thresh={stats["measured_thresh"]}'
        f':offset={stats["offset"]}:linear=true'
    )
    return [
        *FFMPEG_BASE, _overwrite_flag(overwrite), '-i', str(src), '-map', '0:v?', '-map', '0:a:0',
        '-c:v', 'copy', '-af', af, '-c:a', 'aac', '-b:a', audio_bitrate, '-ar', '48000',
        '-movflags', '+faststart', str(out),
    ]


def normalize_loudness(
    src: Path, out: Path, *, target_i: float = -14.0, target_tp: float = -1.5,
    target_lra: float = 11.0, overwrite: bool = False, dry_run: bool = False,
) -> dict[str, Any]:
    ensure_safe_output_path([src], out, overwrite=overwrite)
    pass1 = build_loudnorm_pass1_command(src, target_i=target_i, target_tp=target_tp, target_lra=target_lra)
    if dry_run:
        return {'dry_run': True, 'output': str(out), 'pass1_command': pass1}
    stats = parse_loudnorm_stats(run_cmd(pass1, check=False).stderr or '')
    pass2 = build_loudnorm_pass2_command(
        src, out, stats, target_i=target_i, target_tp=target_tp, target_lra=target_lra, overwrite=overwrite
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    run_cmd(pass2)
    return {'dry_run': False, 'output': str(out), 'measured': stats, 'pass2_command': pass2}


def build_duck_bgm_command(
    voice_video: Path, bgm_audio: Path, out: Path, *, bgm_volume: float = 0.35, threshold: float = 0.04,
    ratio: float = 8.0, attack_ms: float = 15.0, release_ms: float = 350.0,
    fade_out_start: float | None = None, fade_out_duration: float = 2.0,
    target_i: float = -14.0, target_tp: float = -1.5, target_lra: float = 11.0, overwrite: bool = False,
) -> list[str]:
    ensure_safe_output_path([voice_video, bgm_audio], out, overwrite=overwrite)
    if bgm_volume <= 0:
        raise ValueError(f'bgm_volume must be > 0, got {bgm_volume}')
    if ratio < 1.0:
        raise ValueError(f'ratio must be >= 1.0, got {ratio}')
    if fade_out_start is not None and (fade_out_start < 0 or fade_out_duration <= 0):
        raise ValueError('fade_out_start must be >= 0 and fade_out_duration > 0')

    bgm_chain = f'[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={bgm_volume:g}'
    if fade_out_start is not None:
        bgm_chain += f',afade=t=out:st={fade_out_start:g}:d={fade_out_duration:g}'
    fc = ';'.join([
        f'{bgm_chain}[m]',
        '[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[v1][v2]',
        f'[m][v2]sidechaincompress=threshold={threshold:g}:ratio={ratio:g}:attack={attack_ms:g}:release={release_ms:g}[mc]',
        '[mc][v1]amix=inputs=2:weights=1 1:normalize=0[s]',
        f'[s]loudnorm=I={target_i:g}:TP={target_tp:g}:LRA={target_lra:g}[out]',
    ])
    return [
        *FFMPEG_BASE, _overwrite_flag(overwrite), '-i', str(voice_video), '-stream_loop', '-1', '-i', str(bgm_audio),
        '-filter_complex', fc, '-map', '0:v', '-map', '[out]', '-c:v', 'copy',
        '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-shortest', '-movflags', '+faststart', str(out),
    ]


def build_export_command(
    src: Path, out: Path, *, preset: str = 'youtube_1080p', reframe_mode: str = 'crop', overwrite: bool = False,
) -> list[str]:
    if preset not in EXPORT_PRESETS:
        raise ValueError(f'unknown preset "{preset}"; expected one of {sorted(EXPORT_PRESETS)}')
    spec = EXPORT_PRESETS[preset]
    if preset == 'shorts_9x16':
        return build_reframe_command(
            src, out, width=spec['width'], height=spec['height'], mode=reframe_mode, overwrite=overwrite
        )
    ensure_safe_output_path([src], out, overwrite=overwrite)
    vf = (
        f'scale={spec["width"]}:{spec["height"]}:force_original_aspect_ratio=decrease,'
        f'pad={spec["width"]}:{spec["height"]}:(ow-iw)/2:(oh-ih)/2'
    )
    return [
        *FFMPEG_BASE, _overwrite_flag(overwrite), '-i', str(src), '-vf', vf, '-map', '0:v:0', '-map', '0:a?',
        '-c:v', spec['video_codec'], '-crf', str(spec['crf']), '-preset', spec['preset'],
        '-pix_fmt', spec['pix_fmt'], '-c:a', spec['audio_codec'], '-b:a', spec['audio_bitrate'],
        '-ar', str(spec['sample_rate']), '-movflags', '+faststart', str(out),
    ]


def _execute_or_plan(cmd: list[str], out: Path, *, dry_run: bool) -> dict[str, Any]:
    if not dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        run_cmd(cmd)
    return {'dry_run': dry_run, 'output': str(out), 'command': cmd}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Typed, safe FFmpeg operations for geo-video-factory.')
    sub = parser.add_subparsers(dest='cmd', required=True)

    def add_out(p: argparse.ArgumentParser) -> None:
        p.add_argument('-o', '--output', type=Path, required=True)
        p.add_argument('--overwrite', action='store_true')
        p.add_argument('--dry-run', action='store_true')
        p.add_argument('--json', action='store_true', dest='as_json')

    p_probe = sub.add_parser('probe')
    p_probe.add_argument('input', type=Path)
    p_probe.add_argument('--json', action='store_true', dest='as_json')

    p_trim = sub.add_parser('trim')
    p_trim.add_argument('input', type=Path)
    p_trim.add_argument('--start', type=float, default=0.0)
    p_trim.add_argument('--end', type=float, default=None)
    p_trim.add_argument('--duration', type=float, default=None)
    p_trim.add_argument('--reencode', action='store_true')
    add_out(p_trim)

    p_concat = sub.add_parser('concat')
    p_concat.add_argument('inputs', type=Path, nargs='+')
    p_concat.add_argument('--reencode', action='store_true')
    add_out(p_concat)

    p_ref = sub.add_parser('reframe')
    p_ref.add_argument('input', type=Path)
    p_ref.add_argument('--mode', choices=('crop', 'blur'), default='crop')
    add_out(p_ref)

    p_ln = sub.add_parser('loudnorm')
    p_ln.add_argument('input', type=Path)
    p_ln.add_argument('-I', '--target-i', type=float, default=-14.0)
    p_ln.add_argument('--tp', type=float, default=-1.5)
    p_ln.add_argument('--lra', type=float, default=11.0)
    add_out(p_ln)

    p_duck = sub.add_parser('duck-bgm')
    p_duck.add_argument('voice_video', type=Path)
    p_duck.add_argument('bgm_audio', type=Path)
    p_duck.add_argument('--volume', type=float, default=0.35)
    p_duck.add_argument('--threshold', type=float, default=0.04)
    p_duck.add_argument('--ratio', type=float, default=8.0)
    p_duck.add_argument('--fade-out-start', type=float, default=None)
    p_duck.add_argument('--fade-out-duration', type=float, default=2.0)
    add_out(p_duck)

    p_exp = sub.add_parser('export')
    p_exp.add_argument('input', type=Path)
    p_exp.add_argument('--preset', choices=sorted(EXPORT_PRESETS), default='youtube_1080p')
    p_exp.add_argument('--reframe-mode', choices=('crop', 'blur'), default='crop')
    add_out(p_exp)
    return parser


def run_cli(argv: list[str] | None = None) -> tuple[int, str]:
    args = _build_parser().parse_args(argv)
    if args.cmd == 'probe':
        res: dict[str, Any] = probe_streams(args.input)
    elif args.cmd == 'trim':
        cmd = build_trim_command(
            args.input, args.output, start=args.start, end=args.end,
            duration=args.duration, lossless=not args.reencode, overwrite=args.overwrite,
        )
        res = _execute_or_plan(cmd, args.output, dry_run=args.dry_run)
    elif args.cmd == 'concat':
        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8') as tf:
            tf.write(format_concat_list(args.inputs))
            list_path = Path(tf.name)
        try:
            cmd = build_concat_command(
                args.inputs, args.output, list_path=list_path,
                lossless=not args.reencode, overwrite=args.overwrite,
            )
            res = _execute_or_plan(cmd, args.output, dry_run=args.dry_run)
        finally:
            list_path.unlink(missing_ok=True)
    elif args.cmd == 'reframe':
        res = _execute_or_plan(
            build_reframe_command(args.input, args.output, mode=args.mode, overwrite=args.overwrite),
            args.output, dry_run=args.dry_run,
        )
    elif args.cmd == 'loudnorm':
        res = normalize_loudness(
            args.input, args.output, target_i=args.target_i, target_tp=args.tp,
            target_lra=args.lra, overwrite=args.overwrite, dry_run=args.dry_run,
        )
    elif args.cmd == 'duck-bgm':
        cmd = build_duck_bgm_command(
            args.voice_video, args.bgm_audio, args.output, bgm_volume=args.volume,
            threshold=args.threshold, ratio=args.ratio, fade_out_start=args.fade_out_start,
            fade_out_duration=args.fade_out_duration, overwrite=args.overwrite,
        )
        res = _execute_or_plan(cmd, args.output, dry_run=args.dry_run)
    else:
        cmd = build_export_command(
            args.input, args.output, preset=args.preset,
            reframe_mode=args.reframe_mode, overwrite=args.overwrite,
        )
        res = _execute_or_plan(cmd, args.output, dry_run=args.dry_run)

    text = json.dumps(res, ensure_ascii=False, indent=2) if args.as_json else str(res.get('output', res))
    return 0, text


if __name__ == '__main__':
    code, out_text = run_cli()
    print(out_text)
    sys.exit(code)
