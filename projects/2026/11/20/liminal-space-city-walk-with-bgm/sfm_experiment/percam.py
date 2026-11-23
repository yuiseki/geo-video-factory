"""percam.py <model> <tris.npz> <align.json> <sky_dir> <images> <out_dir> <solution idx> [<key> ...]
Per-photo camera fit to PLATEAU skylines (experiment). Start from the global similarity, express each camera
as (world->camera rotation Rw, eye in PLATEAU metres), then refine 3 rotation + 3 position parameters by Powell
on that photo's skyline mismatch, with a weak pull back to the start position (20 m ~ 1 unit of cost x 0.02).
Writes cameras.json (Rw, eye, cost before/after) and a projection sheet for the listed keys (all if none)."""
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).parent))
import skyline as sl  # noqa: E402

model, tris_p, align, sky, images, out, idx = sys.argv[1:8]
keys = sys.argv[8:]
out = Path(out)
out.mkdir(parents=True, exist_ok=True)
pr = sl.Problem(model, tris_p, align, Path(sky) / "skylines.json")
sol = pr.al["solutions"][int(idx)]
s, Rm, t = sol["scale"], np.array(sol["R"]), np.array(sol["t"])
W = sl.W


def skyline_cost(top, c):
    r = c["rows"]
    m = ~np.isnan(r)
    rt = np.where(np.isfinite(top), np.clip(top, -0.2 * c["H"], c["H"]), 0.0)
    e = np.abs(rt[m] - r[m]) / c["H"]
    return float(np.mean(np.minimum(e, 0.15)))


def render(c, Pw, Rw, eye):
    Xc = (Pw - eye) @ Rw.T
    ok = Xc[:, 2] > 0.3
    uv = np.asarray(c["cam"].img_from_cam(Xc[ok])) * c["k"]
    u = np.floor(uv[:, 0]).astype(int)
    v = uv[:, 1]
    inb = (u >= 0) & (u < W) & (v > -c["H"]) & (v < 2 * c["H"])
    top = np.full(W, np.inf)
    np.minimum.at(top, u[inb], v[inb])
    return top


results = {}
cams = [c for c in pr.cams if not keys or any(k in c["name"] for k in keys)]
for c in cams:
    t0 = time.time()
    Rw = c["Rc"] @ pr.R0.T @ Rm.T
    eye = s * (pr.R0 @ (c["C"] - pr.A)) @ Rm.T + t
    # points that could matter: in front, within a wide frustum at the start pose
    Xc = (pr.P - eye) @ Rw.T
    front = Xc[:, 2] > 0.3
    uv = np.full((len(pr.P), 2), 1e9)
    uv[front] = np.asarray(c["cam"].img_from_cam(Xc[front])) * c["k"]
    sel = front & (uv[:, 0] > -W) & (uv[:, 0] < 2 * W) & (uv[:, 1] > -2 * c["H"]) & (uv[:, 1] < 2 * c["H"])
    Pw = pr.P[sel]

    def unpack(x):
        return sl.rotvec(np.radians(x[:3])) @ Rw, eye + x[3:]

    def f(x):
        R2, e2 = unpack(x)
        return skyline_cost(render(c, Pw, R2, e2), c) + 0.02 * (np.linalg.norm(x[3:]) / 20) ** 2

    before = f(np.zeros(6))
    best = (before, np.zeros(6))
    for yaw in (-4, -2, 0, 2, 4):
        for dz in (-6, -3, 0, 3, 6):
            x = np.array([0, yaw, 0, 0, 0, dz], float)
            v_ = f(x)
            if v_ < best[0]:
                best = (v_, x)
    # a camera placed inside a PLATEAU building sees walls everywhere: try stepping out horizontally
    for dx in range(-15, 16, 5):
        for dy in range(-15, 16, 5):
            for yaw in (-3, 0, 3):
                x = best[1].copy()
                x[1] += yaw
                x[3] += dx
                x[4] += dy
                v_ = f(x)
                if v_ < best[0]:
                    best = (v_, x)
    res = minimize(f, best[1], method="Powell",
                   options=dict(xtol=1e-2, ftol=1e-5, maxfev=600, direc=np.diag([0.5, 0.5, 0.5, 2, 2, 2])))
    R2, e2 = unpack(res.x)
    results[c["name"]] = {"Rw": R2.tolist(), "eye": e2.tolist(), "before": before, "after": float(res.fun),
                          "dx": res.x.round(3).tolist()}
    print(f"{c['name'].split('__')[-1][:3]}  {before:.4f} -> {res.fun:.4f}  rot {res.x[:3].round(1)} deg  "
          f"move {res.x[3:].round(1)} m  points {len(Pw)}  {time.time() - t0:.1f}s", flush=True)
json.dump(results, open(out / "cameras.json", "w"), indent=1)

# projection sheet: photo | before | after (PLATEAU painted with the painter's algorithm)
tris = np.load(tris_p)["tris"].astype(np.float64)
nrm = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
cen = tris.mean(1)
VW = 480


def paint(c, Rw, eye, photo):
    k = VW / photo.width
    H = round(photo.height * k)
    base = photo.resize((VW, H))
    near = np.linalg.norm(cen[:, :2] - eye[:2], axis=1) < 600
    T = tris[near]
    Xc = (T.reshape(-1, 3) - eye) @ Rw.T
    ok = (Xc[:, 2].reshape(-1, 3) > 0.3).all(1)
    uv = np.asarray(c["cam"].img_from_cam(np.where(Xc[:, 2:3] > 0.3, Xc, np.array([0, 0, 1.0])))).reshape(-1, 3, 2) * (
        c["k"] * VW / W)
    depth = np.linalg.norm(T.mean(1) - eye, axis=1)
    view = (T.mean(1) - eye) / depth[:, None]
    shade = np.abs((nrm[near] * view).sum(1))
    horiz = np.abs(nrm[near][:, 2]) > 0.7
    over, mask = Image.new("RGB", (VW, H)), Image.new("L", (VW, H), 0)
    d, dm = ImageDraw.Draw(over), ImageDraw.Draw(mask)
    for i in np.argsort(-depth):
        if not ok[i]:
            continue
        p = [tuple(q) for q in uv[i]]
        if max(abs(q[0]) for q in p) > 4 * VW or max(abs(q[1]) for q in p) > 4 * H:
            continue
        cc = int(60 + 190 * shade[i])
        d.polygon(p, fill=(cc // 3, cc // 2, cc) if horiz[i] else (cc, cc // 2, cc // 4), outline=(255, 255, 255))
        dm.polygon(p, fill=140)
    return Image.composite(over, base, mask)


rows = []
for c in cams:
    r = results[c["name"]]
    photo = Image.open(Path(images) / c["name"]).convert("RGB")
    Rw0 = c["Rc"] @ pr.R0.T @ Rm.T
    eye0 = s * (pr.R0 @ (c["C"] - pr.A)) @ Rm.T + t
    k = VW / photo.width
    a = paint(c, Rw0, eye0, photo)
    b = paint(c, np.array(r["Rw"]), np.array(r["eye"]), photo)
    ImageDraw.Draw(a).text((4, 4), f"{c['name'].split('__')[-1][:3]} global {r['before']:.3f}", fill=(255, 255, 0))
    ImageDraw.Draw(b).text((4, 4), f"per photo {r['after']:.3f}", fill=(255, 255, 0))
    rows.append((photo.resize((VW, round(photo.height * k))), a, b))
Hm = max(x[0].height for x in rows)
S = Image.new("RGB", (3 * (VW + 4), len(rows) * (Hm + 4)))
for j, row in enumerate(rows):
    for i, im in enumerate(row):
        S.paste(im, (i * (VW + 4), j * (Hm + 4)))
S.save(out / "percam_project.jpg", quality=82)
print("saved", out / "percam_project.jpg")
