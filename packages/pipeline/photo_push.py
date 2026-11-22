"""Slow push-in on a still photo (Ken Burns), drawn at sub-pixel positions.

ffmpeg's zoompan crops at whole pixels, so a slow push-in (8% over 5.5 s) judders: on a 2026-11-23 test
the mean second temporal difference of the frames was 6.6 with zoompan on a 2x canvas, 3.1 on a 4x canvas,
and 1.2 with the frames drawn here. The photo is first shrunk to the output window with Lanczos, so the
affine transform only ever enlarges (by up to `zoom`) and does not alias.

CLI (needs ffmpeg):
  photo_push.py <photo> <out.mp4> [--focus=0.5] [--zoom=0.08] [--seconds=5.5] [--fps=24] [--size=1280x720] [--pan=0.15]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def cover_window(src_size, out_size, focus: float = 0.5):
    """(x, y, w, h) of the largest window with the output's shape inside the photo: centred across, and
    placed at `focus` (0 top - 1 bottom) along the side that has room, clamped inside the photo."""
    sw, sh = src_size
    ow, oh = out_size
    if sw / sh > ow / oh:
        w, h = sh * ow / oh, float(sh)
        return (sw - w) / 2, 0, w, h
    w, h = float(sw), sw * oh / ow
    return 0, min(max(0.0, sh * focus - h / 2), sh - h), w, h


def affine_at(window, out_size, zoom: float, t: float, pan: float = 0.0):
    """Pillow AFFINE coefficients (output pixel -> photo) for progress t in [0, 1]: the view narrows from the
    whole window to 1 / (1 + zoom) of it, around the window's centre. Not rounded.
    pan (e.g. 0.15) also turns the head: the view starts 1 / (1 + |pan|) of the window and its centre slides
    across the spare width, left to right for pan > 0 and right to left for pan < 0, staying inside."""
    x, y, w, h = window
    p = abs(pan)
    z = 1 + p + zoom * t
    cw, ch = w / z, h / z
    s = cw / out_size[0]
    cx = x + w / 2
    if p:
        cx += (1 if pan > 0 else -1) * (t - 0.5) * (w - w / (1 + p))
    return (s, 0, cx - cw / 2, 0, s, y + (h - ch) / 2)


def push_in_frames(img: Image.Image, out_size, focus: float, zoom: float, n: int, pan: float = 0.0):
    """n RGB frames of the push-in (with an optional sideways pan, see affine_at)."""
    win = cover_window(img.size, out_size, focus)
    k = out_size[0] / win[2]
    small = img.convert("RGB").resize((max(out_size[0], round(img.size[0] * k)),
                                       max(out_size[1], round(img.size[1] * k))), Image.LANCZOS)
    win = tuple(v * k for v in win)
    for i in range(n):
        yield small.transform(out_size, Image.AFFINE, affine_at(win, out_size, zoom, i / n, pan), Image.BICUBIC)


def temporal_roughness(frames) -> float:
    """Mean |f[i+1] - 2 f[i] + f[i-1]| over pixels and frames: 0 for still or steadily moving frames,
    large for frames that step back and forth (judder)."""
    f = np.asarray(frames, np.float64)
    return float(np.abs(f[2:] - 2 * f[1:-1] + f[:-2]).mean())


def write_push_in(photo: Path, out: Path, focus=0.5, zoom=0.08, seconds=5.5, fps=24,
                  size=(1280, 720), crf=12, pan=0.0) -> None:  # pragma: no cover
    """Encode the push-in as an H.264 clip (near-lossless by default, for later editing)."""
    n = int(seconds * fps)
    enc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{size[0]}x{size[1]}", "-r", str(fps), "-i", "-", "-c:v", "libx264",
                            "-crf", str(crf), "-preset", "fast", "-pix_fmt", "yuv420p", str(out)],
                           stdin=subprocess.PIPE)
    for frame in push_in_frames(Image.open(photo), size, focus, zoom, n, pan):
        enc.stdin.write(frame.tobytes())
    enc.stdin.close()
    if enc.wait() != 0:
        raise SystemExit(f"encoding {out} failed")


def main(argv) -> None:  # pragma: no cover
    opts = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in argv if a.startswith("--") and "=" in a}
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 2:
        raise SystemExit(__doc__)
    w, h = (int(v) for v in opts.get("--size", "1280x720").split("x"))
    write_push_in(Path(args[0]), Path(args[1]), float(opts.get("--focus", 0.5)), float(opts.get("--zoom", 0.08)),
                  float(opts.get("--seconds", 5.5)), int(opts.get("--fps", 24)), (w, h), pan=float(opts.get("--pan", 0)))


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
