"""python -m world_model.corner_pose <camera_truth.json> [<ref>]
   python -m world_model.corner_pose keep <camera_truth.json> <photo.json>
A camera from building corners and edges picked in one photo: the place and turn (and, when the photo does not say
it, the focal length) that put each picked roof corner on its pixel and each picked edge through its pixel.

A pick is a point ([x, y, z] in the truth's local frame -> [u, v] in full-resolution photo pixels) or a line (two
3D points of an edge -> one pixel anywhere on that edge in the photo). A vertical edge whose top and foot are hidden
still says where the building stands. With the focal length free, few corners cannot tell a long lens far away
from a short one close by; `eye_z` (the photographer stood on the street) settles it.

The kept truths are packages/pipeline/camera_truth/*.json: the picks, the PLATEAU buildings they came from and the
camera they give, so a photo is placed once by hand and never again (tests/test_corner_pose.py checks that every
kept camera is still what its picks give). Run as a module, it prints each kept camera and its residuals; `keep` solves one photo's picks (a photo
entry without its camera, plus guess_eye) and writes it into the file."""
import json
import math
import sys

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation as Rot

EYE_Z_WEIGHT = 20.0          # pixels per metre the eye strays from the given height


def project(cam, points):
    """Pixels (n, 2) of world points through a camera {eye, Rw (world -> camera, x right, y down), params}."""
    fx, fy, cx, cy = cam["params"]
    pc = (np.atleast_2d(np.asarray(points, float)) - np.asarray(cam["eye"], float)) @ np.asarray(cam["Rw"], float).T
    return np.c_[pc[:, 0] / pc[:, 2] * fx + cx, pc[:, 1] / pc[:, 2] * fy + cy]


def _camera(x, spec, fx0, free):
    fx = fx0 * math.exp(x[6]) if free else fx0
    return {"eye": x[3:6].tolist(), "Rw": Rot.from_rotvec(x[:3]).as_matrix().tolist(),
            "params": [fx, fx, spec["width"] / 2, spec["height"] / 2], "width": spec["width"], "height": spec["height"]}


def residuals(cam, spec):
    """Pixel misses of every pick, then the eye height's (scaled), as one vector."""
    r = []
    for P, uv in spec.get("points", []):
        r += list(project(cam, [P])[0] - np.asarray(uv, float))
    for (a, b), uv in spec.get("lines", []):
        p = project(cam, [a, b]); d = p[1] - p[0]
        n = np.array([-d[1], d[0]]) / max(np.linalg.norm(d), 1e-9)
        r.append(float((np.asarray(uv, float) - p[0]) @ n))
    if spec.get("eye_z") is not None:
        r.append(EYE_Z_WEIGHT * (cam["eye"][2] - spec["eye_z"]))
    return np.array(r)


def _look(eye, target):
    f = (target - eye) / np.linalg.norm(target - eye)
    r = np.cross(f, [0, 0, 1.0]); r /= np.linalg.norm(r)
    return Rot.from_matrix(np.array([r, np.cross(f, r), f])).as_rotvec()


def solve(spec, spread=60, step=20):
    """(camera, residuals) of the best start on a grid of eyes around spec['guess_eye'] (all picks in front)."""
    free = spec.get("fx") is None
    fx0 = spec.get("fx") or 0.9 * max(spec["width"], spec["height"])
    corners = [np.asarray(P, float) for P, _ in spec.get("points", [])]
    corners += [np.asarray(a, float) for (a, _b), _uv in spec.get("lines", [])]
    target = np.mean(corners, axis=0)
    gx, gy, gz = spec["guess_eye"]
    best = None
    for dx in range(-spread, spread + 1, step):
        for dy in range(-spread, spread + 1, step):
            eye = np.array([gx + dx, gy + dy, gz], float)
            x0 = np.r_[_look(eye, target), eye, [0.0] if free else []]
            fit = least_squares(lambda x: residuals(_camera(x, spec, fx0, free), spec), x0,
                                loss="soft_l1", f_scale=10)
            cam = _camera(fit.x, spec, fx0, free)
            pc = (np.array(corners) - cam["eye"]) @ np.array(cam["Rw"]).T
            if (pc[:, 2] > 0).all() and (best is None or fit.cost < best[0]):
                best = (fit.cost, cam)
    cam = best[1]
    return cam, residuals(cam, spec)


def keep(truth_path, photo):
    """Solve a photo's picks (photo['guess_eye'] near where it was taken) and write it, with its camera and largest
    miss, into the camera_truth file; a photo already kept under the same ref is replaced."""
    cam, res = solve(photo)
    entry = {k: v for k, v in photo.items() if k != "guess_eye"}
    entry["camera"] = {"eye": [round(v, 3) for v in cam["eye"]], "Rw": [[round(v, 6) for v in r] for r in cam["Rw"]],
                       "params": [round(v, 2) for v in cam["params"]]}
    entry["residual_px_max"] = round(float(np.abs(res).max()), 1)
    doc = json.loads(open(truth_path).read())
    doc["photos"] = [p for p in doc["photos"] if p["ref"] != photo["ref"]] + [entry]
    with open(truth_path, "w") as f:
        f.write(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    return entry


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    if argv[0] == "keep":                      # keep <camera_truth.json> <photo.json>
        e = keep(argv[1], json.load(open(argv[2])))
        print(e["ref"], "eye", e["camera"]["eye"], "max miss px", e["residual_px_max"])
        return
    doc = json.load(open(argv[0]))
    for photo in doc["photos"]:
        if len(argv) > 1 and photo["ref"] != argv[1]:
            continue
        cam, res = solve(dict(photo, guess_eye=photo["camera"]["eye"]))
        f = np.array(cam["Rw"])[2]
        print(photo["ref"], "eye", np.round(cam["eye"], 2).tolist(), "fx", round(cam["params"][0], 1),
              "heading", round(math.degrees(math.atan2(f[0], f[1])) % 360, 1), "pitch",
              round(math.degrees(math.asin(f[2])), 1), "max miss px", round(float(np.abs(res).max()), 1))


if __name__ == "__main__":
    main(sys.argv[1:])
