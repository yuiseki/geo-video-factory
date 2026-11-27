"""python -m world_model.truth_view grid <photo> <out.jpg> [--width=1224] [--crop=u,v,r]
   python -m world_model.truth_view draw <camera_truth.json> <out_dir>
The pictures a person places a photo with, and checks a kept camera by (camera_truth/README.md).

grid: the photo under a pixel grid labelled in full-resolution pixels, for reading off where a roof corner is;
--crop=u,v,r shows the square of half-size r around (u, v) at full resolution, for reading it closely.
draw: every photo of a camera_truth file with its PLATEAU buildings (buildings.plateau_building) drawn through its
kept camera, one colour per building (the picked ones first, then those in `seen`, drawn to check against but
not picked), and the picked pixels ringed: the picture to look at before keeping a camera."""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from world_model.corner_pose import project

Image.MAX_IMAGE_PIXELS = None
COLOURS = [(255, 0, 0), (0, 120, 255), (0, 200, 0), (255, 160, 0), (200, 0, 200)]


def grid(photo, out, width=1224, crop=None):
    im = Image.open(photo).convert("RGB")
    if crop:
        u, v, r = crop
        im, s, x0, y0 = im.crop((u - r, v - r, u + r, v + r)), 1.0, u - r, v - r
        step = 50
    else:
        s = width / im.width
        im, x0, y0 = im.resize((width, round(im.height * s))), 0, 0
        step = 50
    d = ImageDraw.Draw(im)
    for x in range(0, im.width, step):
        d.line([(x, 0), (x, im.height)], fill=(255, 255, 0), width=2 if x % (5 * step) == 0 else 1)
        if x % (2 * step) == 0:
            d.text((x + 2, 2), str(int(x0 + x / s)), fill=(255, 0, 0))
    for y in range(0, im.height, step):
        d.line([(0, y), (im.width, y)], fill=(255, 255, 0), width=2 if y % (5 * step) == 0 else 1)
        if y % (2 * step) == 0:
            d.text((2, y + 2), str(int(y0 + y / s)), fill=(255, 0, 0))
    im.save(out, quality=90)
    return Path(out)


def draw(photo, buildings, base, out, scale=0.5):
    """The photo with each building's triangles (dict name -> (n, 3, 3) in the truth's frame) drawn through the
    photo's kept camera, and its picked points ringed."""
    im = Image.open(Path(base) / photo["file"]).convert("RGB")
    cam = dict(photo["camera"], width=photo["width"], height=photo["height"])
    d = ImageDraw.Draw(im)
    for colour, tris in zip(COLOURS * 9, buildings.values()):
        for t in np.asarray(tris, float):
            pc = (t - np.asarray(cam["eye"])) @ np.asarray(cam["Rw"]).T
            if (pc[:, 2] <= 0.5).any():
                continue
            p = project(cam, t)
            d.line([tuple(p[0]), tuple(p[1]), tuple(p[2]), tuple(p[0])], fill=colour, width=3)
    for _P, (u, v) in photo.get("points", []):
        d.ellipse((u - 14, v - 14, u + 14, v + 14), outline=(0, 255, 0), width=5)
    if scale != 1.0:
        im = im.resize((round(im.width * scale), round(im.height * scale)))
    im.save(out, quality=88)
    return Path(out)


def main(argv):
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in argv if a.startswith("--"))
    args = [a for a in argv if not a.startswith("--")]
    if len(args) == 3 and args[0] == "grid":
        crop = tuple(int(v) for v in opts["crop"].split(",")) if opts.get("crop") else None
        print(grid(args[1], args[2], int(opts.get("width", 1224)), crop))
    elif len(args) == 3 and args[0] == "draw":
        from buildings.plateau_building import building_triangles
        path = Path(args[1]); doc = json.loads(path.read_text())
        out_dir = Path(args[2]); out_dir.mkdir(parents=True, exist_ok=True)
        for photo in doc["photos"]:
            names = dict(photo["buildings"], **photo.get("seen", {}))     # picked, then only drawn
            tris = building_triangles(list(names.values()), doc["origin"])
            shown = {k: tris[g] for k, g in names.items()}
            print(draw(photo, shown, path.parent, out_dir / (Path(photo["file"]).stem + ".jpg")))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
