"""How far geo/photo_place.py puts a street photo from where it was taken, on Shibuya's SfM-aligned photos.

    python projects/2026/11/26/plateau-pp-ultra-after/placement_eval.py <label> [--only=<n>] [--offset=20] [photo_place options]

The truth is the liminal project's CC0 world model (work/shibuya_world_v1/sfm_world_cc0_v1/cams.json: SfM placed on
PLATEAU, median 0.53 m from the faces). Every camera of it within 4 m of the crossing's ground (52.8 m), the street
photos the skyline search is for, is placed again by photo_place from a point --offset metres away from the truth in
a seeded random direction (the error of a geotag), and the found pose is compared with the truth:
work/placement_eval/<label>/<key>/ (photo_place's files) and work/placement_eval/<label>.json (one row per photo:
position error, heading error, the sky fraction of the picture, the cost). Options other than --only and --offset go
to photo_place (e.g. --min-sky=10). Run from the repository root with packages/pipeline's Python, under the host's
resource limits.
"""
import json
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO / "packages" / "pipeline"))
WORLD = REPO / "projects/2026/11/20/liminal-space-city-walk-with-bgm/work/shibuya_world_v1"
TRUTH = WORLD / "sfm_world_cc0_v1" / "cams.json"
TRIS = WORLD.parent / "shibuya_crossing" / "plateau" / "tris.npz"
GROUND = 52.8


def heading_of(cam: dict) -> float:
    fx, fy, _ = cam["Rw"][2]                     # world -> camera: its third row is the viewing direction
    return math.degrees(math.atan2(fx, fy)) % 360


def street_cams() -> list[tuple[str, dict]]:
    cams = json.loads(TRUTH.read_text())
    return sorted((k, c) for k, c in cams.items() if c["eye"][2] < GROUND + 4)


def main() -> None:
    from geo import photo_place as pp
    from photos import photo_store
    label = sys.argv[1]
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in sys.argv[2:] if a.startswith("--"))
    offset = float(opts.pop("offset", 20))
    only = opts.pop("only", None)
    extra = pp.parse_args(["x", "x", "x", "0", "0", "60"] + [f"--{k}={v}" for k, v in opts.items()])[-1]
    out = HERE / "work" / "placement_eval" / label
    rows = []
    rng = random.Random(20261126)
    for n, (key, cam) in enumerate(street_cams()):
        angle = rng.uniform(0, 2 * math.pi)                # drawn for every photo, so --only keeps the same start
        if only is not None and str(n) != only:
            continue
        tx, ty = cam["eye"][:2]
        x0, y0 = tx + offset * math.cos(angle), ty + offset * math.sin(angle)
        hfov = math.degrees(2 * math.atan(cam["width"] / 2 / cam["params"][0]))
        kwargs = dict(extra)
        said = []
        kwargs.setdefault("radius", 40.0)
        try:
            r = pp.place(photo_store.camera_photo(cam), TRIS, out / key, x0, y0, hfov, key=key, ground=GROUND,
                         log=said.append, **kwargs)
        except SystemExit as e:                      # refused (--min-sky): no pose
            rows.append({"n": n, "key": key, "refused": str(e)})
            print(n, key[:40], "refused", flush=True)
            continue
        b = r["best"]
        dpos = math.hypot(b["east"] - tx, b["north"] - ty)
        dhead = abs((b["heading"] - heading_of(cam) + 180) % 360 - 180)
        sky = next((float(s.split()[1].rstrip("%")) / 100 for s in said if s.startswith("sky ")), None)
        rows.append({"n": n, "key": key, "position_m": round(dpos, 1), "heading_deg": round(dhead, 1),
                     "cost": round(b["cost"], 3), "sky": sky})
        print(n, key[:40], f"{dpos:.1f} m  {dhead:.1f} deg  cost {b['cost']:.3f}", flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    name = out.parent / (label + (f"_{only}" if only is not None else "") + ".json")
    name.write_text(json.dumps(rows, indent=1) + "\n")
    placed = [r for r in rows if "position_m" in r]
    if placed:
        within = sum(r["position_m"] <= 5 and r["heading_deg"] <= 5 for r in placed)
        print(f"{label}: {len(placed)} placed, {len(rows) - len(placed)} refused; within 5 m and 5 deg: {within}; "
              f"median {sorted(r['position_m'] for r in placed)[len(placed) // 2]} m")


if __name__ == "__main__":
    main()
