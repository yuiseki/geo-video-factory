"""Four-corner outlines of the signs and screens in a photo, for pasting our own art over them.

Input is the SAM sign layer saved by people_removal.py (`<id>_signs.png`). Each connected region gets the
quadrilateral through its extreme points (top-left = min x+y, top-right = max x-y, bottom-right = max x+y,
bottom-left = min x-y), which follows a flat sign seen at an angle. `fill` = region area / quad area: near 1
for a sign face, low for merged or irregular regions that need a look by eye.

CLI:
  sign_regions.py <out_dir> <id> ...   -> <id>_signs.json next to the layers (input of sign_replace.py;
      regions with fill < MIN_FILL go under "skipped")
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


def quad_area(quad) -> float:
    q = np.asarray(quad, float)
    x, y = q[:, 0], q[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def degenerate(quad, min_corner: float = 0.1) -> bool:
    """True when a corner and its two neighbours span under `min_corner` of the quad (a triangle, a sliver):
    no homography maps a rectangle onto it. Each corner of a rectangle spans half."""
    qa = quad_area(quad)
    if qa <= 0:
        return True
    return any(quad_area([quad[k - 1], quad[k], quad[(k + 1) % 4]]) < min_corner * qa for k in range(4))


def sign_quads(mask: np.ndarray, min_area: float = 0.0005) -> list[dict]:
    """Regions of at least `min_area` of the image, largest first: {"corners", "area", "fill", "bbox"}."""
    from scipy import ndimage

    on = mask > 127
    labels, _ = ndimage.label(on)
    total = on.size
    out = []
    for i, sl in enumerate(ndimage.find_objects(labels), start=1):
        part = labels[sl] == i
        area = int(part.sum())
        if area < min_area * total:
            continue
        ys, xs = np.nonzero(part)
        xs = xs + sl[1].start
        ys = ys + sl[0].start
        s, d = xs + ys, xs - ys
        idx = [int(np.argmin(s)), int(np.argmax(d)), int(np.argmax(s)), int(np.argmin(d))]
        quad = [[int(xs[k]), int(ys[k])] for k in idx]
        qa = quad_area(quad)
        fill = round(area / qa, 3) if qa and not degenerate(quad) else 0.0
        out.append({"corners": quad, "area": area, "fill": fill,
                    "bbox": [int(sl[1].start), int(sl[0].start), int(sl[1].stop), int(sl[0].stop)]})
    return sorted(out, key=lambda q: -q["area"])


MIN_FILL = 0.8  # below this the region is merged or irregular: replacing its quad would paint past the sign


def replace_json(stem: str, quads: list[dict], size, min_fill: float = MIN_FILL) -> dict:
    """sign_replace.py input: named flat faces under "signs", the rest under "skipped" for a look by eye."""
    doc = {"width": size[0], "height": size[1], "signs": [], "skipped": []}
    for k, q in enumerate(quads):
        doc["signs" if q["fill"] >= min_fill else "skipped"].append({"name": f"{stem}_{k:02d}", **q})
    return doc


def main(argv) -> None:  # pragma: no cover
    from PIL import Image

    out_dir = Path(argv[0])
    for stem in argv[1:]:
        m = np.asarray(Image.open(out_dir / f"{stem}_signs.png").convert("L"))
        doc = replace_json(stem, sign_quads(m), (m.shape[1], m.shape[0]))
        (out_dir / f"{stem}_signs.json").write_text(json.dumps(doc, indent=1))
        print(stem, len(doc["signs"]), "signs,", len(doc["skipped"]), "skipped", flush=True)


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
