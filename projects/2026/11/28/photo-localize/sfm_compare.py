"""Two SfM tools' cameras on the same photos, against cameras geo.photo_solve placed (OpenSfM, visloc-rs).

    python sfm_compare.py <names.tsv> <truth dir> <tool>=<model dir> [<tool>=<model dir> ...] > report.json

<names.tsv> maps each SfM image name to the key photo_solve's run used for the same photo (one "NNN.jpg<TAB>key"
per line). <truth dir> holds photo_solve work directories named by key; only those whose solve.json says "solved"
count as truth. A model dir is either a COLMAP text model with enu_origin.txt beside it (visloc-rs writes both:
tool name "visloc") or an OpenSfM dataset with reconstruction.json and reference_lla.json (any other tool name is
read as OpenSfM). Each tool is scored as it georeferenced itself from the photos' GPS: for every truth photo, how
far its camera is from photo_solve's and by how many degrees it is turned. All positions go through longitude and
latitude and then one local frame, so the tools' own metre conventions do not matter. Every camera is OpenCV's:
x_cam = R @ (x - C), x right, y down, z forward, world east, north, up.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

KY = 110950.0          # metres per degree of latitude, as seed_place.py and photo_solve's tools use
R_EARTH = 6378137.0    # the sphere visloc-rs's enu_origin conversion and OpenSfM's topocentric frame are near


def kx(lat):
    return 111320.0 * math.cos(math.radians(lat))


def to_enu(lon, lat, origin):
    return (lon - origin[0]) * kx(origin[1]), (lat - origin[1]) * KY


def from_enu(e, n, origin):
    return origin[0] + e / kx(origin[1]), origin[1] + n / KY


def heading(r):
    f = np.asarray(r, float)[2]
    return math.degrees(math.atan2(f[0], f[1])) % 360


def angle_deg(a, b):
    c = (np.trace(np.asarray(a, float) @ np.asarray(b, float).T) - 1) / 2
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def quat_to_r(qw, qx, qy, qz):
    return np.array([
        [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
        [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
        [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)]])


def r_to_quat(r):
    r = np.asarray(r, float)
    w = math.sqrt(max(0.0, 1 + r[0, 0] + r[1, 1] + r[2, 2])) / 2
    if w > 1e-6:
        return np.array([w, (r[2, 1] - r[1, 2]) / (4 * w), (r[0, 2] - r[2, 0]) / (4 * w), (r[1, 0] - r[0, 1]) / (4 * w)])
    i = int(np.argmax(np.diag(r)))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = math.sqrt(max(0.0, 1 + r[i, i] - r[j, j] - r[k, k])) * 2
    q = np.zeros(4)
    q[0] = (r[k, j] - r[j, k]) / s
    q[1 + i], q[1 + j], q[1 + k] = s / 4, (r[j, i] + r[i, j]) / s, (r[k, i] + r[i, k]) / s
    return q


def axis_angle_to_r(v):
    v = np.asarray(v, float)
    th = np.linalg.norm(v)
    if th < 1e-12:
        return np.eye(3)
    k = v / th
    kk = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(th) * kk + (1 - math.cos(th)) * kk @ kk


def r_to_axis_angle(r):
    th = math.radians(angle_deg(r, np.eye(3)))
    if th < 1e-12:
        return np.zeros(3)
    r = np.asarray(r, float)
    if math.pi - th < 1e-6:               # half a turn: the axis is the column of (R + I) / 2 that is not zero
        m = (r + np.eye(3)) / 2
        k = m[:, int(np.argmax(np.diag(m)))]
        return k / np.linalg.norm(k) * th
    v = np.array([r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1]]) / (2 * math.sin(th))
    return v * th


def _sphere_lonlat(e, n, lon0, lat0):
    return (lon0 + math.degrees(e / (R_EARTH * math.cos(math.radians(lat0)))), lat0 + math.degrees(n / R_EARTH))


def colmap_cams(model):
    """{image name: {lonlat, up, R}} from a georeferenced COLMAP text model (visloc-rs: enu_origin.txt = lat lon alt)."""
    model = Path(model)
    lat0, lon0, _ = map(float, [ln for ln in (model / "enu_origin.txt").read_text().splitlines()
                                if ln.strip() and not ln.startswith("#")][0].split())
    lines = [ln for ln in (model / "images.txt").read_text().splitlines() if not ln.startswith("#")]
    out = {}
    for ln in lines[0::2]:
        f = ln.split()
        if len(f) < 10:
            continue
        r, t = quat_to_r(*map(float, f[1:5])), np.array(list(map(float, f[5:8])))
        c = -r.T @ t
        out[f[9]] = {"lonlat": _sphere_lonlat(c[0], c[1], lon0, lat0), "up": float(c[2]), "R": r}
    return out


def opensfm_cams(dataset):
    """One {image name: {lonlat, up, R}} per reconstruction (OpenSfM splits what does not connect)."""
    dataset = Path(dataset)
    ref = json.loads((dataset / "reference_lla.json").read_text())
    comps = []
    for rec in json.loads((dataset / "reconstruction.json").read_text()):
        cams = {}
        for name, shot in rec["shots"].items():
            r = axis_angle_to_r(shot["rotation"])
            c = -r.T @ np.asarray(shot["translation"], float)
            cams[name] = {"lonlat": _sphere_lonlat(c[0], c[1], ref["longitude"], ref["latitude"]), "up": float(c[2]), "R": r}
        comps.append(cams)
    return comps


def similarity(src, dst):
    """Scale, rotation and shift with dst = s * R @ src + t, least squares (Umeyama)."""
    src, dst = np.asarray(src, float), np.asarray(dst, float)
    ms, md = src.mean(0), dst.mean(0)
    a, b = src - ms, dst - md
    u, d, vt = np.linalg.svd(b.T @ a / len(src))
    sign = np.diag([1, 1, np.sign(np.linalg.det(u @ vt))])
    r = u @ sign @ vt
    s = float(np.trace(np.diag(d) @ sign) / (a ** 2).sum(1).mean())
    return s, r, md - s * r @ ms


def against_truth(model, truth):
    """One row per truth photo: how far the model's camera is from the truth one, and how much it is turned."""
    rows = []
    for name in sorted(truth):
        if name not in model:
            rows.append({"name": name, "registered": False})
            continue
        o = truth[name]["lonlat"]
        e, n = to_enu(*model[name]["lonlat"], o)
        rows.append({"name": name, "registered": True, "apart_m": math.hypot(e, n), "east_m": e, "north_m": n,
                     "turn_deg": angle_deg(model[name]["R"], truth[name]["R"]),
                     "heading_off_deg": (heading(model[name]["R"]) - heading(truth[name]["R"]) + 180) % 360 - 180})
    return rows


def truth_cams(names, truth_dir):
    """photo_solve's solved cameras, by SfM image name."""
    out = {}
    for img, key in names.items():
        p = Path(truth_dir) / key / "solve.json"
        if not p.exists():
            continue
        s = json.loads(p.read_text())
        if s.get("verdict") != "solved":
            continue
        eye = s["camera"]["eye"]
        out[img] = {"lonlat": from_enu(eye[0], eye[1], s["origin"]), "R": np.asarray(s["camera"]["Rw"], float)}
    return out


def summary(rows):
    got = [r for r in rows if r["registered"]]
    med = (lambda xs: float(np.median(xs)) if xs else None)
    return {"truth": len(rows), "registered": len(got), "median_apart_m": med([r["apart_m"] for r in got]),
            "max_apart_m": max([r["apart_m"] for r in got], default=None),
            "median_turn_deg": med([r["turn_deg"] for r in got])}


def main(argv):
    names = dict(ln.split("\t") for ln in Path(argv[0]).read_text().split("\n") if ln.strip())
    truth = truth_cams(names, argv[1])
    report = {"truth_photos": len(truth), "tools": {}}
    for spec in argv[2:]:
        tool, model = spec.split("=", 1)
        comps = [colmap_cams(model)] if tool == "visloc" else opensfm_cams(model)
        best = max(comps, key=len) if comps else {}
        rows = against_truth(best, truth)
        report["tools"][tool] = {"components": [len(c) for c in comps], "registered_total": sum(len(c) for c in comps),
                                 "largest": len(best), "vs_photo_solve": summary(rows), "rows": rows}
    json.dump(report, sys.stdout, indent=1, default=float)
    print()


if __name__ == "__main__":
    main(sys.argv[1:])
