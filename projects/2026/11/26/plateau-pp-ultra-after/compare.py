"""out/compare_<day|night>.jpg: per area, before and after side by side for each view (aerial, roof, street)."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BEFORE = HERE.parent / "plateau-pp-ultra-before"
areas = json.loads((BEFORE / "areas.json").read_text(encoding="utf-8"))["areas"]
try:
    font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 20)
except OSError:
    font = ImageFont.load_default()
W, H = 480, 270
for t in ("day", "night"):
    rows = [a for a in areas if (HERE / "out" / a["name"] / f"{t}_aerial.png").exists()
            and (BEFORE / "out" / a["name"] / f"{t}_aerial.png").exists()]
    sheet = Image.new("RGB", (W * 6, H * len(rows)), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for r, a in enumerate(rows):
        for c, view in enumerate(("aerial", "roof", "street")):
            for k, root in enumerate((BEFORE, HERE)):
                x = W * (2 * c + k)
                sheet.paste(Image.open(root / "out" / a["name"] / f"{t}_{view}.png").convert("RGB").resize((W, H)), (x, H * r))
                d.rectangle((x, H * r, x + 70, H * r + 26), fill=(0, 0, 0))
                d.text((x + 6, H * r + 2), ("before", "after")[k], font=font, fill=(255, 255, 255))
        d.rectangle((0, H * r + 26, 300, H * r + 54), fill=(0, 0, 0))
        d.text((6, H * r + 28), a["label"], font=font, fill=(255, 255, 255))
    sheet.save(HERE / "out" / f"compare_{t}.jpg", quality=85)
    print(HERE / "out" / f"compare_{t}.jpg")
