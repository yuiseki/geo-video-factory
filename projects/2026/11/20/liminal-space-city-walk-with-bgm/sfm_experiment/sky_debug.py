"""sky_debug.py <model> <tris> <align.json> <sky_dir> <images> <out.jpg> <solution idx> <key> [<key>...]
Draw photo skyline (yellow) and PLATEAU skyline (magenta) for some cameras."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import skyline as sl  # noqa: E402

model, tris, align, sky, images, out, idx = sys.argv[1:8]
keys = sys.argv[8:]
pr = sl.Problem(model, tris, align, Path(sky) / "skylines.json")
sol = pr.al["solutions"][int(idx)]
s, Rm, t = sol["scale"], np.array(sol["R"]), np.array(sol["t"])
tiles = []
for c in pr.cams:
    if not any(k in c["name"] for k in keys):
        continue
    top = pr.render(c, s, Rm, t)
    im = Image.open(Path(images) / c["name"]).convert("RGB").resize((sl.W, c["H"]))
    d = ImageDraw.Draw(im)
    d.line([(x, r) for x, r in enumerate(c["rows"]) if not np.isnan(r)], fill=(255, 255, 0))
    d.line([(x, r) for x, r in enumerate(top) if np.isfinite(r)], fill=(255, 0, 255))
    d.text((3, 3), c["name"].split("__")[-1][:3], fill=(255, 255, 255))
    tiles.append(im)
Hm = max(t_.height for t_ in tiles)
S = Image.new("RGB", (len(tiles) * (sl.W + 4), Hm))
for i, t_ in enumerate(tiles):
    S.paste(t_, (i * (sl.W + 4), 0))
S.save(out, quality=85)
