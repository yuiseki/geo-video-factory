"""camera_path.py <cams.json> <key> <work_dir> <keyframes> [--fps=24]
A camera path relative to where one photo was taken, for a renderer that projects that photo onto the scene: the
picture is only right near the photo's own viewpoint, so the path is written as small offsets from it.
<keyframes> is "t:forward:right:up:dbearing:dpitch;..." (seconds, metres along the photo's level heading / to its
right / up, degrees added to the photo's bearing and pitch). A clamped cubic spline runs through the keyframes, so
the camera starts and ends at rest. Writes <work_dir>/frames.json, one entry per frame with the position, bearing,
pitch and the PNG to write (<work_dir>/f/NNNN.png).
<cams.json> maps a photo key to {"eye": [east, north, up], "Rw": 3x3 world-to-camera rotation whose third row is
the viewing direction, ...}."""
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicSpline

FIELDS = "t:forward:right:up:dbearing:dpitch"


def photo_pose(cam):
    """(eye, bearing, pitch) of a cams.json entry: degrees clockwise from north, degrees above the horizon."""
    forward = np.asarray(cam["Rw"], float)[2]
    bearing = math.degrees(math.atan2(forward[0], forward[1]))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, forward[2]))))
    return np.asarray(cam["eye"], float), bearing, pitch


def parse_keyframes(text):
    """The keyframe string as an (n, 6) array. Refuses what the spline would turn into nonsense."""
    rows = [k.split(":") for k in text.split(";") if k]
    if any(len(r) != 6 for r in rows):
        raise ValueError(f"every keyframe is {FIELDS}: {text!r}")
    keys = np.array(rows, float)
    if len(keys) < 2:
        raise ValueError(f"a path needs at least two keyframes: {text!r}")
    if (np.diff(keys[:, 0]) <= 0).any():
        raise ValueError(f"keyframe times must increase: {text!r}")
    return keys


def path_frames(cam, keys, fps=24, frames_dir=None):
    """One dict per frame: x, y, z, bearing, pitch (and out, the PNG path, when frames_dir is given)."""
    eye, bearing, pitch = photo_pose(cam)
    b = math.radians(bearing)
    ahead = np.array([math.sin(b), math.cos(b), 0.0])       # level, so that "forward" never climbs or digs
    right = np.array([ahead[1], -ahead[0], 0.0])
    spline = CubicSpline(keys[:, 0], keys[:, 1:], bc_type="clamped")
    t0, t1 = keys[0, 0], keys[-1, 0]
    n = int(round(t1 * fps))
    frames = []
    for i in range(n):
        fw, r, u, db, dp = spline(t0 + i / (n - 1) * (t1 - t0))
        p = eye + fw * ahead + r * right + np.array([0.0, 0.0, u])
        frame = dict(x=float(p[0]), y=float(p[1]), z=float(p[2]), bearing=float(bearing + db), pitch=float(pitch + dp))
        if frames_dir is not None:
            frame["out"] = str(Path(frames_dir) / f"{i:04d}.png")
        frames.append(frame)
    return frames


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--"))
    if len(args) != 4:
        raise SystemExit(__doc__)
    cams, key, work = json.loads(Path(args[0]).read_text()), args[1], Path(args[2])
    if key not in cams:
        raise SystemExit(f"no photo {key!r} in {args[0]}: it has {sorted(cams)}")
    (work / "f").mkdir(parents=True, exist_ok=True)
    frames = path_frames(cams[key], parse_keyframes(args[3]), int(opts.get("fps", 24)), work / "f")
    (work / "frames.json").write_text(json.dumps(frames))
    _, bearing, pitch = photo_pose(cams[key])
    print(f"photo bearing {bearing:.1f} pitch {pitch:.1f}; {len(frames)} frames")


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
