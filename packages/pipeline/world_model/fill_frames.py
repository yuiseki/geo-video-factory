"""python -m world_model.fill_frames <frames dir> <frames> [--step=1]
Writes the frames a render left out (missing f####.jpg among 0, step, 2*step, ... < frames) as a copy of the
nearest earlier frame, so that ffmpeg gets an unbroken numbered sequence f%04d at the step, renumbered from 0
into <frames dir>/seq/. Prints which frames were filled: a filled frame is a held picture, not a drawn one."""
import shutil
import sys
from pathlib import Path


def plan(have, frames, step=1):
    """For each wanted frame index, the index of the frame to use (itself, or the nearest earlier one that
    exists, or the nearest later one at the very start)."""
    wanted = list(range(0, frames, step))
    out, last = [], None
    for i in wanted:
        if i in have:
            last = i
        out.append(last)
    first = next((i for i in wanted if i in have), None)
    return [first if o is None else o for o in out]


def main(argv):
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--"))
    folder, frames = Path(argv[0]), int(argv[1])
    step = int(opts.get("step", 1))
    have = {int(f.stem[1:]) for f in folder.glob("f[0-9]*.jpg")}
    seq = folder / "seq"
    seq.mkdir(exist_ok=True)
    src = plan(have, frames, step)
    filled = [i * step for i, s in enumerate(src) if s != i * step]
    for k, s in enumerate(src):
        shutil.copyfile(folder / f"f{s:04d}.jpg", seq / f"f{k:04d}.jpg")
    print("filled", filled)


if __name__ == "__main__":
    main(sys.argv[1:])
