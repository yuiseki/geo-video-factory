"""check_stream.py <sparse_model> <plateau_tris.npz> <camera_018.json> <osm_shibuya_stream.json>
Compare two independent placements of the model's yaw: (a) the anchor 018's fitted bearing, (b) the direction
from 018 to the cluster of photos titled 'from Shibuya Stream' (253, 258, 299) vs the real direction to the
Shibuya Stream building. Also print scale from (b) and where the main cluster's cameras look."""
import json
import sys

import numpy as np
import pycolmap

rec = pycolmap.Reconstruction(sys.argv[1])
lon0, lat0 = np.load(sys.argv[2])["origin"]
fit = json.load(open(sys.argv[3]))["fit"]
k = np.cos(np.radians(lat0)) * 6378137 * np.pi / 180
kn = 6378137 * np.pi / 180
names, C, UP, FW, RIGHTS = [], [], [], [], []
for img in rec.images.values():
    R = img.cam_from_world().rotation.matrix()
    names.append(img.name)
    C.append(img.projection_center())
    UP.append(R.T @ np.array([0, -1.0, 0]))
    RIGHTS.append(R.T @ np.array([1.0, 0, 0]))
    FW.append(R.T @ np.array([0, 0, 1.0]))
C, FW = np.array(C), np.array(FW)
# camera x axes stay horizontal however the camera pitches: up is their common normal
up = np.linalg.svd(np.array(RIGHTS))[2][-1]
up = up if up @ np.mean(UP, 0) > 0 else -up
print("spread of camera ups (deg):", np.round(np.degrees(np.arccos(np.clip(np.array(UP) @ up, -1, 1))), 1))
zz = np.array([0, 0, 1.0])
v = np.cross(up, zz)
s_ = np.linalg.norm(v)
K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]]) / s_
a = np.arctan2(s_, up @ zz)
R0 = np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * K @ K
L = C @ R0.T
F = FW @ R0.T
ai = [i for i, n in enumerate(names) if "shibuya_crossing__018" in n][0]
st = [i for i, n in enumerate(names) if any(f"__{x}_" in n for x in ("253", "258", "299"))]
print("stream photos:", [names[i].split("__")[1][:3] for i in st])
heading = lambda f: np.degrees(np.arctan2(f[0], f[1]))
yaw_a = heading(F[ai]) - fit["bearing"]
vec = L[st].mean(0) - L[ai]
els = json.load(open(sys.argv[4]))["elements"]
pts = np.array([[(p["lon"] - lon0) * k, (p["lat"] - lat0) * kn] for el in els if "geometry" in el for p in el["geometry"]])
eye = np.array([(fit["eye"][0] - lon0) * k, (fit["eye"][1] - lat0) * kn])
real = pts.mean(0) - eye
yaw_b = heading(vec) - heading(real)
print(f"yaw from 018 bearing: {yaw_a:.1f} deg; yaw from Stream direction: {yaw_b:.1f} deg")
print(f"scale from Stream distance: {np.linalg.norm(real) / np.linalg.norm(vec[:2]):.2f} "
      f"(real {np.linalg.norm(real):.0f} m, stream bbox {pts.min(0).round()} .. {pts.max(0).round()})")
print("stream cameras look (after yaw_b):", [round((heading(F[i]) - yaw_b) % 360) for i in st])
print("018 looks (after yaw_b):", round((heading(F[ai]) - yaw_b) % 360), "fit bearing", fit["bearing"] % 360)
print("stream cameras height above 018 (model units):", np.round(L[st, 2] - L[ai, 2], 3), "horizontal", np.linalg.norm(vec[:2]).round(3))
