"""export_projection.py <model> <tris.npz> <align.json> <solution idx> <images> <out_dir> <radius_m> <key> [<key> ...]
Write what the Blender projection test needs: PLATEAU triangles within radius of the first camera (mesh.npz)
and, for each photo, its camera in the PLATEAU ENU frame (cams.json: eye, world->camera rotation in COLMAP
axes, vertical fov, image size, photo path). The pose is the global skyline fit (skyline.py fit)."""
import json
import sys
from pathlib import Path

import numpy as np
import pycolmap

model, tris_p, align, idx, images, out, radius = sys.argv[1:8]
keys = [a for a in sys.argv[8:] if not a.startswith("--")]
opts = dict(a[2:].split("=", 1) for a in sys.argv[8:] if a.startswith("--") and "=" in a)
# --level: zero each camera's roll, keeping bearing and pitch. The global fit leaves a few degrees of roll
#   per photo (018/023 +1.9, 053 -4.1 on 2026-11-23) although the photos' verticals show none; with the
#   render camera level, that roll sinks one side of the projected photo into the synthesised ground.
# --min-eye=<m>: lift eyes that the fit put lower than this above the ground (053 came out 0.9 m below).
LEVEL = "--level" in sys.argv
MIN_EYE = float(opts.get("min-eye", -1e9))


def level(Rw):
    f = Rw.T[:, 2]
    b, p = np.arctan2(f[0], f[1]), np.arcsin(f[2])
    fwd = np.array([np.sin(b) * np.cos(p), np.cos(b) * np.cos(p), np.sin(p)])
    right = np.array([np.cos(b), -np.sin(b), 0.0])
    return np.stack([right, -np.cross(right, fwd), fwd])
out = Path(out)
out.mkdir(parents=True, exist_ok=True)
rec = pycolmap.Reconstruction(model)
al = json.load(open(align))
sol = al["solutions"][int(idx)]
s, Rm, t = sol["scale"], np.array(sol["R"]), np.array(sol["t"])
R0, A = np.array(al["R_level"]), np.array(al["model_anchor"])
cams = {}
for key in keys:
    im = [i for i in rec.images.values() if key in i.name][0]
    cam = rec.cameras[im.camera_id]
    Rc = im.cam_from_world().rotation.matrix()
    Rw = Rc @ R0.T @ Rm.T
    eye = s * (R0 @ (np.array(im.projection_center()) - A)) @ Rm.T + t
    roll = float(np.degrees(np.arcsin(Rw.T[2, 0])))
    if LEVEL:
        Rw = level(Rw)
    eye[2] = max(eye[2], al["ground_z"] + MIN_EYE)
    f = cam.focal_length_y if hasattr(cam, "focal_length_y") else cam.focal_length
    fov = float(np.degrees(2 * np.arctan(cam.height / 2 / f)))
    cams[key] = {"name": im.name, "photo": str(Path(images).resolve() / im.name), "eye": eye.tolist(),
                 "Rw": Rw.tolist(), "fov_v": fov, "width": cam.width, "height": cam.height,
                 "model": str(cam.model), "params": list(map(float, cam.params))}
    cams[key]["fit_roll_deg"] = roll
    print(key, "eye", eye.round(1), "fov_v", round(fov, 1), "fit roll", round(roll, 2), cam.model, np.round(cam.params, 3))
tris = np.load(tris_p)["tris"]
e0 = np.array(cams[keys[0]]["eye"])
near = np.linalg.norm(tris.mean(1)[:, :2] - e0[:2], axis=1) < float(radius)
np.savez_compressed(out / "mesh.npz", tris=tris[near].astype(np.float32), ground=al["ground_z"])
json.dump(cams, open(out / "cams.json", "w"), indent=1)
print("triangles", int(near.sum()), "ground", al["ground_z"])
