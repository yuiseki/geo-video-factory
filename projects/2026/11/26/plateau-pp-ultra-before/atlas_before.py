"""Build the photo atlases of an area with today's world-model tools, step by step, into work/<name>/.

    python projects/2026/11/26/plateau-pp-ultra-before/atlas_before.py <step> <name> [...]

Steps, in order (each reads what the previous wrote; run from the repository root with packages/pipeline's Python,
under the host's resource limits):

    photos   the area's photo set (areas.json "photos": a tokyo_cc0 manifest of the liminal project) staged from the
             shared photo store as work/<name>/images/<n>_<ref>.jpg symlinks; blocklisted photos left out
    tris     the PLATEAU++ v0.1.0 mesh in east/north/up metres around the area's centre (buildings/plateau_mesh.py)
    sfm      pycolmap: SIFT on every image, exhaustive matching, incremental mapping -> work/<name>/sfm/sparse/<k>
    anchors  geo/photo_place.py on up to --anchors geotagged photos within 300 m that the largest SfM model holds
             (the skyline search: today's only way to place a photo on the city without SfM)
    world    world_model/sfm_to_world.py with every anchor -> work/<name>/world/cams.json
    layers   world_model/time_layers.py -> work/<name>/world/layers/cams_<day|dusk|night>.json
    atlas    world_model/build_atlas.py for one building group, "around": every PLATEAU++ triangle within 250 m,
             with the options the Shibuya CC0 atlases used, for day and night -> work/<name>/atlas_<day|night>/

The sfm step can run on any machine with the repository and a photo store holding the same refs (the image names
are the refs, so a model made elsewhere reads the same here). before.py adds work/<name>/atlas_<t>/model.obj to the
scene when it exists. A step that fails says so and stops: a failure is part of the record of today's tools.
"""
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
PIPE = REPO / "packages" / "pipeline"
sys.path.insert(0, str(PIPE))
LIMINAL = REPO / "projects/2026/11/20/liminal-space-city-walk-with-bgm"


def area_of(name: str) -> tuple[dict, dict]:
    conf = json.loads((HERE / "areas.json").read_text(encoding="utf-8"))
    return conf, next(a for a in conf["areas"] if a["name"] == name)


def work(name: str) -> Path:
    d = HERE / "work" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def rows(area: dict) -> list[dict]:
    manifest = LIMINAL / "research" / "tokyo_cc0" / f"{area['photos']}_manifest.json"
    return [r for r in json.loads(manifest.read_text(encoding="utf-8"))["photos"] if r.get("photo")]


def image_name(i: int, ref: str) -> str:
    return f"{i:03d}_" + re.sub(r"[^0-9A-Za-z_.-]+", "_", ref.split(":", 1)[1])[:90].rsplit(".", 1)[0] + ".jpg"


def step_photos(name, area, opts):
    from photos import photo_guard, photo_store
    d = work(name) / "images"
    d.mkdir(exist_ok=True)
    index, n = {}, 0
    for i, row in enumerate(rows(area)):
        src = photo_store.path(row["photo"])
        if src is None:
            print("not in this store:", row["photo"])
            continue
        try:
            photo_guard.check(src)
        except photo_guard.BlockedPhoto as e:
            print("left out:", e)
            continue
        link = d / image_name(i, row["photo"])
        if not link.exists():
            link.symlink_to(src)
        index[link.name] = {"ref": row["photo"], "coordinates": row.get("coordinates")}
        n += 1
    (work(name) / "images.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n")
    print(f"{n} photos staged")


def step_tris(name, area, opts):
    info = json.loads((HERE / "out" / name / "scene.json").read_text())
    lon, lat = area["center"]
    subprocess.run([sys.executable, str(PIPE / "buildings/plateau_mesh.py"), str(REPO / info["plateau_pp"]),
                    str(work(name) / "tris.npz"), str(lon), str(lat)], check=True)


def step_sfm(name, area, opts):
    import pycolmap
    w = work(name)
    db, img = w / "sfm" / "database.db", w / "images"
    (w / "sfm" / "sparse").mkdir(parents=True, exist_ok=True)
    t = time.time()
    if not db.exists():
        ex = pycolmap.FeatureExtractionOptions()
        ex.max_image_size = 1600
        ex.sift.max_num_features = 8192
        pycolmap.extract_features(db, img, camera_mode=pycolmap.CameraMode.PER_IMAGE, extraction_options=ex)
        print("extract", round(time.time() - t), "s", flush=True)
        t = time.time()
        pycolmap.match_exhaustive(db)
        print("match", round(time.time() - t), "s", flush=True)
    t = time.time()
    maps = pycolmap.incremental_mapping(db, img, w / "sfm" / "sparse")
    print("map", round(time.time() - t), "s", flush=True)
    summary = {str(k): rec.num_reg_images() for k, rec in maps.items()}
    (w / "sfm" / "models.json").write_text(json.dumps(summary, indent=1) + "\n")
    print("models (images each):", summary)


def largest_model(w: Path) -> Path:
    summary = json.loads((w / "sfm" / "models.json").read_text())
    if not summary:
        raise SystemExit("SfM made no model")
    return w / "sfm" / "sparse" / max(summary, key=lambda k: summary[k])


def step_anchors(name, area, opts):
    import pycolmap
    from PIL import Image
    w = work(name)
    model = pycolmap.Reconstruction(str(largest_model(w)))
    registered = {img.name for img in model.images.values()}
    index = json.loads((w / "images.json").read_text())
    tris = np.load(w / "tris.npz")
    ox, oy = (float(v) for v in tris["origin"])
    kx, ky = 111320.0 * math.cos(math.radians(oy)), 110950.0
    cand = []
    for nm, rec in index.items():
        if nm in registered and rec.get("coordinates"):
            e, n = (rec["coordinates"][0] - ox) * kx, (rec["coordinates"][1] - oy) * ky
            if math.hypot(e, n) < 300:
                cand.append((math.hypot(e, n), nm, e, n))
    cand.sort()
    print(f"{len(cand)} geotagged photos in the model within 300 m; trying {min(len(cand), int(opts.get('anchors', 6)))}")
    for _, nm, e, n in cand[: int(opts.get("anchors", 6))]:
        hfov = 60.0
        try:
            exif = Image.open(w / "images" / nm).getexif().get_ifd(0x8769)
            f35 = exif.get(0xA405)
            if f35:
                hfov = math.degrees(2 * math.atan(36 / (2 * float(f35))))
        except Exception:
            pass
        out = w / "anchors" / Path(nm).stem
        if (out / "cams.json").exists():
            continue
        out.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([sys.executable, str(PIPE / "geo/photo_place.py"), str(w / "images" / nm), str(w / "tris.npz"),
                            str(out), f"{e:.1f}", f"{n:.1f}", f"{hfov:.1f}", "--radius=60", f"--key={Path(nm).stem}"],
                           capture_output=True, text=True)
        (out / "run.log").write_text(r.stdout + r.stderr)
        print(nm, "placed" if r.returncode == 0 and (out / "cams.json").exists() else f"failed ({r.returncode})", flush=True)


def step_world(name, area, opts):
    w = work(name)
    anchors = sorted(str(p) for p in (w / "anchors").glob("*/cams.json"))
    if not anchors:
        raise SystemExit("no anchor was placed")
    subprocess.run([sys.executable, "-m", "world_model.sfm_to_world", str(largest_model(w)), str(w / "images"),
                    str(w / "tris.npz"), str(w / "world"), *anchors], check=True, cwd=PIPE)


def step_layers(name, area, opts):
    w = work(name)
    subprocess.run([sys.executable, "-m", "world_model.time_layers", str(w / "world" / "cams.json"),
                    str(w / "world" / "layers"), f"--scene={w / 'tris.npz'}"], check=True, cwd=PIPE)


def step_atlas(name, area, opts):
    w = work(name)
    tris = np.load(w / "tris.npz")
    t = tris["tris"]
    near = np.linalg.norm(t.mean(axis=1)[:, :2], axis=1) < 250
    group = w / "group"
    group.mkdir(exist_ok=True)
    np.savez(group / "buildings.npz", origin=tris["origin"], around=t[near])
    for layer in ("day", "night"):
        cams = w / "world" / "layers" / f"cams_{layer}.json"
        if not cams.exists() or not json.loads(cams.read_text()):
            print(f"no {layer} photos: no {layer} atlas")
            continue
        subprocess.run([sys.executable, "-u", "-m", "world_model.build_atlas", str(group), "around", str(w / "tris.npz"),
                        str(w / f"atlas_{layer}"), "--keep=10", "--patch=3", "--agree=25", "--smooth=2", "--fill=mean",
                        "--eras=2", "--width=8192", str(cams)], check=True, cwd=PIPE)


STEPS = {"photos": step_photos, "tris": step_tris, "sfm": step_sfm, "anchors": step_anchors, "world": step_world,
         "layers": step_layers, "atlas": step_atlas}


def main() -> None:
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in sys.argv[1:] if a.startswith("--"))
    step, *names = [a for a in sys.argv[1:] if not a.startswith("--")]
    for name in names:
        _, area = area_of(name)
        print(f"== {step} {name}", flush=True)
        STEPS[step](name, area, opts)


if __name__ == "__main__":
    main()
