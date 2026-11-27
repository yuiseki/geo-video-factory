"""out/compare_<area>.jpg: one sheet per area, before on the left and after on the right, a row per daytime view
(aerial, roof, street). python compare.py [area ...]"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BEFORE = HERE.parent / "plateau-pp-ultra-before"
areas = json.loads((BEFORE / "areas.json").read_text(encoding="utf-8"))["areas"]
try:
    font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 24)
except OSError:
    font = ImageFont.load_default()
W, H = 800, 450
VIEWS = [("day", v) for v in ("aerial", "roof", "street")]
NAMES = {"aerial": "空から", "roof": "屋上", "street": "目の高さ"}


def label(d, x, y, text):
    w = d.textlength(text, font=font)
    d.rectangle((x, y, x + w + 16, y + 34), fill=(0, 0, 0))
    d.text((x + 8, y + 2), text, font=font, fill=(255, 255, 255))


want = set(sys.argv[1:])
for a in areas:
    if want and a["name"] not in want:
        continue
    rows = [(t, v) for t, v in VIEWS
            if all((root / "out" / a["name"] / f"{t}_{v}.png").exists() for root in (BEFORE, HERE))]
    if not rows:
        continue
    sheet = Image.new("RGB", (W * 2, H * len(rows)), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for r, (t, v) in enumerate(rows):
        for k, root in enumerate((BEFORE, HERE)):
            x = W * k
            sheet.paste(Image.open(root / "out" / a["name"] / f"{t}_{v}.png").convert("RGB").resize((W, H)), (x, H * r))
            label(d, x, H * r, f"{('before', 'after')[k]}  {a['label']}  {NAMES[v]}")
    out = HERE / "out" / f"compare_{a['name']}.jpg"
    sheet.save(out, quality=88)
    print(out)
