"""python -m world_model.time_blend <day frames dir> <night frames dir> <out_dir> [--mode=fade|wipe|rise] [--from=0.3] [--to=0.7]
       [--soft=0.25] [--reverse]
One camera move rendered through two time layers, joined into a move during which the time changes.
fade: the whole picture; wipe: an edge crosses from the left; rise: the night climbs from the bottom.
--from and --to are fractions of the move. --reverse starts in the second layer's order (night to day is
done by swapping the two directories). Frames are matched by name; a name missing on either side is skipped."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def weight(frac, shape, mode="fade", start=0.3, end=0.7, soft=0.25):
    """How much of the second layer each pixel shows (h x w, 0..1) at fraction frac of the move."""
    p = float(np.clip((frac - start) / max(end - start, 1e-9), 0, 1))
    p = p * p * (3 - 2 * p)
    h, w = shape
    if mode == "fade":
        return np.full(shape, p, np.float32)
    if mode == "wipe":
        u = np.broadcast_to(np.linspace(0, 1, w, dtype=np.float32), shape)
    elif mode == "rise":
        u = np.broadcast_to(np.linspace(1, 0, h, dtype=np.float32)[:, None], shape)
    else:
        raise ValueError(mode)
    # the soft edge starts off the picture and ends off it, so that both ends are one pure layer
    return np.clip((p * (1 + soft) - u) / soft, 0, 1).astype(np.float32)


def mix(a, b, w):
    return (a.astype(np.float32) * (1 - w[..., None]) + b.astype(np.float32) * w[..., None] + 0.5).astype(np.uint8)


def main(argv):
    opts = dict((a[2:].split("=", 1) + ["1"])[:2] for a in argv if a.startswith("--"))
    a_dir, b_dir, out = (Path(a) for a in argv if not a.startswith("--"))
    out.mkdir(parents=True, exist_ok=True)
    names = sorted(f.name for f in a_dir.glob("f[0-9]*.jpg") if (b_dir / f.name).exists())
    for i, name in enumerate(names):
        a, b = np.asarray(Image.open(a_dir / name).convert("RGB")), np.asarray(Image.open(b_dir / name).convert("RGB"))
        w = weight(i / max(len(names) - 1, 1), a.shape[:2], opts.get("mode", "fade"), float(opts.get("from", 0.3)),
                   float(opts.get("to", 0.7)), float(opts.get("soft", 0.25)))
        Image.fromarray(mix(a, b, w)).save(out / name, quality=93)
    print("blended", len(names), "frames")


if __name__ == "__main__":
    main(sys.argv[1:])
