"""Revise the episode's visual rhythm and use each panel image at most once."""
import json
from pathlib import Path
from shot_effects import camera_views, landmark, photo_motion

root = Path(__file__).resolve().parent
spec = json.loads((root / 'shots/dotonbori.v0.1.2.json').read_text())
seen = set()
# Alternate captures of the same meal or near-identical billboard view.
redundant = {'assets/gyazo/ccfeb7040f40c4dcc23f71033fc9ecb0.jpg',
             'assets/gyazo/46d8534ae3060ddef51435a86c2c8aac.jpg'}
anchors = {
    (135.50115, 34.66881): ('道頓堀', [135.5015715, 34.6690306]),
    (139.78746, 35.69521): ('両国橋', [139.7888628, 35.6943052]),
    (139.7617, 35.6666): ('新橋・汐留川跡', [139.7617, 35.6666]),
    (135.4125, 34.6427): ('コスモスクエア駅', [135.4122147, 34.6425771]),
    (135.457, 34.654): ('道頓堀', [135.5015715, 34.6690306]),
}
extra = {
    11: ('9e289c21ab57679c2ac005f95818c4f1', '道頓堀の看板（2026年11月13日）'),
    23: ('f01c299b67d773988e5257a0fecd41cb', '大阪松竹座（2026年11月13日）'),
}
commons = json.loads((root / 'assets/commons-v013/credits.json').read_text())
commons_by_index = {79: (1, 'コスモスクエア駅の入口'), 80: (0, 'コスモスクエア駅のニュートラム'),
                    101: (3, '南港ポートタウン線の高架'), 108: (6, '大阪南港の ATC'),
                    114: (5, '大阪南港の ATC ホール')}
osm = json.loads((root / 'assets/newtram-overpass.json').read_text())
relation = next(x for x in osm['elements'] if x['type'] == 'relation' and x['id'] == 444913)
ways = {x['id']: x for x in osm['elements'] if x['type'] == 'way'}
route = [[(point['lon'], point['lat']) for point in ways[member['ref']]['geometry']]
         for member in relation['members'] if member['type'] == 'way' and not member.get('role')]
photo_count = 0

for index, shot in enumerate(spec['shots']):
    overlays = []
    for overlay in shot['overlays']:
        if overlay['type'] == 'panel':
            src = overlay['src']
            if src in seen or src in redundant:
                continue
            seen.add(src)
        overlays.append(overlay)
    if index in extra:
        image_id, caption = extra[index]
        src = f'assets/gyazo/{image_id}.jpg'
        if src not in seen:
            seen.add(src)
            overlays = [{'type': 'panel', 'src': src, 'caption': caption,
                         'credit': '写真：ユイ / Gyazo（CC0）', 'screen': [80, 80],
                         'width': 1000, 'show': [0, 1]}]
    if index in commons_by_index:
        number, caption = commons_by_index[index]
        item = next(row for row in commons if row['file'].endswith(f'/{number:02}.jpg'))
        src = item['file']
        if src not in seen:
            seen.add(src)
            overlays = [{'type': 'panel', 'src': src, 'caption': caption,
                         'credit': f"写真：{item['artist']} / Wikimedia Commons（{item['license']}）",
                         'screen': [80, 80], 'width': 1000, 'show': [0, 1]}]
    if not overlays:
        name, coord = anchors[tuple(shot['from']['center'])]
        overlays = [landmark(name, coord)]
    for overlay in overlays:
        if overlay['type'] == 'panel' and not overlay['src'].startswith('assets/maps/'):
            overlay['motion'] = photo_motion(photo_count)
            overlay['width'] = max(overlay.get('width', 720), 1000)
            photo_count += 1
    shot['overlays'] = overlays

    # Choose the view according to what this sentence is explaining.
    center = shot['from']['center']
    name, _ = anchors[tuple(center)]
    text = shot['lines'][0]['text']
    if any(o['type'] in ('panel', 'chapter') for o in overlays):
        effect = 'hold'
    elif any(word in text for word in ('川', '水辺', '水路', '運河')):
        effect = 'track_river'
    elif any(word in text for word in ('全体', '都市', '大阪', '未来', '広が', '生活圏')):
        effect = 'reveal_context'
    elif any(word in text for word in ('駅', '橋', '看板', 'ここ', '店', '建物')):
        effect = 'approach'
    else:
        effect = 'quiet'
    start, end = camera_views(shot['from'], effect)
    shot['from'], shot['to'] = start, end
    if index == 83:
        # Current route, not a claim about the pre-1997 network.
        start.update(center=[135.442, 34.626], zoom=12.0, pitch=18, bearing=0)
        end.update(center=[135.442, 34.626], zoom=12.2, pitch=18, bearing=0)
        shot['overlays'] = [
            *[{'type': 'line', 'coords': points, 'color': '#00a0de', 'width': 5, 'show': [0, 1]}
              for points in route],
            {'type': 'label', 'screen': [370, 90], 'text': 'ニュートラム（現在の路線）', 'style': 'tag', 'show': [0, 1]},
            {'type': 'label', 'at': [135.4122584, 34.6425341], 'text': 'コスモスクエア', 'dot': True, 'show': [0, 1]},
            {'type': 'label', 'at': [135.4719336, 34.6092699], 'text': '住之江公園', 'dot': True, 'show': [0, 1]},
        ]

target = root / 'shots/dotonbori.v0.1.3.json'
target.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n')
print(f'{target}: {len(spec["shots"])} shots, {len(seen)} distinct panel images')
