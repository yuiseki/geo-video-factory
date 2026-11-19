#!/usr/bin/env python3
"""Build narrated, independently renderable chapters from the checked storyboard and script."""
from __future__ import annotations
import copy
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT.parent / 'script.md'
SOURCE = ROOT / 'shots/storyboard_v0_6.json'
DEST = ROOT / 'shots/episode-v0.1.0'


def interpolate_camera(a: dict, b: dict, t: float) -> dict:
    result = {}
    for key in ('center', 'zoom', 'pitch', 'bearing'):
        av, bv = a[key], b[key]
        if key == 'center':
            result[key] = [round(x + (y - x) * t, 7) for x, y in zip(av, bv)]
        elif key == 'bearing':
            delta = (bv - av + 180) % 360 - 180
            result[key] = round(av + delta * t, 6)
        else:
            result[key] = round(av + (bv - av) * t, 6)
    return result


def read_script() -> list[tuple[str, list[dict]]]:
    result = []
    for raw in SCRIPT.read_text(encoding='utf-8').splitlines():
        if raw.startswith('## '):
            result.append((raw[6:].strip(), []))
        elif raw.startswith(('ずんだもん:', '四国めたん:')):
            name, text = raw.split(':', 1)
            result[-1][1].append({'voice': 'a' if name == 'ずんだもん' else 'b', 'text': text.strip()})
    if len(result) != 9 or any(not lines for _, lines in result):
        raise ValueError('script must contain nine nonempty chapters')
    return result


def safe_overlays(index: int, overlays: list[dict], part: int) -> list[dict]:
    result = copy.deepcopy(overlays)
    # Statistics apply to selected observations; sampled facilities and estimated river network
    # are not exhaustive counts or the measured extent of contamination.
    for o in result:
        if index == 0 and o.get('caption') == '伊豆半島の温泉と旅館':
            o['caption'] = '地図から選んだ温泉関連施設'
        if index == 1 and o.get('caption') == '伊豆半島の鉱山':
            o['caption'] = '今回選んだ鉱山'
        if index == 7 and o.get('caption') == 'シアン流出ルート総延長':
            o['caption'] = '河川網をたどった距離（概算）'
        if index == 6 and o.get('text') == '持越橋（シアン3.4ppm）':
            o['text'] = '持越橋付近'
    # The source research does not verify a precise 98 C measurement or actual pipe route.
    if index == 3:
        result = [o for o in result if o.get('type') not in ('counter', 'line')]
    # The mapped river network is not evidence of the contamination extent.
    if index == 7:
        result.append({'type': 'note', 'text': '河川網の概算経路・汚染範囲を示すものではありません'})
    if index == 1:
        result.append({'type': 'note', 'text': '選定地点の直線距離・位置は概略'})
    if part:
        result = [o for o in result if o.get('type') != 'chapter']
        for o in result:
            if o.get('type') == 'counter':
                o['from'] = o['value']
                o['roll'] = False
                o['countUp'] = [0, 0.01]
    return result


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    chapters = read_script()
    if len(source['shots']) != len(chapters):
        raise ValueError('script and storyboard counts do not match')
    DEST.mkdir(parents=True, exist_ok=True)
    manifest = {'series': '伊豆の温泉と金山', 'fps': 24, 'size': '1280x720', 'cardSeconds': 3.0, 'chapters': []}
    for i, ((title, lines), original) in enumerate(zip(chapters, source['shots'])):
        parts = math.ceil(len(lines) / 4)
        spec = {key: copy.deepcopy(value) for key, value in source.items() if key != 'shots'}
        spec.setdefault('credits', []).append('立ち絵：坂本アヒル')
        spec.update({
            'width': 1280, 'height': 720, 'fps': 24,
            'voices': {
                'a': {'speaker': 3, 'name': 'ずんだもん', 'speed': 1.2, 'color': '#ffe94a'},
                'b': {'speaker': 2, 'name': '四国めたん', 'speed': 1.15, 'color': '#ff9ca7'},
            },
            'tts': {'padStart': .18, 'pause': .25, 'padEnd': .25, 'wrap': 23},
            'reaction': {'characters': {'a': {'sprites': 'assets/chara/zundamon', 'seed': 'zundamon'}, 'b': {'sprites': 'assets/chara/metan', 'seed': 'metan'}}, 'order': ['b', 'a'], 'height': 160, 'side': 'right', 'bottom': 135},
            'shots': [],
        })
        a, b = original['from'], original['to']
        for part in range(parts):
            shot = copy.deepcopy(original)
            shot.pop('duration', None)
            shot['ease'] = 'linear'
            shot['from'] = interpolate_camera(a, b, part / parts)
            shot['to'] = interpolate_camera(a, b, (part + 1) / parts)
            shot['lines'] = lines[part * 4:(part + 1) * 4]
            shot['overlays'] = safe_overlays(i, original.get('overlays', []), part)
            spec['shots'].append(shot)
        ident = f'ch{i + 1:02}'
        (DEST / f'{ident}.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        manifest['chapters'].append({'id': ident, 'title': title, 'spec': f'shots/episode-v0.1.0/{ident}.json'})
    (ROOT / 'chapters-v0.1.0.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Built {len(chapters)} chapters with {sum(len(x[1]) for x in chapters)} lines')


if __name__ == '__main__':
    main()
