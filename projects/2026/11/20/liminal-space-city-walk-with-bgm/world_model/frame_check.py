"""frame_check.py <frames dir> [--tol=0.3] [--move]
Frames of one camera move whose brightness jumps away from their neighbours: a renderer that lost its
textures draws a black or a dimmed frame and still reports success. Prints the odd frames; with --move
renames each to bad_<name> so that a resumable render draws it again."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def odd_frames(means, window=4, tol=0.3):
    """Indices whose value is more than `tol` (relative) from the median of the `window` frames on each side."""
    means = np.asarray(means, float)
    out = []
    for i, m in enumerate(means):
        near = np.r_[means[max(0, i - window):i], means[i + 1:i + 1 + window]]
        if len(near) and abs(m - np.median(near)) > tol * max(np.median(near), 1.0):
            out.append(i)
    return out


def main(argv):
    opts = dict((a[2:].split("=", 1) + ["1"])[:2] for a in argv if a.startswith("--"))
    folder = Path([a for a in argv if not a.startswith("--")][0])
    files = sorted(folder.glob("f[0-9]*.jpg"))
    means = [float(np.asarray(Image.open(f).convert("L").resize((64, 36))).mean()) for f in files]
    bad = odd_frames(means, tol=float(opts.get("tol", 0.3)))
    for i in bad:
        print("odd", files[i].name, round(means[i], 1))
        if "move" in opts:
            n = 0
            while (folder / f"bad{n}_{files[i].name}").exists():
                n += 1
            files[i].rename(folder / f"bad{n}_{files[i].name}")
    print(len(bad), "odd of", len(files))


if __name__ == "__main__":
    main(sys.argv[1:])
