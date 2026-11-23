"""walk_shot.py rank   <survey.json | proj_dir> <crosswalks.json>            rate every photo x crosswalk x direction
   walk_shot.py plan   <proj_dir> <crosswalks.json> <work_dir> --photo=<key> --crosswalk=<name>
   walk_shot.py encode <work_dir> <out.mp4>

A straight walk along a crosswalk through one projected photo, no head turn (v0.8.0 on). The photo and the
crosswalk are chosen by measurement, not by eye: packages/pipeline/photo_walk.py rates how much of each
frame of the walk the photo saw, and says which gate a candidate misses.

rank: survey.json is a list with one row per registered photo ({"name", "x", "y", "h" (eye height above
      the ground), "bearing", "pitch", "fov_v", "w", "hgt", "n3d"}); a proj_dir (cams.json + mesh.npz of
      export_projection.py) rates only the exported photos. Prints the rows that pass and the best
      failing ones (--all prints everything).  --ground=<z> (default: the proj_dir's; 0 for a survey)
plan: writes <work_dir>/frames.json for blender_projection.py --frames, frames in <work_dir>/f/.
      --direction=ab|ba (ab = the order of the crosswalk's line; default: the better rated)
      --pitch=<deg> (default: the photo's)  --speed=1.2 (m/s)
Common: --origin=lon,lat of the model's local frame (default: the one blender_projection.py draws the
        zebra bars with)
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "packages" / "pipeline"))
import photo_walk as pw  # noqa: E402

FPS = 24
ORIGIN = (139.70055, 35.65950)


def load_photos(path: Path, ground):
    """({key: photo}, ground z). Survey rows carry heights above the ground; a proj_dir absolute z."""
    if path.is_dir():
        g = float(np.load(path / "mesh.npz")["ground"]) if ground is None else ground
        out = {}
        for key, c in json.load(open(path / "cams.json")).items():
            f = np.array(c["Rw"]).T[:, 2]
            out[key] = dict(eye=tuple(c["eye"]), bearing=float(np.degrees(np.arctan2(f[0], f[1])) % 360),
                            pitch=float(np.degrees(np.arcsin(f[2]))), fov_v=c["fov_v"], width=c["width"],
                            height=c["height"])
        return out, g
    g = 0.0 if ground is None else ground
    return {r["name"]: dict(eye=(r["x"], r["y"], g + r["h"]), bearing=r["bearing"], pitch=r["pitch"],
                            fov_v=r["fov_v"], width=r["w"], height=r["hgt"], n3d=r["n3d"])
            for r in json.load(open(path))}, g


def show(r):
    return (f"{r['photo'][:44]:44s} {r['crosswalk']:14s} {r['direction']} walk {r['walk_m']:5.1f} m "
            f"brg {r['bearing']:5.1f} turn {r['turn']:5.1f} gap {r['eye_gap']:5.1f} eye {r['eye_height']:5.1f} "
            f"cover {r['coverage_min']:.3f}/{r['coverage_mean']:.3f}  {','.join(r['fails']) or 'ok'}")


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--") and "=" in a)
    origin = tuple(float(v) for v in opts["origin"].split(",")) if "origin" in opts else ORIGIN
    ground = float(opts["ground"]) if "ground" in opts else None
    if args[0] == "encode":
        work, out = Path(args[1]), Path(args[2])
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", str(work / "f" / "%05d.png"),
                        "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(out)], check=True)
        return
    photos, ground = load_photos(Path(args[1]), ground)
    crosswalks = pw.crosswalks_local(json.load(open(args[2])), origin)
    if args[0] == "rank":
        rows = pw.rank_walks(photos, crosswalks, ground)
        ok = [r for r in rows if not r["fails"]]
        print(f"{len(photos)} photos x {len(crosswalks)} crosswalks x 2 directions = {len(rows)}; {len(ok)} pass")
        for r in rows if "--all" in argv else ok + [r for r in rows if r["fails"]][:12]:
            print(show(r))
        return
    key = [k for k in photos if opts["photo"] in k][0]
    cw = [c for c in crosswalks if c["name"] == opts["crosswalk"]]
    pitch = float(opts["pitch"]) if "pitch" in opts else None
    rows = [r for r in pw.rank_walks({key: photos[key]}, cw, ground, pitch=pitch)
            if r["direction"] == opts.get("direction", r["direction"])]
    r = rows[0]
    print(show(r))
    work = Path(args[3])
    (work / "f").mkdir(parents=True, exist_ok=True)
    frames = pw.straight_walk(r["start"], r["end"], photos[key]["eye"][2],
                              photos[key]["pitch"] if pitch is None else pitch, float(opts.get("speed", 1.2)), FPS)
    for i, fr in enumerate(frames):
        fr["out"] = str(work / "f" / f"{i:05d}.png")
    json.dump(frames, open(work / "frames.json", "w"))
    json.dump({"photo": key, **r}, open(work / "plan.json", "w"), indent=1)
    print(f"{len(frames)} frames, {len(frames) / FPS:.1f} s")


if __name__ == "__main__":
    main(sys.argv[1:])
