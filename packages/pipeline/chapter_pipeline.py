"""Render independent narrated chapters from a JSON manifest and join them.

Invoke from anywhere against a project's chapters.json. Uses the shared
TypeScript renderer in packages/renderer/dist/src/render.js with --project.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER_ENTRY = REPO_ROOT / 'packages' / 'renderer' / 'dist' / 'src' / 'render.js'
FONT_CANDIDATES = (
    Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'),
    Path('/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc'),
    Path('/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc'),
    Path('C:/Windows/Fonts/NotoSansJP-Bold.ttf'),
    Path('C:/Windows/Fonts/BIZ-UDGothicB.ttc'),
    Path('C:/Windows/Fonts/meiryob.ttc'),
    Path('C:/Windows/Fonts/YuGothB.ttc'),
    Path('C:/Windows/Fonts/msgothic.ttc'),
    Path('/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc'),
    Path('/Library/Fonts/NotoSansCJKjp-Bold.otf'),
)
FPS = 24
SIZE = '1920x1080'
LOUDNORM_KEYS = ('input_i', 'input_tp', 'input_lra', 'input_thresh', 'target_offset')


def find_font(font: str | Path | None = None) -> str:
    if font:
        return str(font)
    for candidate in FONT_CANDIDATES:
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError('no Japanese bold font found; pass --font or set manifest "font"')


def parse_size(value: str) -> tuple[int, int]:
    match = re.fullmatch(r'(\d+)x(\d+)', value)
    if not match:
        raise ValueError(f'invalid size "{value}"; expected WIDTHxHEIGHT')
    width, height = int(match.group(1)), int(match.group(2))
    if width <= 0 or height <= 0:
        raise ValueError(f'invalid size "{value}"; dimensions must be positive integers')
    return width, height


def format_concat_line(path: Path) -> str:
    escaped = path.as_posix().replace("'", "'\\''")
    return f"file '{escaped}'\n"


def can_reuse_chapter(reuse_from: Path | None, ch_id: str, index: int, spec_text: str, rerender: set[str]) -> bool:
    if not reuse_from or ch_id in rerender or str(index) in rerender:
        return False
    prev_job = reuse_from / 'jobs' / ch_id
    prev_mp4 = prev_job / f'{ch_id}.mp4'
    prev_spec = prev_job / 'spec.json'
    return prev_mp4.is_file() and prev_spec.is_file() and prev_spec.read_text(encoding='utf-8') == spec_text


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def duration(path: Path) -> float:
    p = run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
        capture_output=True,
        text=True,
    )
    return float(p.stdout.strip())


def validate_chapter_ids(chapters) -> None:
    if not chapters:
        raise ValueError('manifest must contain chapters')
    names = [chapter['id'] for chapter in chapters]
    if len(names) != len(set(names)):
        raise ValueError('chapter ids must be unique')
    if any(not isinstance(name, str) or not name or not name.replace('-', '').replace('_', '').isalnum() for name in names):
        raise ValueError('chapter ids must be alphanumeric, hyphen or underscore')


def parse_loudnorm(stderr: str) -> str:
    start, end = stderr.rfind('{'), stderr.rfind('}')
    if start < 0 or end <= start:
        raise ValueError('loudnorm measurement did not contain JSON')
    try:
        values = json.loads(stderr[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError('loudnorm measurement contained invalid JSON') from exc
    missing = [key for key in LOUDNORM_KEYS if key not in values]
    if missing:
        raise ValueError(f'loudnorm measurement missing: {", ".join(missing)}')
    return (
        'loudnorm=I=-14:TP=-1.5:LRA=11:'
        f"measured_I={values['input_i']}:measured_TP={values['input_tp']}:"
        f"measured_LRA={values['input_lra']}:measured_thresh={values['input_thresh']}:"
        f"offset={values['target_offset']}:linear=true"
    )


def build_timeline(chapters, chapter_durations, card_durations):
    if len(chapter_durations) != len(chapters) or len(card_durations) != max(0, len(chapters) - 1):
        raise ValueError('duration counts must match chapters')
    durations = [*chapter_durations, *card_durations]
    if any(not isinstance(value, (int, float)) or value < 0 for value in durations):
        raise ValueError('durations must be non-negative numbers')
    cursor = 0.0
    timeline = []
    for index, (chapter, chapter_duration) in enumerate(zip(chapters, chapter_durations)):
        if index:
            cursor += card_durations[index - 1]
        timeline.append({'title': chapter['title'], 'start': cursor})
        cursor += chapter_duration
    return timeline, cursor


def card(
    title: str,
    number: int,
    image: Path,
    video: Path,
    series: str,
    fps: int,
    seconds: float,
    size: tuple[int, int] = (1920, 1080),
    font: str | Path | None = None,
) -> None:
    width, height = size
    sx, sy = width / 1920, height / 1080
    scale = min(sx, sy)
    img = Image.new('RGB', (width, height), '#101c2e')
    draw = ImageDraw.Draw(img)
    font_path = find_font(font)
    small, large = ImageFont.truetype(font_path, max(12, round(36 * scale))), ImageFont.truetype(font_path, max(16, round(72 * scale)))
    if series:
        draw.text((960 * sx, 350 * sy), series, font=small, anchor='mm', fill='#e7b462')
    draw.text((960 * sx, 455 * sy), f'第 {number} 章', font=small, anchor='mm', fill='#d5e0ed')
    draw.text((960 * sx, 560 * sy), title, font=large, anchor='mm', fill='white')
    draw.line((600 * sx, 650 * sy, 1320 * sx, 650 * sy), fill='#e7b462', width=max(1, round(4 * scale)))
    img.save(image)
    run(
        [
            'ffmpeg', '-nostdin', '-v', 'error', '-n', '-loop', '1', '-framerate', str(fps),
            '-i', str(image), '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000',
            '-t', str(seconds), '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            '-crf', '18', '-maxrate', '20M', '-bufsize', '40M', '-profile:v', 'high', '-level:v', '4.1',
            '-g', str(fps * 2), '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', str(video),
        ]
    )


def render(item) -> Path:
    if len(item) == 8:
        i, spec, dest, cache, check_overlap, project_root, renderer_entry, opts = item
    else:
        i, spec, dest, cache, check_overlap, project_root, renderer_entry = item
        opts = {}
    fps = opts.get('fps', FPS)
    size = opts.get('size', SIZE)
    no_voice = bool(opts.get('no_voice', False))
    dest.mkdir(parents=True, exist_ok=True)
    if cache:
        shutil.copytree(cache, dest / 'voice-cache', dirs_exist_ok=True)
    if spec.is_file():
        (dest / 'spec.json').write_text(spec.read_text(encoding='utf-8'), encoding='utf-8')
    log = dest.parent / f'{dest.name}.log'
    with log.open('x', encoding='utf-8') as stream:
        cmd = [
            'node', str(renderer_entry), str(spec),
            '--project', str(project_root),
            '--out', str(dest),
            '--size', str(size),
            '--fps', str(fps),
            '--raw-audio',
        ]
        if no_voice:
            cmd.append('--no-voice')
        if check_overlap:
            cmd.append('--check-label-overlap')
        proc = subprocess.run(cmd, cwd=project_root, stdout=stream, stderr=subprocess.STDOUT)
    lines = log.read_text(errors='replace').replace('\r', '\n').splitlines()
    bad = [line for line in lines if line.startswith(('[http ', '[page]', 'warning:', 'Error:'))]
    if proc.returncode or bad:
        raise RuntimeError(f'chapter {i} failed or logged a rendering error: {log}')
    video = dest / f'{dest.name}.mp4'
    info = json.loads(
        run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type', '-of', 'json', str(video)], capture_output=True, text=True).stdout
    )
    if not {'video', 'audio'} <= {s['codec_type'] for s in info['streams']}:
        raise ValueError(f'chapter {i} must have both video and audio: {video}')
    print(f'chapter {i} complete', flush=True)
    return video


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--workers', type=int, default=3)
    p.add_argument('--voice-cache', type=Path)
    p.add_argument('--check-label-overlap', action='store_true')
    p.add_argument('--no-voice', action='store_true')
    p.add_argument('--fps', type=int)
    p.add_argument('--size')
    p.add_argument('--font', type=Path)
    p.add_argument('--reuse-from', type=Path, help='reuse chapters whose spec.json matches a previous run')
    p.add_argument('--rerender', default='', help='comma-separated chapter ids or indices to force re-render')
    p.add_argument('--renderer', type=Path, default=RENDERER_ENTRY)
    args = p.parse_args()

    if not 1 <= args.workers <= 4:
        p.error('workers must be between 1 and 4')
    if not args.renderer.is_file():
        p.error(f'renderer not built: {args.renderer} (run npm run build in packages/renderer)')

    manifest_path = args.manifest.resolve()
    project_root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    chapters = manifest['chapters']
    try:
        validate_chapter_ids(chapters)
    except (KeyError, ValueError) as exc:
        p.error(str(exc))

    fps = int(args.fps or manifest.get('fps', FPS))
    size_str = str(args.size or manifest.get('size', SIZE))
    size = parse_size(size_str)
    font = args.font or manifest.get('font')
    reuse_from = args.reuse_from.resolve() if args.reuse_from else None
    rerender = {x.strip() for x in args.rerender.split(',') if x.strip()}

    cache = args.voice_cache.resolve() if args.voice_cache else None
    if cache and not cache.is_dir():
        p.error('voice cache must be an existing directory')

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    jobs = out / 'jobs'
    jobs.mkdir()
    card_seconds = float(manifest.get('cardSeconds', 2.5))
    cards, items, reused = {}, [], {}

    for i, ch in enumerate(chapters):
        spec = (project_root / ch['spec']).resolve()
        if not spec.is_file():
            raise FileNotFoundError(spec)
        spec_text = spec.read_text(encoding='utf-8')
        chapter_spec = json.loads(spec_text)
        if chapter_spec.get('bgm'):
            raise ValueError(f'chapter {i}: chapter_pipeline does not mix BGM; mix it after joining')
        if not args.no_voice and not any(shot.get('lines') for shot in chapter_spec.get('shots', [])):
            raise ValueError(f'chapter {i}: narrated shots are required')
        ch_id = ch['id']
        if can_reuse_chapter(reuse_from, ch_id, i, spec_text, rerender):
            prev_job = reuse_from / 'jobs' / ch_id
            dest = jobs / ch_id
            dest.mkdir()
            reused_mp4 = dest / f'{ch_id}.mp4'
            shutil.copy2(prev_job / f'{ch_id}.mp4', reused_mp4)
            shutil.copy2(prev_job / 'spec.json', dest / 'spec.json')
            reused[i] = reused_mp4
            print(f'chapter {i} ({ch_id}) reused', flush=True)
        else:
            opts = {'fps': fps, 'size': size_str, 'no_voice': args.no_voice}
            items.append((i, spec, jobs / ch_id, cache, args.check_label_overlap, project_root, args.renderer.resolve(), opts))
        if i:
            image, video = jobs / f'card-{i:02}.png', jobs / f'card-{i:02}.mp4'
            card(ch['title'], i, image, video, manifest.get('series', ''), fps, card_seconds, size=size, font=font)
            cards[i] = video

    print(f'rendering {len(items)} chapters with {args.workers} workers ({len(reused)} reused)', flush=True)
    rendered = {}
    if items:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for item, video in zip(items, pool.map(render, items)):
                rendered[item[0]] = video
    videos = [reused[i] if i in reused else rendered[i] for i in range(len(chapters))]

    ordered = []
    chapter_durations = [duration(video) for video in videos]
    card_durations = [duration(cards[i]) for i in range(1, len(chapters))]
    timeline, _ = build_timeline(chapters, chapter_durations, card_durations)
    for i, (ch, video) in enumerate(zip(chapters, videos)):
        if i:
            ordered.append(cards[i])
        ordered.append(video)

    concat = out / 'concat.txt'
    concat.write_text(''.join(format_concat_line(f) for f in ordered), encoding='utf-8')
    print('measuring complete audio', flush=True)
    measure = run(
        [
            'ffmpeg', '-hide_banner', '-nostats', '-f', 'concat', '-safe', '0', '-i', str(concat),
            '-vn', '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-',
        ],
        capture_output=True,
        text=True,
    )
    filt = parse_loudnorm(measure.stderr)
    result = out / 'episode.mp4'
    print('joining chapters', flush=True)
    run(
        [
            'ffmpeg', '-nostdin', '-v', 'error', '-n', '-f', 'concat', '-safe', '0', '-i', str(concat),
            '-map', '0:v:0', '-map', '0:a:0', '-c:v', 'copy', '-af', filt, '-c:a', 'aac', '-b:a', '192k',
            '-ar', '48000', '-ac', '2', '-movflags', '+faststart', str(result),
        ]
    )
    (out / 'chapters.json').write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'complete {result} {duration(result):.2f}s', flush=True)


if __name__ == '__main__':
    main()
