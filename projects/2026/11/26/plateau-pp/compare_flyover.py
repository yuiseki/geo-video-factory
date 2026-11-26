"""Render every trial area with the production renderer (flyover), before (no bake) and after (PLATEAU++ v0.1.0).

    python projects/2026/11/26/plateau-pp/compare_flyover.py

Needs out/<name>/ and out/before/<name>/ (build_trial.py, with and without --no-bake) and a built
packages/renderer. Writes the shot specs and renders to out/flyover/, and out/compare/flyover_<view>.jpg: one row
per area, before on the left and after on the right, for an overview and a close view of the same camera path.
Run from the repository root under the host's resource limits.
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
OUT = HERE / "out"
VARIANTS = {"before": ("out/before/{name}/manifest.json", "旧 PLATEAU++ (描画時のシェーダー)"),
            "after": ("out/{name}/manifest.json", "PLATEAU++ v0.1.0 (焼き込み)")}
VIEWS = ("overview", "close")


def spec(area: dict, manifest: str) -> dict:
    w, s, e, n = area["bbox"]
    c = [(w + e) / 2, (s + n) / 2]
    return {"width": 1280, "height": 720, "fps": 30, "fov": 36.87, "base": "seamlessphoto", "world": False,
            "dem": "gsi", "hillshade": False,
            "sky": {"sky-color": "#9ec3ea", "horizon-color": "#dfe9f3", "fog-color": "#dfe9f3",
                    "sky-horizon-blend": 0.6, "horizon-fog-blend": 0.7, "fog-ground-blend": 0.9},
            "credits": ["建物: 国土交通省 PLATEAU / 国土地理院 / © OpenStreetMap contributors"],
            "plateauBuildings": {"manifest": manifest, "heightOffset": -37, "workers": 3},
            "shots": [{"duration": 2.0, "ease": "linear", "keys": [
                {"t": 0.0, "center": c, "zoom": 16.0, "pitch": 60, "bearing": 20},
                {"t": 1.0, "center": c, "zoom": 18.2, "pitch": 72, "bearing": 35}]}]}


def main() -> None:
    areas = json.loads((HERE / "areas.json").read_text(encoding="utf-8"))["areas"]
    (OUT / "flyover").mkdir(parents=True, exist_ok=True)
    (OUT / "compare").mkdir(parents=True, exist_ok=True)
    for area in areas:
        for variant, (manifest, _) in VARIANTS.items():
            path = OUT / "flyover" / f"{area['name']}-{variant}.json"
            path.write_text(json.dumps(spec(area, manifest.format(name=area["name"])), ensure_ascii=False, indent=1))
            subprocess.run(["node", str(REPO / "packages/renderer/dist/src/render.js"), str(path), "--project", str(HERE),
                            "--out", str(OUT / "flyover" / path.stem), "--stills", "1.98", "--no-voice"], check=True)
    try:
        font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 26)
    except OSError:
        font = ImageFont.load_default()
    for k, view in enumerate(VIEWS):
        sheet = Image.new("RGB", (2560, 720 * len(areas)))
        draw = ImageDraw.Draw(sheet)
        for r, area in enumerate(areas):
            for i, (variant, (_, label)) in enumerate(VARIANTS.items()):
                frames = sorted((OUT / "flyover" / f"{area['name']}-{variant}" / "frames").glob("*"))
                sheet.paste(Image.open(frames[k]).convert("RGB").resize((1280, 720)), (1280 * i, 720 * r))
                draw.rectangle((1280 * i, 720 * r, 1280 * i + 720, 720 * r + 44), fill=(0, 0, 0))
                draw.text((1280 * i + 12, 720 * r + 6), f"{area['label']}  {label}", font=font, fill=(255, 255, 255))
        sheet.save(OUT / "compare" / f"flyover_{view}.jpg", quality=88)
        print(OUT / "compare" / f"flyover_{view}.jpg")


if __name__ == "__main__":
    sys.exit(main())
