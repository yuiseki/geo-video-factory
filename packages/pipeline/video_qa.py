"""Automated post-render QA for finished episode MP4 files.

Provides platform compliance checks (ffprobe + loudnorm), content anomaly
detection (black/freeze/silence), and uniform-interval contact sheet generation
with burned-in timecodes and optional platform safe-zone guides.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

PLATFORMS: dict[str, dict[str, Any]] = {
    'youtube': {
        'aspects': [(16, 9)],
        'min_height': 1080,
        'fps_min': 24.0,
        'fps_max': 60.0,
        'codecs': ('h264', 'hevc', 'av1'),
        'pix_fmts': ('yuv420p',),
        'lufs': -14.0,
        'lufs_tol': 2.0,
        'tp': -1.0,
        'tp_tol': 0.1,
        'max_duration': 43200.0,
        'safe': {'top': 0.05, 'bottom': 0.05, 'left': 0.05, 'right': 0.05},
    },
    'shorts': {
        'aspects': [(9, 16), (1, 1)],
        'min_height': 1080,
        'fps_min': 24.0,
        'fps_max': 60.0,
        'codecs': ('h264', 'hevc'),
        'pix_fmts': ('yuv420p',),
        'lufs': -14.0,
        'lufs_tol': 2.0,
        'tp': -1.0,
        'tp_tol': 0.1,
        'max_duration': 180.0,
        'safe': {'top': 0.12, 'bottom': 0.25, 'left': 0.05, 'right': 0.15},
    },
}


def run_cmd(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=True, text=True)


def has_ffmpeg_filter(name: str) -> bool:
    proc = run_cmd(['ffmpeg', '-hide_banner', '-filters'], check=False)
    pattern = re.compile(rf'^\s*[T.][S.][C.]\s+{re.escape(name)}\b', re.M)
    return bool(pattern.search(proc.stdout or ''))


def parse_tiles(value: str) -> tuple[int, int]:
    match = re.fullmatch(r'(\d+)x(\d+)', value.strip())
    if not match:
        raise ValueError(f'invalid tiles "{value}"; expected COLSxROWS (e.g. 4x3)')
    cols, rows = int(match.group(1)), int(match.group(2))
    if cols <= 0 or rows <= 0:
        raise ValueError(f'invalid tiles "{value}"; cols and rows must be positive')
    return cols, rows


def ensure_safe_output_path(src: Path, out: Path, *, overwrite: bool = False) -> None:
    if src.resolve() == out.resolve():
        raise ValueError(f'refusing to overwrite input file: {out}')
    if out.exists() and not overwrite:
        raise FileExistsError(f'output already exists (pass --overwrite to replace): {out}')


def _parse_rate(raw: str | None) -> float | None:
    if not raw or raw in ('0/0', 'N/A'):
        return None
    try:
        frac = Fraction(raw)
        return float(frac) if frac > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def probe_media(path: Path) -> dict[str, Any]:
    proc = run_cmd([
        'ffprobe', '-v', 'error', '-show_format', '-show_streams',
        '-of', 'json', str(path),
    ])
    data = json.loads(proc.stdout or '{}')
    fmt = data.get('format') or {}
    streams = data.get('streams') or []
    video = next((s for s in streams if s.get('codec_type') == 'video'), None)
    audio = next((s for s in streams if s.get('codec_type') == 'audio'), None)

    r_fps = _parse_rate(video.get('r_frame_rate')) if video else None
    avg_fps = _parse_rate(video.get('avg_frame_rate')) if video else None
    fps = avg_fps or r_fps
    vfr = bool(r_fps and avg_fps and abs(r_fps - avg_fps) / max(r_fps, avg_fps) > 0.05)

    return {
        'duration': float(fmt['duration']) if fmt.get('duration') else 0.0,
        'size_bytes': int(fmt['size']) if fmt.get('size') else 0,
        'width': int(video['width']) if video and video.get('width') else None,
        'height': int(video['height']) if video and video.get('height') else None,
        'fps': fps,
        'vfr_suspected': vfr,
        'video_codec': video.get('codec_name') if video else None,
        'pix_fmt': video.get('pix_fmt') if video else None,
        'audio_codec': audio.get('codec_name') if audio else None,
        'sample_rate': int(audio['sample_rate']) if audio and audio.get('sample_rate') else None,
        'channels': int(audio['channels']) if audio and audio.get('channels') else None,
    }


def measure_loudness(path: Path) -> dict[str, float]:
    proc = run_cmd(
        [
            'ffmpeg', '-hide_banner', '-nostdin', '-i', str(path),
            '-map', '0:a:0', '-vn',
            '-af', 'loudnorm=I=-14:TP=-1:LRA=11:print_format=json',
            '-f', 'null', '-',
        ],
        check=False,
    )
    match = re.search(r'\{[^{}]*"input_i"[^{}]*\}', proc.stderr or '', re.S)
    if not match:
        return {}
    try:
        raw = json.loads(match.group(0))
        return {
            'lufs': float(raw['input_i']),
            'tp': float(raw['input_tp']),
            'lra': float(raw['input_lra']),
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        return {}


def _row(name: str, status: str, actual: Any, expected: Any, message: str = '') -> dict[str, Any]:
    return {'name': name, 'status': status, 'actual': actual, 'expected': expected, 'message': message}


def _aspect_matches(width: int, height: int, allowed: list[tuple[int, int]]) -> bool:
    ratio = Fraction(width, height)
    return any(abs(float(ratio) - (w / h)) <= 0.02 for w, h in allowed)


def evaluate_compliance(
    meta: dict[str, Any],
    loudness: dict[str, float],
    *,
    platform: str = 'youtube',
) -> dict[str, Any]:
    if platform not in PLATFORMS:
        raise ValueError(f'unknown platform "{platform}"; expected one of {sorted(PLATFORMS)}')
    spec = PLATFORMS[platform]
    rows: list[dict[str, Any]] = []

    w, h = meta.get('width'), meta.get('height')
    if w and h:
        aspect_ok = _aspect_matches(w, h, spec['aspects'])
        rows.append(_row('aspect', 'PASS' if aspect_ok else 'FAIL', f'{w}x{h}', spec['aspects']))
        rows.append(_row('resolution', 'PASS' if h >= spec['min_height'] else 'FAIL', h, f'>={spec["min_height"]}'))
    else:
        rows.append(_row('video_stream', 'FAIL', None, 'video stream required'))

    v_codec = meta.get('video_codec')
    rows.append(_row('video_codec', 'PASS' if v_codec in spec['codecs'] else 'FAIL', v_codec, list(spec['codecs'])))

    pix_fmt = meta.get('pix_fmt')
    rows.append(_row('pix_fmt', 'PASS' if pix_fmt in spec['pix_fmts'] else 'FAIL', pix_fmt, list(spec['pix_fmts'])))

    fps = meta.get('fps')
    fps_ok = fps is not None and spec['fps_min'] <= fps <= spec['fps_max']
    rows.append(_row('fps', 'PASS' if fps_ok else 'FAIL', fps, f'{spec["fps_min"]}..{spec["fps_max"]}'))
    rows.append(_row('vfr', 'WARN' if meta.get('vfr_suspected') else 'PASS', meta.get('vfr_suspected'), False))

    dur = meta.get('duration', 0.0)
    rows.append(_row('duration', 'WARN' if dur > spec['max_duration'] else 'PASS', dur, f'<={spec["max_duration"]}s'))

    if not meta.get('audio_codec'):
        rows.append(_row('audio_stream', 'FAIL', None, 'audio stream required'))
    elif loudness:
        lufs, tp = loudness['lufs'], loudness['tp']
        lufs_ok = abs(lufs - spec['lufs']) <= spec['lufs_tol']
        tp_ok = tp <= spec['tp'] + spec['tp_tol']
        rows.append(_row('loudness', 'PASS' if lufs_ok else 'FAIL', lufs, f'{spec["lufs"]} +/- {spec["lufs_tol"]} LUFS'))
        rows.append(_row('true_peak', 'PASS' if tp_ok else 'FAIL', tp, f'<={spec["tp"]} dBTP (+{spec["tp_tol"]})'))
    else:
        rows.append(_row('loudness', 'WARN', None, f'{spec["lufs"]} LUFS', 'loudnorm measurement unavailable'))

    ok = all(r['status'] != 'FAIL' for r in rows)
    return {'platform': platform, 'ok': ok, 'rows': rows}


def _status_by_threshold(value: float, warn: float, fail: float) -> str:
    if value >= fail:
        return 'FAIL'
    if value > warn:
        return 'WARN'
    return 'PASS'


def detect_content_anomalies(path: Path, *, duration: float) -> list[dict[str, Any]]:
    vf = 'blackdetect=d=0.5:pix_th=0.10,freezedetect=n=-60dB:d=1.0'
    af = 'silencedetect=noise=-50dB:d=0.5'
    proc = run_cmd(
        ['ffmpeg', '-hide_banner', '-nostdin', '-i', str(path), '-vf', vf, '-af', af, '-f', 'null', '-'],
        check=False,
    )
    stderr = proc.stderr or ''
    total_dur = max(duration, 0.001)

    black_total = sum(float(m) for m in re.findall(r'black_duration:([0-9.]+)', stderr))
    freeze_durs = [float(m) for m in re.findall(r'freeze_duration:\s*([0-9.]+)', stderr)]
    silence_total = sum(float(m) for m in re.findall(r'silence_duration:\s*([0-9.]+)', stderr))

    black_share = min(1.0, black_total / total_dur)
    freeze_max = max(freeze_durs) if freeze_durs else 0.0
    freeze_share = min(1.0, freeze_max / total_dur)
    silence_share = min(1.0, silence_total / total_dur)

    freeze_status = (
        'FAIL' if freeze_share >= 0.95
        else 'WARN' if freeze_max > max(3.0, 0.30 * total_dur)
        else 'PASS'
    )

    return [
        {
            'name': 'black',
            'status': _status_by_threshold(black_share, 0.10, 0.95),
            'actual_share': round(black_share, 4),
            'seconds': round(black_total, 2),
        },
        {
            'name': 'frozen',
            'status': freeze_status,
            'max_seconds': round(freeze_max, 2),
            'actual_share': round(freeze_share, 4),
        },
        {
            'name': 'silence',
            'status': _status_by_threshold(silence_share, 0.50, 0.95),
            'actual_share': round(silence_share, 4),
            'seconds': round(silence_total, 2),
        },
    ]


def _safe_zone_boxes(platform: str) -> list[str]:
    safe = PLATFORMS[platform]['safe']
    boxes: list[str] = []
    if safe['top'] > 0:
        boxes.append(f'drawbox=x=0:y=0:w=iw:h=ih*{safe["top"]:g}:color=red@0.25:t=fill')
    if safe['bottom'] > 0:
        boxes.append(f'drawbox=x=0:y=ih*(1-{safe["bottom"]:g}):w=iw:h=ih*{safe["bottom"]:g}:color=red@0.25:t=fill')
    if safe['left'] > 0:
        boxes.append(f'drawbox=x=0:y=0:w=iw*{safe["left"]:g}:h=ih:color=red@0.25:t=fill')
    if safe['right'] > 0:
        boxes.append(f'drawbox=x=iw*(1-{safe["right"]:g}):y=0:w=iw*{safe["right"]:g}:h=ih:color=red@0.25:t=fill')
    return boxes


def build_contact_sheet(
    src: Path,
    out: Path,
    *,
    duration: float,
    tiles: tuple[int, int] = (4, 3),
    tile_width: int = 480,
    safe: str | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    ensure_safe_output_path(src, out, overwrite=overwrite)
    if safe is not None and safe not in PLATFORMS:
        raise ValueError(f'unknown safe platform "{safe}"')
    cols, rows = tiles
    total_tiles = cols * rows
    safe_dur = max(duration, 1.0)
    use_drawtext = False if dry_run else has_ffmpeg_filter('drawtext')
    filters = [
        f'fps={total_tiles}/{safe_dur:.3f}',
        f'scale={tile_width}:-1',
    ]
    if use_drawtext:
        filters.append(
            "pad=iw:ih+28:0:28:black,"
            "drawtext=text='%{pts\\:hms}':fontcolor=white:fontsize=20:x=8:y=4"
        )
    if safe:
        filters.extend(_safe_zone_boxes(safe))
    filters.append(f'tile={cols}x{rows}')

    cmd = [
        'ffmpeg', '-hide_banner', '-nostdin',
        '-y' if overwrite else '-n',
        '-i', str(src),
        '-vf', ','.join(filters),
        '-frames:v', '1',
        str(out),
    ]
    result: dict[str, Any] = {
        'output': str(out),
        'tiles': f'{cols}x{rows}',
        'safe': safe,
        'timecode_mode': 'drawtext' if use_drawtext else 'none',
        'command': cmd,
        'dry_run': dry_run,
    }
    if not dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        run_cmd(cmd)
    return result


def run_cli(argv: list[str] | None = None) -> tuple[int, str]:
    parser = argparse.ArgumentParser(description='QA checks and contact sheet generator for rendered videos.')
    parser.add_argument('input', type=Path)
    parser.add_argument('--platform', choices=sorted(PLATFORMS), default='youtube')
    parser.add_argument('--content', action='store_true', help='Detect black, frozen, and silent spans')
    parser.add_argument('--contact', type=Path, default=None, help='Output path for contact sheet PNG')
    parser.add_argument('--storyboard', type=Path, default=None, help='Output path for adaptive storyboard JPG')
    parser.add_argument('--storyboard-budget', type=int, default=16, help='Max keyframes for adaptive storyboard')
    parser.add_argument('--tiles', default='4x3', help='Contact sheet grid COLSxROWS (default: 4x3)')
    parser.add_argument('--safe', choices=sorted(PLATFORMS), default=None, help='Overlay platform UI safe zones')
    parser.add_argument('--overwrite', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--json', action='store_true', dest='as_json')
    args = parser.parse_args(argv)

    if args.dry_run:
        plan: dict[str, Any] = {'dry_run': True, 'input': str(args.input), 'platform': args.platform}
        if args.contact:
            plan['contact'] = build_contact_sheet(
                args.input, args.contact, duration=60.0, tiles=parse_tiles(args.tiles),
                safe=args.safe, overwrite=args.overwrite, dry_run=True,
            )
        return 0, json.dumps(plan, ensure_ascii=False, indent=2)

    meta = probe_media(args.input)
    loudness = measure_loudness(args.input) if meta.get('audio_codec') else {}
    compliance = evaluate_compliance(meta, loudness, platform=args.platform)
    report: dict[str, Any] = {'input': str(args.input), 'probe': meta, 'loudness': loudness, 'compliance': compliance}

    ok = compliance['ok']
    if args.content:
        anomalies = detect_content_anomalies(args.input, duration=meta['duration'])
        report['content'] = anomalies
        ok = ok and all(r['status'] != 'FAIL' for r in anomalies)
    if args.contact:
        report['contact'] = build_contact_sheet(
            args.input, args.contact, duration=meta['duration'],
            tiles=parse_tiles(args.tiles), safe=args.safe, overwrite=args.overwrite,
        )
    if args.storyboard:
        try:
            from video_inspect import build_adaptive_storyboard
        except ImportError:
            from packages.pipeline.video_inspect import build_adaptive_storyboard
        report['storyboard'] = build_adaptive_storyboard(
            args.input, args.storyboard, budget=args.storyboard_budget,
            timeline_path=args.storyboard.with_suffix('.timeline.txt'), overwrite=args.overwrite,
        )

    report['ok'] = ok
    text = json.dumps(report, ensure_ascii=False, indent=2) if args.as_json else (
        f'{args.input}: {"PASS" if ok else "FAIL"} ({args.platform}, {meta["duration"]:.2f}s)'
    )
    return (0 if ok else 1), text


if __name__ == '__main__':
    code, output = run_cli()
    print(output)
    sys.exit(code)
