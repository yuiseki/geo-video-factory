"""Convert the episode dialogue into a reproducible narrated shot list."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent.parent.parent / '道頓堀文化の空洞化_ずんだもん四国めたん台本.md'


def split_text(text: str, limit: int = 42) -> list[str]:
    text = text.strip()
    chunks = []
    while len(text) > limit:
        if text[limit] in '。！？!?、，':
            chunks.append(text[:limit + 1].strip())
            text = text[limit + 1:].strip()
            continue
        window = text[:limit + 1]
        candidates = [i + 1 for i, c in enumerate(window[:-1]) if c in '。！？!?、，']
        near_end = [i for i in candidates if i >= limit // 2]
        cut = near_end[-1] if near_end else (candidates[-1] if candidates else limit)
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        chunks.append(text)
    return chunks


def parse_dialogue(source: str) -> list[dict]:
    section = 0
    lines = []
    for line in source.splitlines():
        if line.startswith('## 素材'):
            break
        match = re.match(r'^【場面(\d+)', line)
        if match:
            section = int(match.group(1))
        elif line.startswith('【導入'):
            section = 0
        elif line.startswith('【結び'):
            section = 8
        match = re.match(r'^\*\*(ずんだもん|四国めたん)：\*\*\s*(.+)', line)
        if match:
            voice = 'a' if match.group(1) == 'ずんだもん' else 'b'
            text = re.sub(r'\[\d+\]', '', match.group(2)).strip()
            lines.append({'section': section, 'voice': voice, 'text': text})
    return lines


PLACES = {
    0: ([135.50115, 34.66881], '道頓堀'),
    1: ([135.50115, 34.66881], '道頓堀'),
    2: ([139.78746, 35.69521], '両国・柳橋'),
    3: ([139.78746, 35.69521], '柳橋・神田川'),
    4: ([139.7617, 35.6666], '新橋・汐留川跡'),
    5: ([135.4125, 34.6427], 'コスモスクエア'),
    6: ([135.4125, 34.6427], '大阪南港・咲洲'),
    7: ([135.457, 34.654], '大阪市内'),
    8: ([135.457, 34.654], '大阪市内'),
}
TITLES = ['道頓堀からコスモスクエアへ', '光る水辺の街', '江戸の水辺の盛り場', '柳橋と川を守る堤防',
          '新橋と消えた水路', 'ニュートラムに乗って', '昭和に描かれた未来', '二つの街がある風景', '街の中に残る時間']

PANELS = {
    'dotonbori': ('assets/commons/dotonbori.jpg', '道頓堀の夜景（2015年）', '写真：Kristoffer Trolle / Wikimedia Commons（CC BY 2.0）', 900),
    'takoyaki': ('assets/commons/takoyaki.jpg', '道頓堀のたこ焼き店（別店舗・イメージ）', '写真：City Foodsters / Wikimedia Commons（CC BY 2.0）', 820),
    'glico': ('assets/commons/glico.jpg', '道頓堀のグリコサイン（2014年）', '写真：Tokumeigakarinoaoshima / Wikimedia Commons（CC0）', 490),
    'ryogoku': ('assets/commons/ryogoku.jpg', '歌川広重「両国橋大川ばた」（1856年）', 'Museum of Fine Arts, Boston / Wikimedia Commons（Public domain）', 420),
    'yanagibashi': ('assets/commons/yanagibashi.jpg', '歌川国芳「両国柳ばし」', 'British Museum / Wikimedia Commons（Public domain）', 750),
    'newtram': ('assets/commons/newtram.jpg', 'ニュートラムの車内', '写真：Hahifuheho / Wikimedia Commons（CC0）', 720),
    'station': ('assets/commons/station.jpg', 'コスモスクエア駅の案内（2024年）', '写真：Niiryoku2910 / Wikimedia Commons（CC BY 4.0）', 760),
    'atc': ('assets/commons/atc.jpg', '大阪南港のATCと周辺', '写真：U-ichiro Murakami / Wikimedia Commons（Public domain）', 820),
}


def photo_panel(key: str, x: int = 80, y: int = 80) -> dict:
    src, caption, credit, width = PANELS[key]
    return {'type': 'panel', 'src': src, 'caption': caption, 'credit': credit,
            'screen': [x, y], 'width': width, 'show': [0, 1]}


def map_panel(place: str, layer: str, caption: str, x: int) -> dict:
    return {'type': 'panel', 'src': f'assets/maps/{place}/{layer}.png', 'caption': caption,
            'credit': '空中写真：国土地理院 地理院タイルを加工', 'screen': [x, 85], 'width': 560, 'show': [0, 1]}


def overlays_for(section: int, i: int, text: str) -> list[dict]:
    if i == 0:
        return [{'type': 'chapter', 'kicker': 'YuisekinTV', 'text': TITLES[section], 'show': [0, 1]}]
    if section in (0, 1):
        if 'グリコ' in text:
            return [photo_panel('glico')]
        if '1615年' in text or '芝居小屋' in text:
            return [map_panel('dotonbori', 'ort_1928', '道頓堀 1928年頃', 80),
                    map_panel('dotonbori', 'seamlessphoto', '道頓堀 全国最新写真', 720)]
        if 'たこ焼き' in text:
            return [photo_panel('takoyaki')]
        return [photo_panel('dotonbori')] if i % 3 == 0 else []
    if section == 2:
        return [photo_panel('ryogoku' if i % 2 else 'yanagibashi')] if i % 3 else []
    if section in (3, 4):
        place = 'yanagibashi' if section == 3 else 'shimbashi'
        if i % 3 != 0:
            return [map_panel(place, 'ort_USA10', '1945〜1950年', 80),
                    map_panel(place, 'seamlessphoto', '全国最新写真', 720)]
        return []
    if section == 5:
        return [photo_panel('station' if i % 2 else 'newtram')] if i % 3 else []
    if section == 6:
        if 'ATC' in text or i % 4 == 0:
            return [photo_panel('atc')]
        if i % 3 != 0:
            return [map_panel('cosmosquare_station', 'gazo1', '1974〜1978年', 80),
                    map_panel('cosmosquare_station', 'seamlessphoto', '全国最新写真', 720)]
        return []
    if section in (7, 8):
        return [photo_panel('dotonbori' if i % 2 else 'atc')] if i % 3 == 0 else []
    return []


def speech_text(text: str) -> str:
    for old, new in [('明暦の大火', 'めいれきのたいか'), ('両国橋', 'りょうごくばし'), ('両国', 'りょうごく'),
                     ('高潮', 'たかしお'), ('防潮堤', 'ぼうちょうてい'),
                     ('柳橋', 'やなぎばし'), ('咲洲', 'さきしま'), ('中ふ頭', 'なかふとう'),
                     ('戎橋', 'えびすばし'), ('汐留川', 'シオドメガワ'), ('数寄屋橋', 'スキヤバシ'),
                     ('橋の上や川岸', 'はしのうえやかわぎし'), ('両岸', 'りょうがん'), ('栄え', 'さかえ'), ('出開帳', 'でがいちょう'),
                     ('芝居小屋', 'しばいごや'), ('ATC', 'エーティーシー'), ('VOICEVOX', 'ボイスボックス')]:
        text = text.replace(old, new)
    return text


def build_spec(source: str) -> dict:
    turns = parse_dialogue(source)
    shots = []
    seen = {}
    for turn in turns:
        section = turn['section']
        for text in split_text(turn['text']):
            index = seen.get(section, 0)
            seen[section] = index + 1
            center, label = PLACES[section]
            wide = section >= 7
            zoom = 11.5 if wide else 14.5 + (index % 3) * 0.3
            bearing = [-15, 5, 20, 0][index % 4]
            line = {'voice': turn['voice'], 'text': text, 'speech': speech_text(text),
                    'face': 'surprise' if '！？' in text else ('point' if turn['voice'] == 'b' else 'normal')}
            overlay = overlays_for(section, index, text)
            if not overlay:
                overlay = [{'type': 'label', 'text': label, 'screen': [220, 80], 'style': 'tag', 'show': [0, 1]}]
            shots.append({'from': {'center': center, 'zoom': zoom, 'pitch': 40, 'bearing': bearing},
                          'to': {'center': [center[0] + .0006, center[1] + .0003], 'zoom': zoom + .28,
                                 'pitch': 43, 'bearing': bearing + 8},
                          'lines': [line], 'overlays': overlay})
    return {'width': 1920, 'height': 1080, 'fps': 24, 'base': 'seamlessphoto', 'dem': 'gsi', 'exaggeration': 1.0,
            'world': False, 'voices': {'a': {'speaker': 3, 'name': 'ずんだもん', 'speed': 1.2, 'color': '#ffe94a'},
                                      'b': {'speaker': 2, 'name': '四国めたん', 'speed': 1.2, 'color': '#ff9ca7'}},
            'tts': {'padStart': .18, 'pause': .25, 'padEnd': .25, 'wrap': 23},
            'reaction': {'characters': {'a': {'sprites': 'assets/chara/zundamon', 'seed': 'zundamon'},
                                         'b': {'sprites': 'assets/chara/metan', 'seed': 'metan'}},
                         'order': ['b', 'a'], 'height': 240, 'side': 'right', 'bottom': 180},
            'credits': ['地図の位置は概略'], 'shots': shots}


if __name__ == '__main__':
    spec = build_spec(SOURCE.read_text(encoding='utf-8'))
    target = ROOT / 'shots' / 'dotonbori.json'
    target.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{target}: {len(spec["shots"])} shots')
