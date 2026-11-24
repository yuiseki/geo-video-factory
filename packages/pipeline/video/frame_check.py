"""frame_check.py <frames dir> [min mean 0-255]
Lists the rendered frames that are darker than the limit (default 25, a daylight scene; about 6 for a night scene)
and exits 1 if there is any. A renderer that runs out of a GPU buffer writes a black or near-black frame and still
exits 0, so a finished render is only trusted after this has looked at every frame."""
import sys
from pathlib import Path

from PIL import Image, ImageStat


def mean_level(path):
    """Mean of R, G and B over a small copy of the frame, 0-255."""
    return sum(ImageStat.Stat(Image.open(path).convert("RGB").resize((96, 72))).mean) / 3


def dark_frames(folder, limit=25.0):
    """(number of frames, names of the frames darker than the limit). No frames at all is an error: an empty
    directory must not read as a clean render."""
    paths = sorted(Path(folder).glob("*.png"))
    if not paths:
        raise FileNotFoundError(f"no frames (*.png) in {folder}")
    return len(paths), [p.stem for p in paths if mean_level(p) < limit]


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    total, dark = dark_frames(argv[0], float(argv[1]) if len(argv) > 1 else 25.0)
    print(total, "frames,", len(dark), "dark", dark[:5], dark[-5:])
    return 1 if dark else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
