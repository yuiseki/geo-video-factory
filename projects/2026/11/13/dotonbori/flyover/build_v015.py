"""Attach owner photographs to their EXIF camera positions and update the shop image."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'packages' / 'pipeline'))
from photo_geo import exif_coordinates, linked_photo

ROOT = Path(__file__).resolve().parent
spec = json.loads((ROOT / 'shots/dotonbori.v0.1.3.json').read_text())

# Subject coordinates are OSM features, separate from EXIF camera positions.
subjects = {
    '63fec71eed55499db29276a87216b48f': {'at': [135.5027289, 34.6692927], 'name': 'ドン・キホーテ道頓堀店'},
    '595dc51520a6d3b3ba9c0831ae3f52c1': {'at': [135.5010546, 34.6689260], 'name': 'グリコサイン'},
    'f01c299b67d773988e5257a0fecd41cb': {'at': [135.5009117, 34.6684231], 'name': '大阪松竹座'},
}
bridges = {'595dc51520a6d3b3ba9c0831ae3f52c1': {'at': [135.5012993, 34.6690658], 'name': '戎橋'}}
used = []
for shot in spec['shots']:
    for i, overlay in enumerate(shot['overlays']):
        src = overlay.get('src', '')
        if overlay['type'] == 'panel' and src.startswith('assets/gyazo/'):
            key = Path(src).stem
            position = exif_coordinates(ROOT / src)
            replacement = linked_photo(src, overlay.get('caption', ''), position,
                                       subject=subjects.get(key), bridge=bridges.get(key))
            shot['overlays'][i] = replacement
            # The point remains in the open area to the right of the photo while the camera moves.
            lon, lat = position
            shot['from'] = {'center': [lon - 0.0017, lat - 0.00005], 'zoom': 16.0, 'pitch': 20, 'bearing': -5}
            shot['to'] = {'center': [lon - 0.0016, lat - 0.00005], 'zoom': 16.3, 'pitch': 32, 'bearing': 5}
            used.append({'src': src, 'camera': position, 'subject': subjects.get(key)})
        elif overlay['type'] == 'panel' and src == 'assets/commons/takoyaki.jpg':
            shot['overlays'][i] = {
                'type': 'panel', 'src': 'assets/commons-v013/kukuru-honten.webp',
                'caption': 'たこ家道頓堀くくる 道頓堀本店',
                'credit': '出典：たこ家道頓堀くくる公式サイト（dotonbori-kukuru.com/dotonbori-honten/）',
                'screen': [80, 80], 'width': 1000, 'motion': 'still', 'show': [0, 1],
            }

spec['credits'] = [c for c in spec.get('credits', []) if '写真：ユイ' not in c]
out = ROOT / 'shots/dotonbori.v0.1.5.json'
out.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n')
(ROOT / 'assets/v015-photo-locations.json').write_text(json.dumps(used, ensure_ascii=False, indent=2) + '\n')
print(f'{out}: {len(used)} EXIF-linked photographs')
