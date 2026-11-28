"""The repository's usual SfM (pycolmap, as atlas_before.py's step_sfm), georeferenced from the photos' GPS.

    python colmap_sfm.py <image dir> <work dir> [--threads=6]
    python colmap_sfm.py --georef <COLMAP text model> <image dir> <out dir>    another tool's model, same fit

SIFT on every image (long side 1600 px, up to 8,192 features, one camera per image from its EXIF), exhaustive
matching, incremental mapping. Every model it makes is put into metres east, north, up with
world_model.sim3.from_positions (the cameras' mean up is the world's up; scale, heading and shift from the GPS
fixes, horizontal least squares; the eye at 1.6 m) and written as a COLMAP text model with enu_origin.txt in
<work dir>/geo/<k>/, so sfm_compare.py reads it like visloc-rs's output. <work dir>/models.json gives the images
per model and the seconds each stage took.
"""
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

R_EARTH = 6378137.0
EYE = 1.6


def sphere_enu(lon, lat, origin):
    return (math.radians(lon - origin[0]) * R_EARTH * math.cos(math.radians(origin[1])),
            math.radians(lat - origin[1]) * R_EARTH)


def georeference(sfm, gps, eye_z=EYE):
    """{name: {R, C}} in metres east, north, up, from {name: (R_sfm, C_sfm)} and {name: (east, north)} GPS."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "packages" / "pipeline"))
    from world_model import sim3
    names = [k for k in sfm if k in gps]
    sim = sim3.from_positions([sfm[k][0] for k in names], [sfm[k][1] for k in names],
                              [gps[k] for k in names], eye_z)
    out = {}
    for k, (r, c) in sfm.items():
        rw, eye = sim3.camera(sim, np.asarray(r, float), np.asarray(c, float))
        out[k] = {"R": rw, "C": eye}
    return out


def write_model(d, cams, origin):
    """images.txt (world -> camera quaternion and translation) and enu_origin.txt (lat lon alt) in d."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sfm_compare import r_to_quat
    d.mkdir(parents=True, exist_ok=True)
    lines = ["# IMAGE_ID QW QX QY QZ TX TY TZ CAMERA_ID NAME"]
    for i, (name, cam) in enumerate(sorted(cams.items()), 1):
        r = np.asarray(cam["R"], float)
        t = -r @ np.asarray(cam["C"], float)
        q = r_to_quat(r)
        lines += [" ".join(map(str, [i, *q, *t, i, name])), ""]
    (d / "images.txt").write_text("\n".join(lines) + "\n")
    if origin is not None:
        (d / "enu_origin.txt").write_text(f"# lat lon alt\n{origin[1]} {origin[0]} 0\n")


def read_model(d):
    """{name: (R, C)} from a COLMAP text model's images.txt, in its own frame."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sfm_compare import quat_to_r
    lines = [ln for ln in (Path(d) / "images.txt").read_text().splitlines() if not ln.startswith("#")]
    out = {}
    for ln in lines[0::2]:
        f = ln.split()
        if len(f) < 10:
            continue
        r, t = quat_to_r(*map(float, f[1:5])), np.array(list(map(float, f[5:8])))
        out[f[9]] = (r, -r.T @ t)
    return out


def georeference_model(model, fixes, out):
    """Put a COLMAP text model made by any tool on the photos' GPS ({name: (lon, lat)}), written to out/0/."""
    sfm = read_model(model)
    origin = tuple(np.mean(list(fixes.values()), axis=0))
    gps = {k: sphere_enu(*v, origin) for k, v in fixes.items()}
    write_model(Path(out) / "0", georeference(sfm, gps), origin)


def exif_lonlat(path):
    from PIL import Image
    g = Image.open(path).getexif().get_ifd(0x8825)
    if 2 not in g or 4 not in g:
        return None
    lat, lon = (float(a) + float(b) / 60 + float(c) / 3600 for a, b, c in (g[2], g[4]))
    return (-lon if g.get(3) == "W" else lon), (-lat if g.get(1) == "S" else lat)


def main(argv):
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in argv if a.startswith("--"))
    paths = [Path(a) for a in argv if not a.startswith("--")]
    if "georef" in opts:
        model, img, out = paths
        fixes = {p.name: exif_lonlat(p) for p in sorted(img.glob("*.jpg"))}
        georeference_model(model, {k: v for k, v in fixes.items() if v}, out)
        return
    img, work = paths
    import zlib  # noqa: F401  (pycolmap's wheel needs it loaded first)
    import pycolmap
    work.mkdir(parents=True, exist_ok=True)
    db, sparse = work / "database.db", work / "sparse"
    sparse.mkdir(exist_ok=True)
    took = {}
    t = time.time()
    ex = pycolmap.FeatureExtractionOptions()
    ex.max_image_size = 1600
    ex.sift.max_num_features = 8192
    ex.num_threads = int(opts.get("threads", 6))     # every core at once runs a many-core host out of memory
    pycolmap.extract_features(db, img, camera_mode=pycolmap.CameraMode.PER_IMAGE, extraction_options=ex)
    took["extract_s"] = round(time.time() - t)
    t = time.time()
    pycolmap.match_exhaustive(db)
    took["match_s"] = round(time.time() - t)
    t = time.time()
    maps = pycolmap.incremental_mapping(db, img, sparse)
    took["map_s"] = round(time.time() - t)
    fixes = {p.name: exif_lonlat(p) for p in sorted(img.glob("*.jpg"))}
    fixes = {k: v for k, v in fixes.items() if v}
    origin = tuple(np.mean(list(fixes.values()), axis=0))
    gps = {k: sphere_enu(*v, origin) for k, v in fixes.items()}
    models = {}
    for k, rec in maps.items():
        sfm = {}
        for im in rec.images.values():
            pose = im.cam_from_world() if callable(im.cam_from_world) else im.cam_from_world
            r = np.asarray(pose.rotation.matrix(), float)
            sfm[im.name] = (r, -r.T @ np.asarray(pose.translation, float))
        models[str(k)] = len(sfm)
        if sum(1 for n in sfm if n in gps) >= 3:
            write_model(work / "geo" / str(k), georeference(sfm, gps), origin)
    (work / "models.json").write_text(json.dumps({"images": models, **took}, indent=1) + "\n")
    print("models (images each):", models, took)


if __name__ == "__main__":
    main(sys.argv[1:])
