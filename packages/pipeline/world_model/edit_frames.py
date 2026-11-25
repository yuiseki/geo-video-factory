"""python -m world_model.edit_frames <edit.json> <out_dir>
Joins clips of numbered frames into one numbered sequence: cuts, crossfades, a day-to-night change inside one
move, and a fade to black. Directories in the edit list may use $VARS (expanded from the environment), so the
list carries no machine paths.

edit.json: {"size": [1280, 720], "clips": [
   {"dir": "$OUT/globe/frames", "pattern": "*.png", "first": 0, "last": 360},
   {"dir": "...", "first": 0, "last": 180, "cross": 20},            # crossfade 20 frames over the previous clip
   {"dir": "...day", "night": "...night", "mode": "wipe", "first": 0, "last": 150},
   {"black": 4},                                                     # an edit point
   {"dir": "...", "first": 0, "last": 240, "fade_in": 3, "fade_out": 30}]}
first/last count the clip's own frames in name order (last exclusive)."""
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from world_model import time_blend as tb


def frames_of(clip):
    if "black" in clip:
        return [None] * int(clip["black"])
    names = sorted(Path(os.path.expandvars(clip["dir"])).glob(clip.get("pattern", "f[0-9]*.jpg")))
    return names[clip.get("first", 0):clip.get("last", len(names))]


def schedule(lengths, crosses):
    """Start frame of each clip on the output timeline and the total length. Clip k overlaps the end of clip
    k-1 by crosses[k] frames."""
    starts, t = [], 0
    for n, c in zip(lengths, crosses):
        t -= min(c, t)
        starts.append(t)
        t += n
    return starts, t


def main(argv):
    edit = json.loads(Path(argv[0]).read_text())
    out = Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    size = tuple(edit.get("size", [1280, 720]))
    clips = edit["clips"]
    lists = [frames_of(c) for c in clips]
    nights = [frames_of(dict(c, dir=c["night"])) if "night" in c else None for c in clips]
    starts, total = schedule([len(x) for x in lists], [c.get("cross", 0) for c in clips])
    load = lambda p: (np.zeros((size[1], size[0], 3), np.float32) if p is None
                      else np.asarray(Image.open(p).convert("RGB").resize(size, Image.LANCZOS), np.float32))
    for t in range(total):
        picture = None
        for k, (clip, names, start) in enumerate(zip(clips, lists, starts)):
            i = t - start
            if not 0 <= i < len(names):
                continue
            im = load(names[i])
            if nights[k] is not None:
                w = tb.weight(i / max(len(names) - 1, 1), im.shape[:2], clip.get("mode", "wipe"),
                              clip.get("from", 0.25), clip.get("to", 0.75), clip.get("soft", 0.3))
                im = im * (1 - w[..., None]) + load(nights[k][i]) * w[..., None]
            if "fade_in" in clip and i < clip["fade_in"]:
                im = im * ((i + 1) / (clip["fade_in"] + 1))
            if "fade_out" in clip and i >= len(names) - clip["fade_out"]:
                im = im * ((len(names) - 1 - i) / clip["fade_out"])
            cross = clip.get("cross", 0)
            if picture is not None and cross and i < cross:
                a = (i + 1) / (cross + 1)
                picture = picture * (1 - a) + im * a
            else:
                picture = im
        Image.fromarray(np.clip(picture + 0.5, 0, 255).astype(np.uint8)).save(out / f"f{t:05d}.jpg", quality=94)
    print("wrote", total, "frames;", "clip starts", starts)


if __name__ == "__main__":
    main(sys.argv[1:])
