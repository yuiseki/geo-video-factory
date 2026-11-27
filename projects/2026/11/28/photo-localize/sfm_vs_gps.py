"""Where a GPS-prior SfM model put each camera, against the phone's own GPS fix.

    python sfm_vs_gps.py <COLMAP text model dir> <image dir> <gsi photo tile dir> <out.png> <out.json>

The model must be georeferenced (enu_origin.txt beside it, as visloc-rs writes).
The picture lays both on GSI aerial photo tiles at zoom 18 (from <gsi dir>/18/x/y.jpg):
red dots are the GPS fixes, blue dots the model's camera centres with a short line
along the viewing direction, grey lines join the two for each photo.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

Z, R_EARTH = 18, 6378137.0


def enu_to_lonlat(e, n, lon0, lat0):
    return lon0 + math.degrees(e / (R_EARTH * math.cos(math.radians(lat0)))), lat0 + math.degrees(n / R_EARTH)


def lonlat_to_px(lon, lat):
    s = 256 * 2 ** Z
    return s * (lon + 180) / 360, s * (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2


def quat_to_r(qw, qx, qy, qz):
    return np.array([
        [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
        [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
        [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)]])


def exif_lonlat(path):
    g = Image.open(path).getexif().get_ifd(0x8825)
    deg = [float(a) + float(b) / 60 + float(c) / 3600 for a, b, c in (g[2], g[4])]
    return deg[1] * (-1 if g[3] == "W" else 1), deg[0] * (-1 if g[1] == "S" else 1)


def cameras(model):
    lat0, lon0, _ = map(float, [ln for ln in (model / "enu_origin.txt").read_text().splitlines()
                                if not ln.startswith("#")][0].split())
    lines = [ln for ln in (model / "images.txt").read_text().splitlines() if not ln.startswith("#")]
    out = {}
    for ln in lines[0::2]:
        f = ln.split()
        r, t = quat_to_r(*map(float, f[1:5])), np.array(list(map(float, f[5:8])))
        c, view = -r.T @ t, r.T @ np.array([0.0, 0.0, 1.0])
        out[f[9]] = {"lonlat": enu_to_lonlat(c[0], c[1], lon0, lat0), "heading": math.degrees(math.atan2(view[0], view[1])) % 360}
    return out


def main(model, images, tiles, png, js):
    cams = cameras(Path(model))
    rows = []
    for name, c in sorted(cams.items()):
        g = exif_lonlat(Path(images) / name)
        dx = (c["lonlat"][0] - g[0]) * R_EARTH * math.cos(math.radians(g[1])) * math.pi / 180
        dy = (c["lonlat"][1] - g[1]) * R_EARTH * math.pi / 180
        rows.append({"image": name, "gps": g, "sfm": c["lonlat"], "heading": round(c["heading"], 1),
                     "east_m": round(dx, 1), "north_m": round(dy, 1), "off_m": round(math.hypot(dx, dy), 1)})
    pts = [lonlat_to_px(*r["gps"]) for r in rows] + [lonlat_to_px(*r["sfm"]) for r in rows]
    x0, y0 = int(min(p[0] for p in pts)) - 120, int(min(p[1] for p in pts)) - 120
    x1, y1 = int(max(p[0] for p in pts)) + 120, int(max(p[1] for p in pts)) + 120
    img = Image.new("RGB", (x1 - x0, y1 - y0), (40, 40, 40))
    for tx in range(x0 // 256, x1 // 256 + 1):
        for ty in range(y0 // 256, y1 // 256 + 1):
            f = Path(tiles) / str(Z) / str(tx) / f"{ty}.jpg"
            if f.exists():
                img.paste(Image.open(f).convert("RGB"), (tx * 256 - x0, ty * 256 - y0))
    d = ImageDraw.Draw(img)
    for r in rows:
        gx, gy = (v - o for v, o in zip(lonlat_to_px(*r["gps"]), (x0, y0)))
        sx, sy = (v - o for v, o in zip(lonlat_to_px(*r["sfm"]), (x0, y0)))
        d.line([gx, gy, sx, sy], fill=(200, 200, 200), width=2)
        h = math.radians(r["heading"])
        d.line([sx, sy, sx + 30 * math.sin(h), sy - 30 * math.cos(h)], fill=(80, 160, 255), width=3)
        d.ellipse([gx - 5, gy - 5, gx + 5, gy + 5], fill=(255, 60, 60))
        d.ellipse([sx - 5, sy - 5, sx + 5, sy + 5], fill=(80, 160, 255))
    img.save(png)
    off = sorted(r["off_m"] for r in rows)
    Path(js).write_text(json.dumps({"median_off_m": off[len(off) // 2], "max_off_m": off[-1], "rows": rows}, indent=1))
    print(len(rows), "cameras, offset from GPS median", off[len(off) // 2], "m, max", off[-1], "m")


if __name__ == "__main__":
    main(*sys.argv[1:6])
