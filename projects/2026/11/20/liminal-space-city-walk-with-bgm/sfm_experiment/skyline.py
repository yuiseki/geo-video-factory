"""skyline.py: fit a COLMAP model to PLATEAU by matching skylines (experiment).

photo skyline: per column, the first row from the top that is not sky. Sky = the region connected to the top
edge whose pixels are smooth (small gradient) and close in colour to the top rows.
PLATEAU skyline: per column, the smallest row of PLATEAU points (sampled along raised triangle edges and on
roofs) projected through the photo's COLMAP camera after the model->PLATEAU similarity.

usage:
  skyline.py masks  <model> <images> <out_dir>                  sky masks + skylines (cache) and a contact sheet
  skyline.py score  <model> <tris.npz> <align.json> <out_dir>    cost of each saved solution
  skyline.py fit    <model> <tris.npz> <align.json> <out_dir> <solution index>   optimise 7 DoF from a solution
"""
import json
import sys
from pathlib import Path

import numpy as np
import pycolmap
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

W = 320


def sky_profile(photo: Image.Image):
    """(skyline rows (nan where the column has no sky at the top), sky mask) at width W."""
    k = W / photo.width
    H = round(photo.height * k)
    im = np.asarray(photo.convert("RGB").resize((W, H), Image.LANCZOS), np.float32)
    lum = im.mean(2)
    g = np.hypot(ndimage.sobel(lum, 0), ndimage.sobel(lum, 1)) / 8
    top = im[:max(3, H // 40)].reshape(-1, 3)
    ref = np.median(top, 0)
    spread = np.percentile(np.linalg.norm(top - ref, axis=1), 80)
    close = np.linalg.norm(im - ref, axis=2) < max(18.0, 2.5 * spread) + 0.15 * ref.mean()
    cand = close & (g < 6)
    cand = ndimage.binary_opening(cand, iterations=1)
    lab, _ = ndimage.label(cand)
    ids = np.unique(lab[0][lab[0] > 0])
    sky = np.isin(lab, ids)
    sky = ndimage.binary_closing(sky, iterations=2) & np.isin(lab, ids) | sky
    rows = np.full(W, np.nan)
    for x in range(W):
        col = sky[:, x]
        if col[0]:
            nz = np.flatnonzero(~col)
            if len(nz) and nz[0] < H - 3:
                rows[x] = nz[0]
    # a column whose sky reaches deep while neighbours stop high is usually a gap to the street: keep it,
    # but drop columns with sky over 85% of the height (probably a mis-detected wall)
    rows[rows > 0.85 * H] = np.nan
    return rows, sky, H


def load_model(path):
    rec = pycolmap.Reconstruction(path)
    return rec, sorted(rec.images.values(), key=lambda i: i.name)


def cmd_masks(model, images, out):
    out.mkdir(parents=True, exist_ok=True)
    rec, imgs = load_model(model)
    sheet, cache = [], {}
    for im in imgs:
        photo = Image.open(Path(images) / im.name)
        rows, sky, H = sky_profile(photo)
        cache[im.name] = {"rows": [None if np.isnan(r) else float(r) for r in rows], "H": H,
                          "scale": W / photo.width}
        small = photo.convert("RGB").resize((W, H))
        ov = np.asarray(small).copy()
        ov[sky] = (ov[sky] * 0.4 + np.array([0, 80, 160]) * 0.6).astype(np.uint8)
        t = Image.fromarray(ov)
        d = ImageDraw.Draw(t)
        d.line([(x, r) for x, r in enumerate(rows) if not np.isnan(r)], fill=(255, 255, 0), width=1)
        d.text((3, 3), f"{im.name.split('__')[-1][:3]} {np.mean(~np.isnan(rows)):.0%}", fill=(255, 255, 255))
        sheet.append(t)
    json.dump(cache, open(out / "skylines.json", "w"))
    cols = 8
    Hm = max(t.height for t in sheet)
    S = Image.new("RGB", (cols * (W + 4), ((len(sheet) + cols - 1) // cols) * (Hm + 4)))
    for i, t in enumerate(sheet):
        S.paste(t, ((i % cols) * (W + 4), (i // cols) * (Hm + 4)))
    S.save(out / "sky_sheet.jpg", quality=80)
    print("cameras with sky:", sum(np.mean([r is not None for r in v["rows"]]) > 0.2 for v in cache.values()),
          "of", len(cache))


def plateau_points(tris, ground, radius=600.0, step=0.7):
    """Points on raised triangle edges (both ends above ground + 2 m) and on roof-like triangles."""
    c = tris.mean(1)
    tris = tris[np.linalg.norm(c[:, :2], axis=1) < radius]
    pts = []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        A, B = tris[:, a], tris[:, b]
        keep = (A[:, 2] > ground + 2) & (B[:, 2] > ground + 2)
        A, B = A[keep], B[keep]
        L = np.linalg.norm(B - A, axis=1)
        n = np.maximum(1, np.ceil(L / step)).astype(int)
        rep = np.repeat(np.arange(len(A)), n)
        f = (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)) / np.repeat(n, n)
        pts.append(A[rep] + f[:, None] * (B - A)[rep])
    P = np.unique(np.round(np.concatenate(pts), 1), axis=0)
    return P


class Problem:
    def __init__(self, model, tris_path, align, cache):
        self.rec, self.imgs = load_model(model)
        al = json.load(open(align))
        self.al = al
        self.R0, self.A = np.array(al["R_level"]), np.array(al["model_anchor"])
        tris = np.load(tris_path)["tris"].astype(np.float64)
        self.ground = al["ground_z"]
        self.P = plateau_points(tris, self.ground)
        sk = json.load(open(cache))
        self.cams = []
        for im in self.imgs:
            e = sk[im.name]
            rows = np.array([np.nan if r is None else r for r in e["rows"]])
            if np.mean(~np.isnan(rows)) < 0.2:
                continue
            cfw = im.cam_from_world()
            self.cams.append(dict(name=im.name, rows=rows, H=e["H"], k=e["scale"],
                                  Rc=cfw.rotation.matrix(), tc=np.array(cfw.translation),
                                  cam=self.rec.cameras[im.camera_id], C=np.array(im.projection_center())))
        print("PLATEAU skyline points", len(self.P), "cameras used", len(self.cams))

    def render(self, c, s, Rm, t):
        X = self.A + ((self.P - t) @ Rm / s) @ self.R0       # PLATEAU -> model
        Xc = X @ c["Rc"].T + c["tc"]
        ok = Xc[:, 2] > 1e-6
        Xc = Xc[ok]
        uv = np.asarray(c["cam"].img_from_cam(Xc)) * c["k"]
        u = np.floor(uv[:, 0]).astype(int)
        v = uv[:, 1]
        inb = (u >= 0) & (u < W) & (v > -c["H"]) & (v < 2 * c["H"])
        top = np.full(W, np.inf)
        np.minimum.at(top, u[inb], v[inb])
        return top

    def cost(self, s, Rm, t, per_camera=False):
        out = []
        for c in self.cams:
            top = self.render(c, s, Rm, t)
            r = c["rows"]
            m = ~np.isnan(r)
            # no building in a column that shows a skyline: count as the full distance to the image top
            rt = np.where(np.isfinite(top), np.clip(top, -0.2 * c["H"], c["H"]), 0.0)
            e = np.abs(rt[m] - r[m]) / c["H"]
            out.append(np.mean(np.minimum(e, 0.15)))
        out = np.array(out)
        return out if per_camera else float(np.mean(np.sort(out)[: max(1, int(0.8 * len(out)))]))


def rotvec(w):
    th = np.linalg.norm(w)
    if th < 1e-12:
        return np.eye(3)
    k = w / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K


def cmd_score(model, tris, align, out):
    pr = Problem(model, tris, align, out / "skylines.json")
    for i, sol in enumerate(pr.al["solutions"]):
        print(i, f"scale {sol['scale']:.2f}", f"cost {pr.cost(sol['scale'], np.array(sol['R']), np.array(sol['t'])):.4f}")


def cmd_fit(model, tris, align, out, idx):
    from scipy.optimize import minimize
    pr = Problem(model, tris, align, out / "skylines.json")
    sol = pr.al["solutions"][idx]
    s0, R0m, t0 = sol["scale"], np.array(sol["R"]), np.array(sol["t"])
    # rotate/scale about the cameras' centroid in PLATEAU space so the parameters are less coupled
    cc = np.mean([s0 * (pr.R0 @ (c["C"] - pr.A)) @ R0m.T + t0 for c in pr.cams], 0)

    def unpack(x):
        s = s0 * np.exp(x[0])
        Rd = rotvec(np.radians(x[1:4]))
        Rm = Rd @ R0m
        t = Rd @ (t0 - cc) * np.exp(x[0]) + cc + x[4:7]
        return s, Rm, t

    f = lambda x: pr.cost(*unpack(x))
    print("start cost", f(np.zeros(7)))
    best = (f(np.zeros(7)), np.zeros(7))
    # coarse: scale and yaw grid
    full = pr.P
    pr.P = full[::3]
    for ls in np.log(np.geomspace(0.6, 1.4, 9)):
        for yaw in np.arange(-12, 13, 4):
            for dz in np.arange(-20, 21, 5):
                x = np.zeros(7)
                x[0], x[3], x[6] = ls, yaw, dz
                v = f(x)
                if v < best[0]:
                    best = (v, x)
                    print("  grid", round(v, 4), x.round(2), flush=True)
    print("grid best", best[0], best[1].round(3), flush=True)
    res = minimize(f, best[1], method="Powell",
                   options=dict(xtol=1e-3, ftol=1e-5, maxfev=500, direc=np.diag([0.02, 0.5, 0.5, 1, 2, 2, 2])))
    pr.P = full
    s, Rm, t = unpack(res.x)
    print("fit cost", res.fun, "x", res.x.round(3), "scale", round(s, 2), flush=True)
    per = pr.cost(s, Rm, t, per_camera=True)
    al = pr.al
    al["solutions"].append({"scale": s, "R": Rm.tolist(), "t": t.tolist(), "median": -1.0, "skyline_cost": res.fun})
    json.dump(al, open(out / "align_skyline.json", "w"), indent=1)
    worst = np.argsort(-per)[:8]
    print("worst cameras:", [(pr.cams[i]["name"].split("__")[-1][:3], round(per[i], 3)) for i in worst])


if __name__ == "__main__":
    cmd, a = sys.argv[1], sys.argv[2:]
    if cmd == "masks":
        cmd_masks(a[0], a[1], Path(a[2]))
    elif cmd == "score":
        cmd_score(a[0], a[1], a[2], Path(a[3]))
    elif cmd == "fit":
        cmd_fit(a[0], a[1], a[2], Path(a[3]), int(a[4]))
