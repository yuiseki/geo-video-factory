"""make_path.py <cams.json> <key> <work_dir> <keyframes> [--fps=24]
A camera path relative to where one photo was taken. <keyframes> is "t:forward:right:up:dbearing:dpitch;..." (seconds,
metres along the photo's level heading / to its right / up, degrees added to the photo's bearing and pitch). A clamped
cubic spline runs through the keyframes (it starts and ends at rest). Writes <work_dir>/frames.json for
blender_projection.py --frames, frames in <work_dir>/f/NNNN.png."""
import json, math, sys
from pathlib import Path
import numpy as np
from scipy.interpolate import CubicSpline

cams, key, work = json.load(open(sys.argv[1])), sys.argv[2], Path(sys.argv[3])
K = np.array([[float(v) for v in k.split(":")] for k in sys.argv[4].split(";")])
opts = dict(a[2:].split("=", 1) for a in sys.argv[5:] if a.startswith("--"))
FPS = int(opts.get("fps", 24))
c = cams[key]; eye = np.array(c["eye"]); f = np.array(c["Rw"])[2]
b0, p0 = math.degrees(math.atan2(f[0], f[1])), math.degrees(math.asin(f[2]))
fh = np.array([math.sin(math.radians(b0)), math.cos(math.radians(b0)), 0.0]); rh = np.array([fh[1], -fh[0], 0.0])
sp = CubicSpline(K[:, 0], K[:, 1:], bc_type="clamped")
n = int(round(K[-1, 0] * FPS))
(work / "f").mkdir(parents=True, exist_ok=True)
frames = []
for i in range(n):
    fw, r, u, db, dp = sp(K[0, 0] + i / (n - 1) * (K[-1, 0] - K[0, 0]))
    p = eye + fw * fh + r * rh + np.array([0, 0, u])
    frames.append(dict(x=float(p[0]), y=float(p[1]), z=float(p[2]), bearing=float(b0 + db), pitch=float(p0 + dp),
                       out=str(work / "f" / f"{i:04d}.png")))
json.dump(frames, open(work / "frames.json", "w"))
print(f"photo bearing {b0:.1f} pitch {p0:.1f}; {n} frames")
