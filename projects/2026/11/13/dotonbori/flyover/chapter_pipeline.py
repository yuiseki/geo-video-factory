"""Render independent narrated chapters, insert silent cards, and join the episode.

Run the entire command inside one resource-limited systemd scope.  Rendering
parallelism is bounded; the existing VOICEVOX cache is shared read-only.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess

import build_story
from shot_effects import landmark
from title_card import create_card, encode_card

ROOT = Path(__file__).resolve().parent
RENDERER_ENTRY = ROOT.parents[4] / 'packages' / 'renderer' / 'dist' / 'src' / 'render.js'
CARD_SECONDS = 2.5
FPS = 24


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def duration(path):
    p = run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
            capture_output=True, text=True)
    return float(p.stdout.strip())


def chapter_specifications(spec, turns):
    sections = []
    for turn in turns:
        sections.extend([turn['section']] * len(build_story.split_text(turn['text'])))
    if len(sections) != len(spec['shots']):
        raise ValueError('dialogue and shot counts differ; refusing to split')
    results = []
    for section in dict.fromkeys(sections):
        chapter = {k: v for k, v in spec.items() if k != 'shots'}
        chapter['shots'] = []
        for i, (which, shot) in enumerate(zip(sections, spec['shots'])):
            if which != section:
                continue
            shot = json.loads(json.dumps(shot))
            shot['overlays'] = [x for x in shot['overlays'] if x['type'] != 'chapter']
            # Ground the subject relative to two known Osaka Metro stations.
            if section in (0, 1) and not shot.get('transition') and not any(x['type'] in ('panel', 'photo_marker') for x in shot['overlays']):
                shot['overlays'] += [
                    landmark('なんば駅', [135.5002710, 34.6661565]),
                    landmark('心斎橋駅', [135.5003566, 34.6745173]),
                ]
            chapter['shots'].append(shot)
        results.append((section, build_story.TITLES[section], chapter))
    return results


def render_chapter(item):
    section, _, spec_path, output = item
    log = output.parent / f'{output.name}.log'
    with log.open('x') as stream:
        p = subprocess.run(['node', str(RENDERER_ENTRY), str(spec_path), '--project', str(ROOT), '--out', str(output),
                            '--size', '1920x1080', '--fps', str(FPS), '--raw-audio'],
                           cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    if p.returncode:
        raise RuntimeError(f'chapter {section} failed; see {log}')
    text = log.read_text(errors='replace')
    if any(line.startswith(('[http ', '[page]', 'warning:', 'Error:')) for line in text.replace('\r', '\n').splitlines()):
        raise RuntimeError(f'chapter {section} logged a rendering error; see {log}')
    print(f'chapter {section} complete', flush=True)
    return output / (output.name + '.mp4')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--workers', type=int, default=3)
    p.add_argument('--spec', type=Path, default=ROOT / 'shots/dotonbori.v0.1.3.json')
    p.add_argument('--version', default='v0.1.4')
    p.add_argument('--reuse-from', type=Path, help='reuse chapters whose generated specifications are identical')
    p.add_argument('--rerender', default='', help='comma-separated chapter numbers to render even when reusable')
    args = p.parse_args()
    if not 1 <= args.workers <= 4:
        p.error('workers must be between 1 and 4')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    jobs = out / 'jobs'
    jobs.mkdir()
    spec = json.loads(args.spec.read_text())
    turns = build_story.parse_dialogue(build_story.SOURCE.read_text())
    chapters = chapter_specifications(spec, turns)
    force = {int(x) for x in args.rerender.split(',') if x.strip()}
    items, cards, reused = [], {}, {}
    for section, title, chapter in chapters:
        spec_path = jobs / f'chapter-{section:02}.json'
        spec_path.write_text(json.dumps(chapter, ensure_ascii=False, indent=2))
        if args.reuse_from:
            previous = args.reuse_from.resolve() / 'jobs'
            old_spec = previous / f'chapter-{section:02}.json'
            old_video = previous / f'chapter-{section:02}' / f'chapter-{section:02}.mp4'
            if section not in force and old_spec.is_file() and old_video.is_file() and json.loads(old_spec.read_text()) == chapter:
                reused[section] = old_video
        clip_out = jobs / f'chapter-{section:02}'
        clip_out.mkdir()
        (clip_out / 'voice-cache').symlink_to(ROOT / 'out/final/voice-cache', target_is_directory=True)
        items.append((section, title, spec_path, clip_out))
        if section:
            img = jobs / f'card-{section:02}.png'
            card = jobs / f'card-{section:02}.mp4'
            create_card(title, section, img)
            encode_card(img, card, fps=FPS, seconds=CARD_SECONDS)
            cards[section] = card
    pending = [item for item in items if item[0] not in reused]
    print(f'rendering {len(pending)} chapters using {args.workers} workers; reusing {len(reused)} unchanged chapters', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        fresh = dict(zip((item[0] for item in pending), pool.map(render_chapter, pending)))
    paths = [reused.get(item[0]) or fresh[item[0]] for item in items]
    ordered, chapters_info, cursor = [], [], 0.0
    for (section, title, _, _), video in zip(items, paths):
        if section:
            chapters_info.append({'title': title, 'start': cursor})
            ordered.append(cards[section]); cursor += duration(cards[section])
        else:
            chapters_info.append({'title': title, 'start': cursor})
        ordered.append(video); cursor += duration(video)
    concat = out / 'concat.txt'
    concat.write_text(''.join("file '" + str(f).replace("'", "'\\''") + "'\n" for f in ordered))
    print('measuring complete audio', flush=True)
    measure = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-f', 'concat', '-safe', '0', '-i', str(concat),
                              '-vn', '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'],
                             check=True, capture_output=True, text=True)
    raw = measure.stderr
    levels = json.loads(raw[raw.rfind('{'):raw.rfind('}') + 1])
    filt = ('loudnorm=I=-14:TP=-1.5:LRA=11:'
            f"measured_I={levels['input_i']}:measured_TP={levels['input_tp']}:"
            f"measured_LRA={levels['input_lra']}:measured_thresh={levels['input_thresh']}:"
            f"offset={levels['target_offset']}:linear=true")
    result = out / f'dotonbori.{args.version}.mp4'
    print('joining chapters', flush=True)
    run(['ffmpeg', '-nostdin', '-v', 'error', '-n', '-f', 'concat', '-safe', '0', '-i', str(concat),
         '-map', '0:v:0', '-map', '0:a:0', '-c:v', 'copy', '-af', filt, '-c:a', 'aac', '-b:a', '192k',
         '-ar', '48000', '-ac', '2', '-movflags', '+faststart', str(result)])
    (out / 'chapters.json').write_text(json.dumps(chapters_info, ensure_ascii=False, indent=2))
    print(f'complete {result} {duration(result):.2f}s', flush=True)


if __name__ == '__main__':
    main()
