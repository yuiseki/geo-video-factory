"""Build the label-enabled episode using the existing dialogue and CC0 photos."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent
spec = json.loads((root / 'shots/dotonbori.json').read_text())
prepared = json.loads((root / 'out/final/prepared-shots.json').read_text())
photos = json.loads((root / 'assets/gyazo/panels_v011/manifest.json').read_text())
candidates = json.loads((root / 'assets/nominatim-label-candidates.json').read_text())


def candidate(query, category, kind):
    group = next(group for group in candidates if group['query'] == query)
    found = [row for row in group['results'] if row['category'] == category and row['type'] == kind]
    row = max(found, key=lambda row: row['importance'])
    return [float(row['lon']), float(row['lat'])]


locations = {
    (135.50115, 34.66881): ('道頓堀', candidate('道頓堀', 'place', 'locality')),
    (135.4125, 34.6427): ('コスモスクエア駅', candidate('コスモスクエア', 'railway', 'station')),
    (139.78746, 35.69521): ('両国橋', candidate('両国橋', 'man_made', 'bridge')),
    (139.7617, 35.6666): ('新橋・汐留川跡', [139.7617, 35.6666]),
    (135.457, 34.654): ('道頓堀', candidate('道頓堀', 'place', 'locality')),
}
spec['osmLabels'] = True
elapsed = 0.0
assert len(prepared['shots']) == len(spec['shots'])
for shot, timed in zip(spec['shots'], prepared['shots']):
    duration = timed['duration']
    midpoint = elapsed + duration / 2
    location, coordinates = locations[tuple(shot['from']['center'])]
    overlays = shot['overlays']
    photo = next((p for p in photos if p['start'] <= midpoint < p['end']), None)
    if photo:
        overlays = [{'type': 'panel', 'src': f"assets/gyazo/{photo['id']}.jpg",
                     'caption': photo['caption'], 'credit': '写真：ユイ / Gyazo（CC0）',
                     'screen': [80, 80], 'width': 900, 'show': [0, 1]}]
    elif len(overlays) == 1 and overlays[0]['type'] == 'label':
        overlays = [{'type': 'label', 'at': coordinates, 'text': location,
                     'style': 'tag', 'show': [0, 1]}]
    for overlay in overlays:
        if overlay.get('type') == 'panel' and overlay.get('src', '').startswith('assets/maps/'):
            overlay['caption'] = f"{location}周辺（現在の地名）：{overlay['caption']}"
    shot['overlays'] = overlays
    elapsed += duration

target = root / 'shots/dotonbori.v0.1.2.json'
target.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n')
print(f'{target}: {len(spec["shots"])} shots, approximately {elapsed:.1f} seconds')
