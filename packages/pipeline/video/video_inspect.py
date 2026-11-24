"""FFmpeg-backed adaptive storyboard, zoom, and full-frame inspection CLI."""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
if str(_Path(__file__).resolve().parents[1]) not in _sys.path:
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Any

from PIL import Image

try:
    from video.storyboard import (
        TILES_PER_SHEET,
        choose_grid,
        compose_storyboard,
        format_time,
        format_timeline,
        parse_crop,
        parse_time,
        select_keyframes,
    )
except ImportError:
    from packages.pipeline.video.storyboard import (
        TILES_PER_SHEET,
        choose_grid,
        compose_storyboard,
        format_time,
        format_timeline,
        parse_crop,
        parse_time,
        select_keyframes,
    )

MAX_ZOOM_FRAMES = 48
MAX_FRAME_EDGE = 2000


def _probe_video(path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
         'stream=width,height,r_frame_rate,avg_frame_rate:format=duration', '-of', 'json', str(path)],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(proc.stdout or '{}')
    stream = (data.get('streams') or [{}])[0]
    fmt = data.get('format') or {}
    w, h = int(stream['width']), int(stream['height'])
    dur = float(fmt.get('duration') or 0.0)
    raw_fps = stream.get('avg_frame_rate') or stream.get('r_frame_rate') or '30/1'
    num, _, den = raw_fps.partition('/')
    fps = float(num) / float(den) if den and float(den) > 0 else float(num)
    return {'width': w, 'height': h, 'duration': dur, 'fps': fps}


def _sample_signatures(
    path: Path,
    *,
    start: float,
    end: float,
    sample_fps: float,
    sig_width: int,
    aspect: float,
) -> tuple[list[bytes], list[float]]:
    sig_h = max(2, int(round(sig_width / aspect / 2)) * 2)
    frame_bytes = sig_width * sig_h
    cmd = [
        'ffmpeg', '-hide_banner', '-nostdin', '-ss', f'{start:.3f}', '-to', f'{end:.3f}',
        '-i', str(path), '-an', '-vf', f'fps={sample_fps:.4f},scale={sig_width}:{sig_h},format=gray',
        '-f', 'rawvideo', '-',
    ]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    raw = proc.stdout
    count = len(raw) // frame_bytes
    sigs = [raw[i * frame_bytes:(i + 1) * frame_bytes] for i in range(count)]
    times = [start + i / sample_fps for i in range(count)]
    return sigs, times


def _crop_filter(w: int, h: int, crop: tuple[float, float, float, float] | None) -> list[str]:
    if not crop:
        return []
    cx, cy, cw, ch = crop
    return [f'crop={max(2, int(w * cw))}:{max(2, int(h * ch))}:{int(w * cx)}:{int(h * cy)}']


def _extract_frame_image(
    path: Path,
    t: float,
    *,
    out_w: int,
    out_h: int,
    src_w: int,
    src_h: int,
    crop: tuple[float, float, float, float] | None = None,
) -> Image.Image:
    vf = _crop_filter(src_w, src_h, crop) + [f'scale={out_w}:{out_h}']
    cmd = [
        'ffmpeg', '-hide_banner', '-nostdin', '-ss', f'{t:.3f}', '-i', str(path),
        '-frames:v', '1', '-vf', ','.join(vf), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-',
    ]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    return Image.frombytes('RGB', (out_w, out_h), proc.stdout)


def build_adaptive_storyboard(
    video_path: Path,
    out_path: Path,
    *,
    budget: int = 16,
    start: float = 0.0,
    end: float | None = None,
    timeline_path: Path | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    info = _probe_video(video_path)
    dur = info['duration']
    span_end = min(dur, end) if end is not None else dur
    span = max(0.1, span_end - start)
    sample_fps = min(8.0, 2400.0 / span)
    aspect = info['width'] / info['height']
    sigs, times = _sample_signatures(video_path, start=start, end=span_end, sample_fps=sample_fps, sig_width=128, aspect=aspect)
    selected = select_keyframes(sigs, budget=budget)
    if not selected:
        raise RuntimeError(f'no frames sampled from {video_path}')

    with_hours = dur >= 3600
    outputs: list[str] = []
    for s_idx in range(0, len(selected), TILES_PER_SHEET):
        chunk = selected[s_idx:s_idx + TILES_PER_SHEET]
        layout = choose_grid(aspect, count=len(chunk))
        tiles = [
            (
                _extract_frame_image(video_path, times[sf.index], out_w=layout.tile_w, out_h=layout.tile_h, src_w=info['width'], src_h=info['height']),
                f'#{s_idx + j + 1} {format_time(times[sf.index], 1, with_hours)}',
            )
            for j, sf in enumerate(chunk)
        ]
        target = out_path if len(selected) <= TILES_PER_SHEET else out_path.with_name(f'{out_path.stem}_{s_idx // TILES_PER_SHEET + 1:02d}{out_path.suffix}')
        compose_storyboard(tiles, layout, target, overwrite=overwrite)
        outputs.append(str(target))

    tl_text = format_timeline(selected, times)
    if timeline_path:
        timeline_path.parent.mkdir(parents=True, exist_ok=True)
        timeline_path.write_text(tl_text + '\n', encoding='utf-8')
    return {'outputs': outputs, 'keyframes': len(selected), 'timeline': tl_text, 'timestamps': [round(times[s.index], 2) for s in selected]}


def zoom_segment(
    video_path: Path,
    out_path: Path,
    *,
    start: float,
    end: float,
    fps: float | None = None,
    crop: tuple[float, float, float, float] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    info = _probe_video(video_path)
    end = min(info['duration'], end)
    span = max(0.05, end - start)
    cap_fps = MAX_ZOOM_FRAMES / span
    eff_fps = max(0.1, min(fps if fps and fps > 0 else min(info['fps'], cap_fps), info['fps'], cap_fps))
    count = min(MAX_ZOOM_FRAMES, max(1, int(math.floor(span * eff_fps)) + 1))
    cw = crop[2] if crop else 1.0
    ch = crop[3] if crop else 1.0
    aspect = (info['width'] * cw) / (info['height'] * ch)
    with_hours = info['duration'] >= 3600

    outputs: list[str] = []
    for s_idx in range(0, count, TILES_PER_SHEET):
        n_chunk = min(TILES_PER_SHEET, count - s_idx)
        layout = choose_grid(aspect, count=n_chunk)
        tiles = []
        for j in range(n_chunk):
            idx = s_idx + j
            t = min(end, start + idx / eff_fps)
            img = _extract_frame_image(video_path, t, out_w=layout.tile_w, out_h=layout.tile_h, src_w=info['width'], src_h=info['height'], crop=crop)
            tiles.append((img, f'#{idx + 1} {format_time(t, 2, with_hours)}'))
        target = out_path if count <= TILES_PER_SHEET else out_path.with_name(f'{out_path.stem}_{s_idx // TILES_PER_SHEET + 1:02d}{out_path.suffix}')
        compose_storyboard(tiles, layout, target, overwrite=overwrite)
        outputs.append(str(target))
    return {'outputs': outputs, 'frames': count, 'fps': round(eff_fps, 2), 'start': start, 'end': end}


def extract_frame(
    video_path: Path,
    out_path: Path,
    *,
    t: float,
    crop: tuple[float, float, float, float] | None = None,
    max_edge: int = MAX_FRAME_EDGE,
    overwrite: bool = False,
) -> dict[str, Any]:
    if out_path.exists() and not overwrite:
        raise FileExistsError(f'output already exists: {out_path}')
    info = _probe_video(video_path)
    src_w = int(info['width'] * (crop[2] if crop else 1.0))
    src_h = int(info['height'] * (crop[3] if crop else 1.0))
    scale = min(1.0, max_edge / max(src_w, src_h))
    out_w = max(2, int((src_w * scale) // 2) * 2)
    out_h = max(2, int((src_h * scale) // 2) * 2)
    img = _extract_frame_image(video_path, t, out_w=out_w, out_h=out_h, src_w=info['width'], src_h=info['height'], crop=crop)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, quality=95)
    return {'output': str(out_path), 'width': out_w, 'height': out_h, 't': t}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Adaptive storyboard, zoom, and frame inspection.')
    sub = ap.add_subparsers(dest='cmd', required=True)

    sb = sub.add_parser('storyboard')
    sb.add_argument('video', type=Path)
    sb.add_argument('--out', type=Path, required=True)
    sb.add_argument('--budget', type=int, default=16)
    sb.add_argument('--start', default='0')
    sb.add_argument('--end', default=None)
    sb.add_argument('--timeline', type=Path, default=None)
    sb.add_argument('--overwrite', action='store_true')
    sb.add_argument('--json', action='store_true')

    zm = sub.add_parser('zoom')
    zm.add_argument('video', type=Path)
    zm.add_argument('--start', required=True)
    zm.add_argument('--end', required=True)
    zm.add_argument('--out', type=Path, required=True)
    zm.add_argument('--fps', type=float, default=None)
    zm.add_argument('--crop', default=None)
    zm.add_argument('--overwrite', action='store_true')
    zm.add_argument('--json', action='store_true')

    fr = sub.add_parser('frame')
    fr.add_argument('video', type=Path)
    fr.add_argument('--t', required=True)
    fr.add_argument('--out', type=Path, required=True)
    fr.add_argument('--crop', default=None)
    fr.add_argument('--max-edge', type=int, default=MAX_FRAME_EDGE)
    fr.add_argument('--overwrite', action='store_true')
    fr.add_argument('--json', action='store_true')

    args = ap.parse_args(argv)
    if args.cmd == 'storyboard':
        res = build_adaptive_storyboard(args.video, args.out, budget=args.budget, start=parse_time(args.start), end=parse_time(args.end) if args.end else None, timeline_path=args.timeline, overwrite=args.overwrite)
    elif args.cmd == 'zoom':
        res = zoom_segment(args.video, args.out, start=parse_time(args.start), end=parse_time(args.end), fps=args.fps, crop=parse_crop(args.crop), overwrite=args.overwrite)
    else:
        res = extract_frame(args.video, args.out, t=parse_time(args.t), crop=parse_crop(args.crop), max_edge=args.max_edge, overwrite=args.overwrite)
    print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else res.get('timeline', json.dumps(res, ensure_ascii=False)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
