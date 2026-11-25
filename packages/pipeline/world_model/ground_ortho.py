"""python -m world_model.ground_ortho <work_dir> <out_dir> [--radius=300] [--zoom=18] [--z=<ground height>] [--dim=1.0] [--centre=x,y]

The ground of the world model: the GSI seamless aerial photo laid flat at one height, as an OBJ with its texture.
<work_dir>/buildings.npz gives the origin of the local east/north/up frame (geometry_map.py).
The photo is not a true ortho (roofs lean away from the nadir), which does not matter where the buildings stand
on top of it, and it shows the cars and people of its day at about half a metre per pixel.
--dim darkens it for a night scene. Source: 国土地理院 シームレス空中写真 (credit it wherever the render is shown).
"""
import io
import math
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

from world_model.geometry_map import to_enu

URL = "https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{z}/{x}/{y}.jpg"


def tile_of(lon, lat, z):
    n = 2 ** z
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def lonlat_of(x, y, z):
    n = 2 ** z
    return x / n * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))


def main(argv):
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--"))
    work, out = [Path(a) for a in argv if not a.startswith("--")][:2]
    out.mkdir(parents=True, exist_ok=True)
    origin = np.load(work / "buildings.npz")["origin"]
    z, radius = int(opts.get("zoom", 18)), float(opts.get("radius", 300))
    cx, cy = (float(v) for v in opts.get("centre", "0,0").split(","))
    lon0, lat0 = float(origin[0]), float(origin[1])
    # metres to degrees near the origin, only to decide which tiles to fetch
    dlat, dlon = 1 / 111320.0, 1 / (111320.0 * math.cos(math.radians(lat0)))
    xa, ya = tile_of(lon0 + (cx - radius) * dlon, lat0 + (cy + radius) * dlat, z)
    xb, yb = tile_of(lon0 + (cx + radius) * dlon, lat0 + (cy - radius) * dlat, z)
    x0, x1, y0, y1 = int(xa), int(xb), int(ya), int(yb)
    cache = out / "tiles"
    cache.mkdir(exist_ok=True)
    mosaic = Image.new("RGB", ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256))
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            f = cache / f"{z}_{x}_{y}.jpg"
            if not f.exists():
                req = urllib.request.Request(URL.format(z=z, x=x, y=y), headers={"User-Agent": "geo-video-factory"})
                f.write_bytes(urllib.request.urlopen(req, timeout=30).read())
            mosaic.paste(Image.open(io.BytesIO(f.read_bytes())).convert("RGB"), ((x - x0) * 256, (y - y0) * 256))
    dim = float(opts.get("dim", 1.0))
    if dim != 1.0:
        mosaic = Image.fromarray((np.asarray(mosaic) * dim).clip(0, 255).astype(np.uint8))
    mosaic.save(out / "ground.jpg", quality=92)
    height = float(opts.get("z", 0.0))
    # a grid, not one quad: web mercator against a local tangent frame is close to affine here but not exactly
    steps = 8
    lines, grid = ["mtllib model.mtl", "usemtl ground"], {}
    nx, ny = x1 - x0 + 1, y1 - y0 + 1
    k = 0
    for j in range(steps + 1):
        for i in range(steps + 1):
            u, v = i / steps, j / steps
            lon, lat = lonlat_of(x0 + u * nx, y0 + v * ny, z)
            e, n = to_enu([(lon, lat)], origin)[0]
            lines.append("v %.3f %.3f %.3f" % (e, n, height))
            lines.append("vt %.6f %.6f" % (u, 1 - v))
            k += 1
            grid[i, j] = k
    for j in range(steps):
        for i in range(steps):
            a, b, c, d = grid[i, j], grid[i + 1, j], grid[i + 1, j + 1], grid[i, j + 1]
            lines.append(f"f {a}/{a} {d}/{d} {c}/{c}")
            lines.append(f"f {a}/{a} {c}/{c} {b}/{b}")
    (out / "model.obj").write_text("\n".join(lines) + "\n")
    (out / "model.mtl").write_text("newmtl ground\nKd 1 1 1\nmap_Kd ground.jpg\n")
    print("tiles", nx, "x", ny, "at zoom", z, "->", mosaic.size)


if __name__ == "__main__":
    main(sys.argv[1:])
