"""out/compare/sheet.jpg: every area in a row, Blender on the left and three.js on the right."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "compare"
areas = json.loads((HERE / "areas.json").read_text(encoding="utf-8"))["areas"]
try:
    font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 28)
except OSError:
    font = ImageFont.load_default()
rows = [a for a in areas if (OUT / f"{a['name']}_blender.png").exists()]
sheet = Image.new("RGB", (2560, 720 * len(rows)))
draw = ImageDraw.Draw(sheet)
for r, area in enumerate(rows):
    for i, (kind, label) in enumerate([("blender", "Blender (glTF の読み込みだけ)"), ("three", "three.js (素の GLTFLoader)")]):
        sheet.paste(Image.open(OUT / f"{area['name']}_{kind}.png").convert("RGB").resize((1280, 720)), (1280 * i, 720 * r))
        draw.rectangle((1280 * i, 720 * r, 1280 * i + 640, 720 * r + 46), fill=(0, 0, 0))
        draw.text((1280 * i + 12, 720 * r + 6), f"{area['label']}  {label}", font=font, fill=(255, 255, 255))
sheet.save(OUT / "sheet.jpg", quality=88)
print(OUT / "sheet.jpg")
