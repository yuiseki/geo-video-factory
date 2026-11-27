"""python -m world_model.silhouette_pose prompt <camera_truth.json>
   python -m world_model.sam_mask <camera_truth.json>          (with torch and transformers)
   python -m world_model.silhouette_pose keep <camera_truth.json>
   python -m world_model.silhouette_pose <camera_truth.json> [<ref>]
A camera pulled onto a building's outline as SAM cut it out of the photo (world_model/sam_mask.py), deterministically.

The target's PLATEAU model is drawn through the camera (hidden where nearer buildings stand in front); every pixel
of its outline in the upper half of the building carries the 3D point behind it, and is matched to the nearest point
of SAM's outline. The camera moves to put each 3D point on the line SAM's outline runs along there (point to line),
a few degrees and metres per step at most, with a search radius that shrinks. The foot is left out: people, cars and
trees hide it and dent SAM's outline there. The focal length is the photo's and stays fixed: one building's outline
cannot tell a long lens far away from a short one close by.

solve() runs it from the same five starts around a given camera and keeps the one whose outline misses least; a
start that went astray misses by tens of pixels, so a failure looks like one. Run as a module, it solves every kept
photo of a camera_truth file that has SAM masks (photo["silhouette"]["masks"]) from its hand-placed camera; `prompt`
writes SAM's prompt (the target's middle and box as the hand camera draws it) and `keep` writes the camera found.
The kept camera must stay what the masks give (tests/test_silhouette_pose.py)."""
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation as Rot

from world_model import surface_atlas as sa

UPPER = 0.5                                        # outline above this share of the building's height is used
STEP = np.array([3, 3, 3, 5, 5, 5], float)         # degrees (camera x, y, z) and metres per step at most
RADII = (80, 60, 50, 40, 30, 25, 20, 15, 12, 10, 8, 8, 8, 8)     # search radius per step, full-resolution pixels
STARTS = ([0, 0, 0, 0, 0, 0], [0, 2, 0, 3, 0, 0], [1.5, -1, 0.5, 0, 3, 1], [-1, 1.5, 0, -3, -2, 0], [0, -2, 0, 0, 0, -3])
EYE_Z_WEIGHT = 10.0                                # pixels per metre the eye strays from a given height


def moved(cam, x):
    """The camera turned by x[:3] degrees about its own axes (x right, y down, z forward) and moved by x[3:6] m."""
    R = Rot.from_rotvec(np.radians(np.asarray(x[:3], float))).as_matrix() @ np.asarray(cam["Rw"], float)
    return dict(cam, Rw=R.tolist(), eye=(np.asarray(cam["eye"], float) + np.asarray(x[3:6], float)).tolist())


def _project(cam, P):
    pc = (P - np.asarray(cam["eye"], float)) @ np.asarray(cam["Rw"], float).T
    fx, fy, cx, cy = cam["params"]
    return np.c_[pc[:, 0] / pc[:, 2] * fx + cx, pc[:, 1] / pc[:, 2] * fy + cy]


def _scaled(cam, scale):
    return dict(cam, width=round(cam["width"] * scale), height=round(cam["height"] * scale),
                params=[v * scale for v in cam["params"]])


def visible(cam, scene, target, scale=1.0):
    """(mask of the target where nothing nearer hides it, its depth) at `scale` of the photo."""
    c = _scaled(cam, scale)
    d = sa.depth_buffer(scene, c, scale=1.0); t = sa.depth_buffer(target, c, scale=1.0)
    return np.isfinite(t) & (t <= d + 0.5), t


def outline_points(cam, scene, target, scale=0.5, upper=UPPER):
    """3D points on the target's visible outline, in the upper part of the building, frame edges left out."""
    vis, t = visible(cam, scene, target, scale)
    v = vis.astype(np.uint8)
    edge = v & (1 - cv2.erode(v, np.ones((3, 3), np.uint8)))
    edge[:3, :] = edge[-3:, :] = edge[:, :3] = edge[:, -3:] = 0
    ys, xs = np.nonzero(edge)
    c = _scaled(cam, scale); fx, fy, cx, cy = c["params"]; z = t[ys, xs]
    P = np.c_[(xs + 0.5 - cx) / fx * z, (ys + 0.5 - cy) / fy * z, z] @ np.asarray(c["Rw"]) + np.asarray(c["eye"])
    lo, hi = target[..., 2].min(), target[..., 2].max()
    return P[P[:, 2] > lo + upper * (hi - lo)]


def mask_outline(mask):
    """Points of the mask's outer outline and the unit normal there (frame edges left out)."""
    cs, _ = cv2.findContours(np.asarray(mask, np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea)[:, 0, :].astype(float)
    tang = np.roll(c, -7, 0) - np.roll(c, 7, 0)
    n = np.c_[-tang[:, 1], tang[:, 0]]
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    h, w = np.asarray(mask).shape
    keep = (c[:, 0] > 3) & (c[:, 0] < w - 4) & (c[:, 1] > 3) & (c[:, 1] < h - 4)
    return c[keep], n[keep]


def choose_mask(masks, cam, scene, target, scale=0.25):
    """Index of the mask that overlaps the target drawn through `cam` the most."""
    vis, _ = visible(cam, scene, target, scale)
    best = []
    for m in masks:
        s = cv2.resize(np.asarray(m, np.uint8), (vis.shape[1], vis.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
        best.append((vis & s).sum() / max((vis | s).sum(), 1))
    return int(np.argmax(best))


def refine(cam, scene, target, mask, eye_z=None, radii=RADII):
    """(camera, median miss in pixels of the target's upper outline from SAM's) after the steps of `radii`."""
    q, nq = mask_outline(mask)
    tree = cKDTree(q)
    for r in radii:
        P = outline_points(cam, scene, target)
        if len(P) < 20:
            return cam, float("inf")
        dist, j = tree.query(_project(cam, P), distance_upper_bound=r)
        ok = np.isfinite(dist)
        if ok.sum() < 20:
            return cam, float("inf")
        P, qq, nn = P[ok], q[j[ok]], nq[j[ok]]

        def res(x, cam=cam):
            c = moved(cam, x)
            out = ((_project(c, P) - qq) * nn).sum(1)
            return np.r_[out, EYE_Z_WEIGHT * (c["eye"][2] - eye_z)] if eye_z is not None else out
        fit = least_squares(res, np.zeros(6), loss="soft_l1", f_scale=3.0, bounds=(-STEP, STEP))
        cam = moved(cam, fit.x)
    P = outline_points(cam, scene, target)
    if len(P) < 20:
        return cam, float("inf")
    dist, _ = tree.query(_project(cam, P))
    return cam, float(np.median(dist))


def solve(cam, scene, target, masks, eye_z=None):
    """(best run, all runs): refine from each of STARTS around `cam`; a run is {start, camera, miss_px}."""
    mask = masks[choose_mask(masks, cam, scene, target)]
    runs = []
    for start in STARTS:
        c, miss = refine(moved(cam, start), scene, target, mask, eye_z)
        runs.append({"start": list(start), "camera": {k: c[k] for k in ("eye", "Rw", "params")}, "miss_px": miss})
    best = min(runs, key=lambda r: r["miss_px"])
    return best, runs


def store_ready():
    try:
        from buildings.pp_tiles import store
        return any(store().glob("plateau/*/*.json"))
    except Exception:
        return False


def solve_kept(doc, photo, base, radius=400):
    """The silhouette camera of a kept photo, from its hand-placed camera and its kept SAM mask."""
    from PIL import Image
    from buildings.plateau_building import area_triangles, building_triangles
    cam = dict(photo["camera"], width=photo["width"], height=photo["height"])
    target = np.concatenate(list(building_triangles(list(photo["buildings"].values()), doc["origin"]).values()))
    scene = area_triangles(doc["origin"], cam["eye"][:2], radius)
    masks = [np.asarray(Image.open(Path(base) / m).convert("L")) > 127 for m in photo["silhouette"]["masks"]]
    best, runs = solve(cam, scene, target, masks, photo.get("eye_z"))
    best["runs"] = [{"start": r["start"], "miss_px": round(r["miss_px"], 2)} for r in runs]
    return best


def prompt(doc, photo, radius=400):
    """SAM's prompt for a kept photo: the middle of the target as drawn through the hand-placed camera, and its box."""
    from buildings.plateau_building import area_triangles, building_triangles
    cam = dict(photo["camera"], width=photo["width"], height=photo["height"])
    target = np.concatenate(list(building_triangles(list(photo["buildings"].values()), doc["origin"]).values()))
    vis, _ = visible(cam, area_triangles(doc["origin"], cam["eye"][:2], radius), target, 0.5)
    ys, xs = np.nonzero(vis)
    return {"point": [round(float(xs.mean()) * 2, 1), round(float(ys.mean()) * 2, 1)],
            "box": [int(xs.min()) * 2, int(ys.min()) * 2, int(xs.max()) * 2 + 1, int(ys.max()) * 2 + 1]}


def _write(path, doc):
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    if argv[0] == "prompt":                    # prompt <camera_truth.json>: SAM's prompt from the hand camera
        path = Path(argv[1]); doc = json.loads(path.read_text())
        for photo in doc["photos"]:
            photo.setdefault("silhouette", {})["prompt"] = prompt(doc, photo)
            print(photo["ref"], photo["silhouette"]["prompt"])
        return _write(path, doc)
    keep = argv[0] == "keep"                   # keep <camera_truth.json>: solve and write the silhouette camera
    path = Path(argv[1] if keep else argv[0]); doc = json.loads(path.read_text())
    for photo in doc["photos"]:
        if "masks" not in photo.get("silhouette", {}) or (not keep and len(argv) > 1 and photo["ref"] != argv[1]):
            continue
        best = solve_kept(doc, photo, path.parent)
        if keep:
            c = best["camera"]
            photo["silhouette"].update(camera={"eye": [round(v, 3) for v in c["eye"]],
                                               "Rw": [[round(v, 6) for v in r] for r in c["Rw"]],
                                               "params": [round(v, 2) for v in c["params"]]},
                                       miss_px=round(best["miss_px"], 2), runs=best["runs"])
        hand = photo["camera"]
        turn = math.degrees(np.linalg.norm(Rot.from_matrix(np.array(best["camera"]["Rw"]) @ np.array(hand["Rw"]).T).as_rotvec()))
        print(photo["ref"], "eye", np.round(best["camera"]["eye"], 2).tolist(), "miss px", round(best["miss_px"], 2),
              "from the hand camera", round(float(np.linalg.norm(np.array(best["camera"]["eye"]) - hand["eye"])), 2), "m",
              round(turn, 2), "deg", "runs", [r["miss_px"] for r in best["runs"]])
    if keep:
        _write(path, doc)


if __name__ == "__main__":
    main(sys.argv[1:])
