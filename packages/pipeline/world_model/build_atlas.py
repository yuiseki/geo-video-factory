"""python -m world_model.build_atlas <work_dir> <building> <scene tris.npz> <out_dir> [--texel=0.05] [--width=4096] [--keep=6] [--fuse=face|median] [--few=3] [--patch=metres] [--agree=colour distance] [--smooth=0.7] [--expose=0] [--fill=mean] [--split=metres] [--changing=colour distance] [--eras=k] [--era=0]
       [--only=<word in the camera key>,...] <cams.json>...
The texture of one building, read back from every placed photo, and the building as an OBJ that uses it.
<work_dir>/buildings.npz comes from geometry_map.py; each cams.json is what photo_place.py writes.
Writes atlas.png, seen.png (how many photos saw each texel), quality.png (how well the best photo saw it, 0..255:
photo pixels across a texel, surface_atlas.texel_quality), model.obj, model.mtl and report.json.
--fuse=face (default) takes each face from as few photos as possible; median blends them (surface_atlas.fuse).
Texels that no photo saw are grey in atlas.png and are counted in report.json; they are not made up."""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from photos import photo_guard
from photos.photo_store import camera_photo  # a camera names its photo by ref, or by path
from world_model import surface_atlas as sa

Image.MAX_IMAGE_PIXELS = None
UNSEEN = (128, 128, 128)
ROOF = (92, 92, 96)


def main(argv):
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--"))
    work, name, scene_path, out = [a for a in argv if not a.startswith("--")][:4]
    cam_files = [a for a in argv if not a.startswith("--")][4:]
    texel, width = float(opts.get("texel", 0.05)), int(opts.get("width", 4096))
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    tris = np.load(Path(work) / "buildings.npz")[name].astype(float)
    scene = np.load(scene_path)["tris"].astype(float)
    groups = sa.planar_faces(tris)
    if "split" in opts:
        # one plane can run through many buildings of a street; cut it into cells so that a chart is not a
        # mostly empty rectangle as long as the street
        cell = np.floor(tris.mean(axis=1) / float(opts["split"])).astype(np.int64)
        groups = [g[(cell[g] == c).all(axis=1)] for g in groups for c in np.unique(cell[g], axis=0)]
    charts = [sa.chart(tris[g], texel) for g in groups]
    pos, rows = sa.pack([c[1].shape for c in charts], width)
    cams = {}
    for f in cam_files:
        cams.update(json.loads(Path(f).read_text()))
    if "only" in opts:
        cams = {k: c for k, c in cams.items() if any(word in k for word in opts["only"].split(","))}
    cams = photo_guard.drop_blocked(cams)              # photo_blocklist.tsv: never paint these
    # every texel that lies on a face, as one long list: the atlas is mostly empty, and one call per photo over
    # the list is far faster than one per face
    where, points, normal_of, face_of, patch_of = [], [], [], [], []
    patch_px = max(1, int(round(float(opts.get("patch", 0)) / texel))) if float(opts.get("patch", 0)) > 0 else 10 ** 9
    for f, ((pts, mask, normal, _), (y, x)) in enumerate(zip(charts, pos)):
        yy, xx = np.nonzero(mask)
        where.append((y + yy) * width + x + xx)
        points.append(pts[mask])
        normal_of.append(np.broadcast_to(normal, (len(yy), 3)))
        face_of.append(np.full(len(yy), f))
        patch_of.append(np.stack([np.full(len(yy), f), yy // patch_px, xx // patch_px], axis=1))
    where, points, normal_of = np.concatenate(where), np.concatenate(points), np.concatenate(normal_of)
    face_of = np.concatenate(face_of)
    # --patch=3 lets every 3 m square of a face choose its own photo instead of the whole face choosing one
    patches, face_of = np.unique(np.concatenate(patch_of), axis=0, return_inverse=True)
    face_of = face_of.ravel()
    index = {tuple(p): i for i, p in enumerate(patches.tolist())}
    pairs = [(i, index[q]) for (f, y, x), i in index.items() for q in ((f, y + 1, x), (f, y, x + 1)) if q in index]
    stack = sa.TopK(len(where), int(opts.get("keep", 6)))
    corners_xyz = tris.reshape(-1, 3)
    used = {}
    for key, cam in cams.items():
        # skip photos that do not have the building in the frame at all
        pc = sa.to_camera(corners_xyz, cam)
        front = pc[:, 2] > 1.0
        fx, fy, cx, cy = cam["params"]
        px, py = pc[front, 0] / pc[front, 2] * fx + cx, pc[front, 1] / pc[front, 2] * fy + cy
        if not ((px > 0) & (px < cam["width"]) & (py > 0) & (py < cam["height"])).any():
            continue
        image = np.asarray(photo_guard.open_photo(camera_photo(cam)).convert("RGB"))
        if image.shape[1] != cam["width"]:
            raise SystemExit(f"{key}: photo is {image.shape[1]} wide, camera says {cam['width']}")
        depth = sa.depth_buffer(scene, cam)
        colours, weights = sa.observe(image, points, normal_of, cam, depth)
        used[key] = int((weights > 0).sum())
        if used[key]:
            stack.add(colours, weights, view=len(used) - 1)
        print(key[-50:], "saw", used[key], "texels", flush=True)
    gains = None
    if opts.get("expose", "1") != "0" and used:
        cols_, w_, v_ = stack.arrays(views=True)
        gains = sa.exposure_gains(cols_, w_, v_, few=int(opts.get("few", 3)))
        stack.colours *= gains[np.maximum(v_, 0)][..., None].astype(np.float32)
    eras = None
    if int(opts.get("eras", 1)) > 1 and used:
        # the facade was refitted, or repainted, during the years the photos span: keep one of its looks
        cols_, w_, v_ = stack.arrays(views=True)
        share, both = sa.view_agreement(cols_, w_, v_, close=float(opts.get("agree", 25)) or 25.0)
        eras = sa.view_clusters(share, both, k=int(opts["eras"]))
        want = int(opts.get("era", 0))
        stack.weights[(eras != want)[np.maximum(v_, 0)] | (v_ < 0)] = 0
        names = list(used)
        for e in range(int(eras.max()) + 1):
            print("era", e, [names[i][-40:] for i in np.nonzero(eras == e)[0]][:40], flush=True)
    if opts.get("fuse", "face") == "face":
        part, chosen = sa.fuse_by_face(*stack.arrays(views=True), face_of, cap=1.0 / texel ** 2,
                                       agree=float(opts.get("agree", 0)) or None, few=int(opts.get("few", 3)),
                                       changing=float(opts.get("changing", 0)) or None,
                                       pairs=np.array(pairs).reshape(-1, 2), strength=float(opts.get("smooth", 0.7)))
        took = np.bincount(chosen[chosen >= 0], minlength=len(used))
        used = {k: [n, int(took[i])] for i, (k, n) in enumerate(used.items())}      # texels seen, texels taken
    else:
        part, _ = sa.fuse(*stack.arrays(), few=int(opts.get("few", 3)))
    fused = np.full((rows * width, 3), np.nan, np.float32)
    fused[where] = part
    count = np.zeros(rows * width, np.int32)
    count[where] = stack.count
    quality = np.zeros(rows * width, np.float32)
    if used:
        quality[where] = sa.texel_quality(stack.weights.T, texel)     # TopK keeps (k, n)
    fused, count = fused.reshape(rows, width, 3), count.reshape(rows, width)
    if opts.get("fill") == "mean" and np.isfinite(part).any():
        # a face no photo saw takes the mean colour of what was seen: of its own face where there is some, of the
        # whole building otherwise. seen.png still says which texels are observed and which are this guess.
        seen_t = np.isfinite(part[:, 0])
        whole = part[seen_t].mean(axis=0)
        real_face = np.concatenate([np.full(len(c[1].nonzero()[0]), f) for f, c in enumerate(charts)])
        tot = np.zeros((len(charts), 3)); num = np.zeros(len(charts))
        np.add.at(tot, real_face[seen_t], part[seen_t]); np.add.at(num, real_face[seen_t], 1)
        mean = np.where(num[:, None] > 0, tot / np.maximum(num, 1)[:, None], whole)
        # roofs are hardly ever seen from the street; the few texels a sign bled onto must not paint them
        flat = np.array([abs(c[2][2]) > 0.5 for c in charts])
        thin = num < 0.2 * np.bincount(real_face, minlength=len(charts))
        mean[flat & thin] = ROOF
        guess = part.copy()
        guess[~seen_t] = mean[real_face[~seen_t]]
        fused.reshape(-1, 3)[where] = guess
    atlas = np.where(np.isnan(fused), np.array(UNSEEN, np.float32), fused).clip(0, 255).astype(np.uint8)
    Image.fromarray(atlas).save(out / "atlas.png")
    Image.fromarray((np.clip(count, 0, 5) * 51).astype(np.uint8)).save(out / "seen.png")
    Image.fromarray((quality.reshape(rows, width) * 255).round().astype(np.uint8)).save(out / "quality.png")

    report = {"building": name, "texel_m": texel, "atlas": [width, rows], "photos": used, "faces": [],
              "gains": None if gains is None else dict(zip(used, np.round(gains, 3).tolist())),
              "eras": None if eras is None else dict(zip(used, eras.tolist()))}
    lines, vt = ["mtllib model.mtl", "usemtl atlas"], 1
    for g, (points, mask, normal, corners), (y, x) in zip(groups, charts, pos):
        r, k = mask.shape
        part = count[y:y + r, x:x + k][mask]
        report["faces"].append({"azimuth": round(float(np.degrees(np.arctan2(normal[0], normal[1])) % 360), 1),
                                "tilt": round(float(np.degrees(np.arcsin(normal[2]))), 1),
                                "area_m2": round(float(mask.sum() * texel ** 2), 1),
                                "seen": round(float((part > 0).mean()), 3) if part.size else 0.0})
        for tri, uv in zip(tris[g], corners):
            for p, (cu, cv) in zip(tri, uv):
                lines.append("v %.4f %.4f %.4f" % tuple(p))
                lines.append("vt %.6f %.6f" % ((x + cu) / width, 1 - (y + cv) / rows))
            lines.append("f %d/%d %d/%d %d/%d" % (vt, vt, vt + 1, vt + 1, vt + 2, vt + 2))
            vt += 3
    (out / "model.obj").write_text("\n".join(lines) + "\n")
    (out / "model.mtl").write_text("newmtl atlas\nKd 1 1 1\nmap_Kd atlas.png\n")
    walls = [f for f in report["faces"] if abs(f["tilt"]) < 20]
    area = sum(f["area_m2"] for f in walls)
    report["wall_area_m2"] = round(area, 1)
    report["wall_seen"] = round(sum(f["area_m2"] * f["seen"] for f in walls) / max(area, 1e-9), 3)
    report["faces"].sort(key=lambda f: -f["area_m2"])
    (out / "report.json").write_text(json.dumps(report, indent=1))
    print("walls", report["wall_area_m2"], "m2, seen", report["wall_seen"], "atlas", width, "x", rows)
    for f in report["faces"][:12]:
        print(" ", f)


if __name__ == "__main__":
    main(sys.argv[1:])
