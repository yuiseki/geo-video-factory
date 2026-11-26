#!/usr/bin/env python3
"""Build narrated, independently renderable chapters from the checked storyboard and script."""
from __future__ import annotations
import copy
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT.parent / 'script.md'
SOURCE = ROOT / 'shots/storyboard.json'
VERSION = 'v0.2.0'
DEST = ROOT / f'shots/episode-{VERSION}'


def speech_text(text: str) -> str:
    # VOICEVOX audio_query readings checked for every line; leave the subtitle untouched.
    for written, reading in (
        ('金鉱床', 'きんこうしょう'), ('金山', 'きんざん'), ('土肥', 'とい'),
        ('フィリピン海', 'フィリピンかい'), ('真ん中の値', '真ん中のあたい'),
        ('示す値', '示すあたい'),
    ):
        text = text.replace(written, reading)
    return text


def circle_coords(center: list[float], radius_m: float = 500) -> list[list[float]]:
    lon, lat = map(math.radians, center)
    angular = radius_m / 6371008.8
    points = []
    for i in range(73):
        bearing = 2 * math.pi * i / 72
        lat2 = math.asin(math.sin(lat) * math.cos(angular) + math.cos(lat) * math.sin(angular) * math.cos(bearing))
        lon2 = lon + math.atan2(math.sin(bearing) * math.sin(angular) * math.cos(lat), math.cos(angular) - math.sin(lat) * math.sin(lat2))
        points.append([round(math.degrees(lon2), 8), round(math.degrees(lat2), 8)])
    return points


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
            text = text.strip()
            line = {'voice': 'a' if name == 'ずんだもん' else 'b', 'text': text}
            reading = speech_text(text)
            if reading != text:
                line['speech'] = reading
            result[-1][1].append(line)
    if len(result) != 9 or any(not lines for _, lines in result):
        raise ValueError('script must contain nine nonempty chapters')
    return result


def safe_overlays(index: int, overlays: list[dict], part: int) -> list[dict]:
    result = copy.deepcopy(overlays)
    for o in result:
        if o.get('type') == 'label' and o.get('at') and any(s in o.get('text', '') for s in ('金山', '鉱山', '鉱滓堆積場')):
            o['leader'] = True
            o['dot'] = False
            x, y = o.get('offset', [0, -80])
            o['offset'] = [x, min(-80, y)]
            if any(s in o['text'] for s in ('縄地', '河津', 'ほおずき')):
                o['text'] += '（概略）'
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
        mines = json.loads((ROOT.parent / 'research/data/mines.geojson').read_text(encoding='utf-8'))['features']
        for name, location, offset in (
            ('龕附天正金鉱', [138.79035, 34.90588], [-110, -90]),
            ('湯ヶ島鉱山（概略）', [138.9034, 34.88621], [110, -105]),
        ):
            result.append({'type': 'label', 'text': name, 'at': location, 'offset': offset,
                           'leader': True, 'style': 'tag', 'show': [0.1, 1]})
        for feature in mines:
            result.append({'type': 'polygon', 'coords': circle_coords(feature['geometry']['coordinates']),
                           'fill': '#ffd36a', 'fillOpacity': 0.04, 'outline': '#ffcf54', 'width': 3, 'show': [0, 1]})
        result.append({'type': 'note', 'text': '鉱山の代表地点から半径0.5km・位置は概略'})
        if part < 3:
            labels = [o for o in result if o.get('type') == 'label' and o.get('leader')]
            keep = {o['text'] for o in labels[part * 3:(part + 1) * 3]}
            result = [o for o in result if o.get('type') != 'label' or not o.get('leader') or o['text'] in keep]
        else:
            result = [o for o in result if (o.get('type') != 'label' or o.get('text') == '土肥金山') and o.get('type') != 'counter']
            result.append({'type': 'counter', 'screen': [70, 60], 'caption': '土肥金山からの半径', 'value': 0.5, 'decimals': 1, 'unit': 'km', 'scale': 1.2, 'show': [0, 1]})
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
            'cameraPadding': {'bottom': 260},
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
            if i == 1 and part == parts - 1:
                shot['from'] = interpolate_camera(a, b, 1)
                shot['to'] = {'center': [138.79326, 34.90814], 'zoom': 12.7, 'pitch': 35, 'bearing': 0}
                shot['ease'] = 'smooth'
            else:
                denominator = parts - 1 if i == 1 else parts
                shot['from'] = interpolate_camera(a, b, part / denominator)
                shot['to'] = interpolate_camera(a, b, (part + 1) / denominator)
            shot['lines'] = lines[part * 4:(part + 1) * 4]
            shot['overlays'] = safe_overlays(i, original.get('overlays', []), part)
            spec['shots'].append(shot)
        ident = f'ch{i + 1:02}'
        (DEST / f'{ident}.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        manifest['chapters'].append({'id': ident, 'title': title, 'spec': f'shots/episode-{VERSION}/{ident}.json'})
    (ROOT / f'chapters-{VERSION}.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Built {len(chapters)} chapters with {sum(len(x[1]) for x in chapters)} lines')


if __name__ == '__main__':
    main()
