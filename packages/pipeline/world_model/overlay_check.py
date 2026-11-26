"""python -m world_model.overlay_check <cams.json> <scene tris.npz> <out.jpg> [--columns=3] <key>...

Draw the outlines of the geometry prior over the photos, as each camera in
cams.json sees it, and tile them. This is the check that a pose is right: the
red building edges must sit on the building edges of the photo. A top view
cannot show a camera that is a few degrees or metres off.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from photos import photo_guard
from photos.photo_store import camera_photo  # a camera names its photo by ref, or by path
from world_model import surface_atlas as sa


def edges(depth, jump=0.08):
    """True where the depth map steps by more than `jump` of its own value (or meets the sky)."""
    d = np.where(np.isfinite(depth), depth, 1e6)
    e = np.zeros(d.shape, bool)
    e[:, 1:] |= np.abs(d[:, 1:] - d[:, :-1]) > jump * np.minimum(d[:, 1:], d[:, :-1])
    e[1:, :] |= np.abs(d[1:, :] - d[:-1, :]) > jump * np.minimum(d[1:, :], d[:-1, :])
    return e


def main(argv):
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--"))
    cams_path, scene, out, *keys = [a for a in argv if not a.startswith("--")]
    cams = json.loads(Path(cams_path).read_text())
    tris = np.load(scene)["tris"].astype(np.float64)
    cols = int(opts.get("columns", 3))
    tiles = []
    for key in keys or sorted(cams):
        cam = cams[key]
        scale = 640 / cam["width"]
        e = edges(sa.depth_buffer(tris, cam, scale=scale))
        with photo_guard.open_photo(camera_photo(cam)) as im:
            rgb = np.asarray(im.convert("RGB").resize((e.shape[1], e.shape[0]))).copy()
        rgb[e] = (255, 0, 0)
        tile = Image.new("RGB", (640, 480))
        im = Image.fromarray(rgb)
        im.thumbnail((640, 480))
        tile.paste(im, (0, 0))
        tiles.append(tile)
        print(key)
    rows = -(-len(tiles) // cols)
    sheet = Image.new("RGB", (cols * 640, rows * 480))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * 640, (i // cols) * 480))
    sheet.save(out, quality=88)


if __name__ == "__main__":
    main(sys.argv[1:])
