"""out/sheet_<day|night>.jpg: one row per area (aerial, roof, street), labelled."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
areas = json.loads((HERE / "areas.json").read_text(encoding="utf-8"))["areas"]
try:
    font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 24)
except OSError:
    font = ImageFont.load_default()
W, H = 640, 360
for t in ("day", "night"):
    rows = [a for a in areas if (HERE / "out" / a["name"] / f"{t}_aerial.png").exists()]
    sheet = Image.new("RGB", (W * 3, H * len(rows)))
    d = ImageDraw.Draw(sheet)
    for r, a in enumerate(rows):
        for c, view in enumerate(("aerial", "roof", "street")):
            sheet.paste(Image.open(HERE / "out" / a["name"] / f"{t}_{view}.png").convert("RGB").resize((W, H)), (W * c, H * r))
        d.rectangle((0, H * r, 420, H * r + 36), fill=(0, 0, 0))
        d.text((10, H * r + 4), a["label"], font=font, fill=(255, 255, 255))
    sheet.save(HERE / "out" / f"sheet_{t}.jpg", quality=88)
    print(HERE / "out" / f"sheet_{t}.jpg")
