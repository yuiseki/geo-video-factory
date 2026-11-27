"""python -m geo.photo_solve <photo file or address> <work_dir> [--vision-python=<python with torch and transformers>]
One photo placed on PLATEAU from nothing but the photo file (its pixels and its EXIF), with no person picking or
looking, and refused rather than guessed when a gate does not pass.

1. exif.json      photos/photo_exif.py: size, focal length (35 mm equivalent), GPS position and how far to trust it.
2. tris.npz       PLATEAU around the position (buildings/plateau_building.area_triangles), after PLATEAU++ is built
                  for the whole box (OVERPASS_URL; tiles made before are not made again).
   sky.json       which sky photo_place reads: clear blue or overcast white, whichever finds more (night only when
                  neither does); refused here when none finds 2 % of the picture.
3. place/         geo/photo_place.py: the skyline searched over every heading, pitch, roll and field of view, on an
                  8 m grid and then a 2 m grid around the best eight places, within 40 m of the GPS fix first and
                  wider (100 m, then as far as the EXIF says the fix may be off) only while the best place is not
                  alone or lies on the rim. Gate: no place 10 m or more away fits within 1 % (alone).
4. target.json    the PLATEAU building the coarse camera sees most of (by its visible pixels).
5. masks/         world_model/sam_mask.py, run with --vision-python: SAM's three masks of that building, prompted by
                  its middle and box as the coarse camera draws it.
6. solve.json     world_model/silhouette_pose.py from the coarse camera. Gates: the best start's median miss of the
                  building's upper outline, three of five starts reaching the same camera, and the camera within the
                  GPS radius of the EXIF position.
   overlay.jpg    the building and its neighbours drawn through the camera found (world_model/truth_view.py).

Each step writes its files and is skipped when they are there, so a run that stopped goes on from where it stopped.
Exit status 0 with "solved", or 1 with the gate that refused."""
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

MISS_PX = 4.0              # the best start's median miss of the upper outline, full-resolution pixels
AGREE_M, AGREE_DEG = 1.0, 0.5
AGREE_RUNS = 3
TRIS_RADIUS = 700.0
SOLVE_WORKERS = 5          # the five starts of the silhouette camera run side by side


def _json(path, value=None):
    if value is None:
        return json.loads(Path(path).read_text())
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=1))
    return value


def step_exif(photo, work):
    from photos.photo_exif import camera_from_exif
    f = work / "exif.json"
    return _json(f) if f.exists() else _json(f, camera_from_exif(photo))


def photo_file(photo, work):
    """The photo's file: where it is, or fetched once into the work directory when an address was given."""
    if "://" not in str(photo):
        return Path(photo).resolve()
    import urllib.request
    f = Path(work).resolve() / "photo.jpg"
    if not f.exists():
        with urllib.request.urlopen(urllib.request.Request(str(photo), headers={"User-Agent": "geo-video-factory"}),
                                    timeout=60) as r:
            f.write_bytes(r.read())
    return f


def step_tris(ex, work):
    """PLATEAU within TRIS_RADIUS of the fix. The whole box is built first, every time (one built before costs
    nothing), so the scene does not depend on what the tile store happened to hold."""
    from buildings import plateau_building, plateau_pp
    f = work / "tris.npz"
    if not f.exists():
        origin = (ex["lon"], ex["lat"])
        kx, ky = 111320 * math.cos(math.radians(ex["lat"])), 110950
        r = TRIS_RADIUS
        plateau_pp.cached([ex["lon"] - r / kx, ex["lat"] - r / ky, ex["lon"] + r / kx, ex["lat"] + r / ky])
        t = plateau_building.area_triangles(origin, (0.0, 0.0), TRIS_RADIUS)
        np.savez_compressed(f, tris=t.astype(np.float32), origin=np.array(origin))
    return f


SKY_SHARE = 0.02           # less sky than this in the picture leaves no roofline to place it by


def step_sky(photo, work):
    """Which of photo_place's sky readings to use: the clear blue sky or the bright white of an overcast one, the one
    that finds more; the dark of a night sky only when neither finds any. Refuses before the search when none does."""
    f = work / "sky.json"
    if f.exists():
        return _json(f)
    from PIL import Image
    from geo.photo_place import WORK_W, sky_mask
    with Image.open(photo) as im:
        w, h = im.size
        rgb = np.asarray(im.convert("RGB").resize((WORK_W, round(WORK_W * h / w))))
    share = {k: round(float(sky_mask(rgb, k).mean()), 4) for k in ("blue", "bright", "dark")}
    kind = max(("blue", "bright"), key=lambda k: share[k])
    if share[kind] < SKY_SHARE:
        kind = "dark" if share["dark"] >= SKY_SHARE else None
    return _json(f, {"kind": kind, "share": share})


SEARCH_RADII = (40.0, 100.0)    # metres searched first; widened only when the answer is not decided inside
# The fine search stays photo_place's +-4 m: at +-2 m the Ueno photo's best (0.640) lay 3 m outside and a worse one
# (0.649, 1.1 m away) was taken, to save 20 s.
COARSE_GRID = 8.0


def step_place(photo, tris_path, ex, sky, work):
    """The skyline search, from a small radius outwards: it stops at the first radius whose answer is alone and does
    not lie on the radius's rim (within one coarse step), else widens, up to how far the EXIF says the fix may be off.
    A photo whose GPS is good is searched over 40 m, not the 300 m a cell-tower label asks for."""
    import shutil
    from geo.photo_place import place
    f = work / "place" / "result.json"
    if f.exists():
        return _json(f)
    limit = ex["search_radius_m"]
    tried = []
    for radius in [r for r in SEARCH_RADII if r < limit] + [limit]:
        out = work / f"place_{radius:g}m"
        res = _place_once(place, photo, tris_path, ex, sky, out, radius)
        tried.append({"radius": radius, "alone": res["alone"], "moved_m": round(res["moved_m"], 1)})
        if res["alone"] and res["moved_m"] <= radius - COARSE_GRID:
            break
    shutil.copytree(out, work / "place")
    res.update(radius=radius, tried=tried)
    return _json(f, res)


def _place_once(place, photo, tris_path, ex, sky, out, radius):
    if ex["fx"] is not None:
        hfov, fov_range = ex["hfov_deg"], "0.94:1.06:3"
    else:                                     # no 35 mm equivalent: phones' main cameras, 50 to 80 degrees across
        hfov, fov_range = 65.0, "0.77:1.23:7"
    return place(photo, tris_path, out, 0.0, 0.0, hfov, radius=radius,
                 grid=2.0, coarse_grid=COARSE_GRID, fov_range=fov_range, min_sky=40, sky=sky,
                 log=lambda s: print(s, flush=True))


def _coarse_camera(work):
    cams = _json(work / "place" / "cams.json")
    c = next(iter(cams.values()))
    return {k: c[k] for k in ("eye", "Rw", "params", "width", "height")}


def step_target(cam, ex, work, radius=250.0, scale=0.125):
    """The building the coarse camera sees most of, by its visible pixels at 1/8 resolution."""
    f = work / "target.json"
    if f.exists():
        return _json(f)
    from buildings.plateau_building import area_triangles, building_triangles, _store_entries
    from world_model.silhouette_pose import scene_depth, visible
    origin = (ex["lon"], ex["lat"])
    kx, ky = 111320 * math.cos(math.radians(ex["lat"])), 110950
    R = np.asarray(cam["Rw"]); eye = np.asarray(cam["eye"])
    ids = []
    for entry in _store_entries():
        for gid, (lon, lat) in (entry.get("feature_centroids") or {}).items():
            p = np.array([(lon - origin[0]) * kx, (lat - origin[1]) * ky, eye[2]])
            pc = R @ (p - eye)
            if pc[2] > 5 and np.hypot(*(p[:2] - eye[:2])) < radius and abs(pc[0] / pc[2]) < 1.5:
                ids.append(gid)
    tris = building_triangles(sorted(set(ids)), origin)
    scene = area_triangles(origin, eye[:2], 400.0)
    behind = scene_depth(cam, scene, scale)      # drawn once for every building asked
    seen = {gid: int(visible(cam, scene, t, scale, behind)[0].sum()) for gid, t in tris.items()}
    best = max(seen, key=seen.get)
    vis, _ = visible(cam, scene, tris[best], 0.5)
    ys, xs = np.nonzero(vis)
    order = sorted(seen, key=seen.get, reverse=True)
    return _json(f, {"gml_id": best, "pixels_at_1_8": seen[best], "next": [[g, seen[g]] for g in order[1:6]],
                     "prompt": {"point": [round(float(xs.mean()) * 2, 1), round(float(ys.mean()) * 2, 1)],
                                "box": [int(xs.min()) * 2, int(ys.min()) * 2, int(xs.max()) * 2 + 1, int(ys.max()) * 2 + 1]}})


def step_masks(photo, target, work, vision_python):
    out = work / "masks"
    if not (out / "scores.json").exists():
        if not vision_python:
            raise SystemExit("SAM needs --vision-python=<a python with torch and transformers>")
        p, b = target["prompt"]["point"], target["prompt"]["box"]
        subprocess.run([vision_python, "-m", "world_model.sam_mask", f"--photo={photo}", f"--point={p[0]},{p[1]}",
                        f"--box={','.join(str(v) for v in b)}", f"--out={out}"], check=True,
                       cwd=Path(__file__).resolve().parents[1])
    return sorted(out.glob("mask_*.png"))


def _apart(a, b):
    from scipy.spatial.transform import Rotation as Rot
    turn = math.degrees(np.linalg.norm(Rot.from_matrix(np.array(a["Rw"]) @ np.array(b["Rw"]).T).as_rotvec()))
    return float(np.linalg.norm(np.array(a["eye"]) - b["eye"])), turn


def judge(alone, best, runs, radius):
    """(verdict, gates): every gate a camera must pass before it is given as the answer. The camera is in the frame
    whose origin is the EXIF position, so its distance from the origin is its distance from the GPS fix."""
    agree = sum(1 for r in runs if np.isfinite(r["miss_px"]) and
                all(v <= lim for v, lim in zip(_apart(r["camera"], best["camera"]), (AGREE_M, AGREE_DEG))))
    from_gps = float(np.hypot(*best["camera"]["eye"][:2]))
    gates = {"alone": bool(alone),
             "miss_px": [round(best["miss_px"], 2), best["miss_px"] <= MISS_PX],
             "starts_agreeing": [agree, agree >= AGREE_RUNS],
             "from_gps_m": [round(from_gps, 1), from_gps <= radius]}
    refused = [k for k, v in gates.items() if not (v if isinstance(v, bool) else v[1])]
    return ("solved" if not refused else "refused: " + ", ".join(refused)), gates


def step_solve(cam, ex, target, mask_paths, place, work):
    from PIL import Image
    from buildings.plateau_building import area_triangles, building_triangles
    from world_model.silhouette_pose import solve
    origin = (ex["lon"], ex["lat"])
    tgt = building_triangles([target["gml_id"]], origin)[target["gml_id"]]
    scene = area_triangles(origin, cam["eye"][:2], 400.0)
    masks = [np.asarray(Image.open(m).convert("L")) > 127 for m in mask_paths]
    best, runs = solve(cam, scene, tgt, masks, eye_z=place["ground"] + place["eye_height"], workers=SOLVE_WORKERS)
    verdict, gates = judge(place["alone"], best, runs, ex["search_radius_m"])
    out = {"verdict": verdict, "origin": list(origin),
           "camera": best["camera"], "gates": gates, "target": target["gml_id"],
           "runs": [{"start": r["start"], "miss_px": round(r["miss_px"], 2)} for r in runs]}
    return _json(work / "solve.json", out), tgt


def main(argv):
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in argv if a.startswith("--"))
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 2:
        raise SystemExit(__doc__)
    work = Path(args[1]); work.mkdir(parents=True, exist_ok=True)
    photo = photo_file(args[0], work)
    clock = [time.time()]

    def took(step):                       # how long each step took, to the log
        clock.append(time.time()); print(f"[{step} {clock[-1] - clock[-2]:.1f} s]", flush=True)
    ex = step_exif(photo, work)
    sky = step_sky(photo, work)
    if sky["kind"] is None:
        _json(work / "solve.json", {"verdict": "refused: no sky", "sky": sky})
        print("refused: no sky to read a roofline from", sky["share"]); raise SystemExit(1)
    took("exif and sky")
    tris = step_tris(ex, work); took("tris")
    place = step_place(photo, tris, ex, sky["kind"], work); took("place")
    if not place["alone"]:
        _json(work / "solve.json", {"verdict": "refused: alone", "place": place["best"]})
        print("refused: the skyline does not decide the place"); raise SystemExit(1)
    cam = _coarse_camera(work)
    target = step_target(cam, ex, work); took("target")
    masks = step_masks(photo, target, work, opts.get("vision-python")); took("masks")
    out, tgt = step_solve(cam, ex, target, masks, place, work); took("solve")
    from world_model.truth_view import draw
    photo_entry = {"file": photo.name, "camera": out["camera"], "width": ex["width"], "height": ex["height"]}
    draw(photo_entry, {"target": tgt}, photo.parent, work / "overlay.jpg")
    print(out["verdict"], json.dumps(out["gates"]))
    raise SystemExit(0 if out["verdict"] == "solved" else 1)


if __name__ == "__main__":
    main(sys.argv[1:])
