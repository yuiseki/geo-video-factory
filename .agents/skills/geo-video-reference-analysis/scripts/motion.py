"""Measure slow camera moves (zoom in/out, pan) in a video, including slow moves over still photos.

Every STEP seconds a pair of frames is compared: ORB features are matched and a similarity
transform (scale + shift) is fitted with RANSAC. The top 8% (titles) and bottom 22% (subtitles)
are masked so that fixed text does not decide the fit.

usage: python3 motion.py <video.mp4> <out.tsv> [step_seconds=0.5]
needs numpy and OpenCV, e.g. `uv run --with opencv-python-headless --with numpy python motion.py ...`

out.tsv: t, scale_per_s, dx_per_s, dy_per_s (px at 1920 wide), inliers, label
The printed summary gives the share of time zooming in/out, panning, static or cut, and median speeds.

Checked on synthetic clips with known moves: directions were all right, speeds read slightly low
(a 0.8-0.9 %/s zoom measured 0.65-0.8 %/s). Large fixed overlays (characters, big text, credits)
outvote the background and make a moving picture read as static, so videos built from flat
diagrams with a mascot read lower than they are.
"""
from __future__ import annotations

import subprocess
import sys

import cv2
import numpy as np

W, H = 640, 360
SCALE_TO_1920 = 1920 / W
ZOOM_T, PAN_T = 0.004, 4.0  # per second: 0.4 % zoom, 4 px (at 1920 wide) count as moving


def label(s: float, dx: float, dy: float) -> str:
    parts = []
    if s > 1 + ZOOM_T:
        parts.append('zoom_in')
    elif s < 1 - ZOOM_T:
        parts.append('zoom_out')
    # picture moving up on screen = camera moving down; report the camera's direction
    if abs(dy) >= PAN_T and abs(dy) >= abs(dx):
        parts.append('pan_down' if dy < 0 else 'pan_up')
    elif abs(dx) >= PAN_T:
        parts.append('pan_right' if dx < 0 else 'pan_left')
    return '+'.join(parts) or 'static'


def frames(src: str, step: float):
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-nostdin', '-i', src, '-vf',
                          f'fps={1 / step},scale={W}:{H},format=gray', '-f', 'rawvideo', '-'],
                         stdout=subprocess.PIPE)
    while True:
        buf = p.stdout.read(W * H)
        if len(buf) < W * H:
            break
        yield np.frombuffer(buf, np.uint8).reshape(H, W)
    p.wait()


def measure(src: str, step: float) -> list[tuple]:
    orb = cv2.ORB_create(1500)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    mask = np.zeros((H, W), np.uint8)
    mask[int(H * .08):int(H * .78), :] = 255
    centre = np.array([W / 2, H / 2])
    rows, prev = [], None
    for i, f in enumerate(frames(src, step)):
        kp, des = orb.detectAndCompute(f, mask)
        if prev is not None:
            row = (i * step, 1.0, 0.0, 0.0, 0, 'cut')
            if des is not None and prev[1] is not None and len(kp) > 20 and len(prev[0]) > 20:
                m = bf.match(prev[1], des)
                if len(m) >= 12:
                    a = np.float32([prev[0][x.queryIdx].pt for x in m])
                    b = np.float32([kp[x.trainIdx].pt for x in m])
                    M, inl = cv2.estimateAffinePartial2D(a, b, method=cv2.RANSAC, ransacReprojThreshold=2.0)
                    n = int(inl.sum()) if inl is not None else 0
                    if M is not None and n >= 12:
                        s = float(np.hypot(M[0, 0], M[1, 0])) ** (1 / step)
                        dx, dy = ((M[:, :2] @ centre + M[:, 2]) - centre) * SCALE_TO_1920 / step
                        row = (i * step, s, float(dx), float(dy), n, label(s, dx, dy))
            rows.append(row)
        prev = (kp, des)
    return rows


def summary(rows: list[tuple]) -> str:
    n = len(rows) or 1
    count: dict[str, int] = {}
    for r in rows:
        for part in r[5].split('+'):
            count[part] = count.get(part, 0) + 1
    moving = sum(1 for r in rows if r[5] not in ('static', 'cut'))
    zoom = [abs(r[1] - 1) * 100 for r in rows if 'zoom' in r[5]]
    pan = [float(np.hypot(r[2], r[3])) for r in rows if 'pan' in r[5]]
    shares = ' '.join(f'{k}={100 * v / n:.0f}%' for k, v in sorted(count.items(), key=lambda kv: -kv[1]))
    return (f'pairs {n} moving {100 * moving / n:.0f}% {shares} | '
            f'zoom median {np.median(zoom) if zoom else 0:.2f}%/s pan median {np.median(pan) if pan else 0:.0f} px/s')


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, out = sys.argv[1], sys.argv[2]
    step = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
    rows = measure(src, step)
    with open(out, 'w') as f:
        f.write('t\tscale_per_s\tdx_per_s\tdy_per_s\tinliers\tlabel\n')
        f.writelines('%.1f\t%.5f\t%.1f\t%.1f\t%d\t%s\n' % r for r in rows)
    print(summary(rows))


if __name__ == '__main__':
    main()
