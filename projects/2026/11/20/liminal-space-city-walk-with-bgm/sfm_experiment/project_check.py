"""project_check.py <sparse_model> <plateau_tris.npz> <align.json> <images_dir> <out_prefix> <name_key> [<name_key> ...]
For each solution in align.json and each photo: draw PLATEAU (painter's algorithm, shaded by facing) through
the photo's COLMAP camera and blend it over the photo, so building edges can be compared by eye."""
import json
import sys

import numpy as np
import pycolmap
from PIL import Image, ImageDraw

rec = pycolmap.Reconstruction(sys.argv[1])
tris = np.load(sys.argv[2])["tris"].astype(np.float64)
al = json.load(open(sys.argv[3]))
img_dir, prefix, keys = sys.argv[4], sys.argv[5], sys.argv[6:]
R0, A = np.array(al["R_level"]), np.array(al["model_anchor"])
nrm = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
cen = tris.mean(1)
W = 640
rows = []
for key in keys:
    im = [i for i in rec.images.values() if key in i.name][0]
    cam = rec.cameras[im.camera_id]
    photo = Image.open(f"{img_dir}/{im.name}").convert("RGB")
    k = W / photo.width
    H = round(photo.height * k)
    photo = photo.resize((W, H))
    cfw = im.cam_from_world()
    Rc, tc = cfw.rotation.matrix(), np.array(cfw.translation)
    row = [photo]
    for sol in al["solutions"]:
        s, Rm, t = sol["scale"], np.array(sol["R"]), np.array(sol["t"])
        # PLATEAU (world) -> model -> camera
        to_model = lambda Y: A + ((Y - t) @ Rm / s) @ R0
        eye_w = s * (R0 @ (np.array(im.projection_center()) - A)) @ Rm.T + t
        near = np.linalg.norm(cen[:, :2] - eye_w[:2], axis=1) < 600
        T = tris[near]
        Xc = to_model(T.reshape(-1, 3)) @ Rc.T + tc
        z = Xc[:, 2].reshape(-1, 3)
        ok = (z > 0.05 / s).all(1)
        uv = np.array(cam.img_from_cam(Xc)).reshape(-1, 3, 2) * k
        depth = np.linalg.norm(T.mean(1) - eye_w, axis=1)
        view = (T.mean(1) - eye_w) / depth[:, None]
        shade = np.abs((nrm[near] * view).sum(1))
        horiz = np.abs(nrm[near][:, 2]) > 0.7
        over = Image.new("RGB", (W, H), (0, 0, 0))
        mask = Image.new("L", (W, H), 0)
        d, dm = ImageDraw.Draw(over), ImageDraw.Draw(mask)
        for i in np.argsort(-depth):
            if not ok[i]:
                continue
            p = [tuple(q) for q in uv[i]]
            if max(abs(q[0]) for q in p) > 4 * W or max(abs(q[1]) for q in p) > 4 * H:
                continue
            c = int(60 + 190 * shade[i])
            d.polygon(p, fill=(c // 3, c // 2, c) if horiz[i] else (c, c // 2, c // 4), outline=(255, 255, 255))
            dm.polygon(p, fill=150)
        blend = Image.composite(over, photo, mask)
        ImageDraw.Draw(blend).text((6, 6), f"scale {s:.1f}  median {sol['median']:.2f} m", fill=(255, 255, 0))
        row.append(blend)
    rows.append(row)
cols = max(len(r) for r in rows)
H0 = max(r[0].height for r in rows)
out = Image.new("RGB", (cols * (W + 6), len(rows) * (H0 + 6)), (0, 0, 0))
for j, r in enumerate(rows):
    for i, t_ in enumerate(r):
        out.paste(t_, (i * (W + 6), j * (H0 + 6)))
out.save(prefix + "_project.jpg", quality=85)
print("saved", prefix + "_project.jpg", out.size)
