"""sfm_to_world.py <sparse model dir> <images dir> <scene tris.npz> <out_dir> <anchor cams.json>... [--radius=450]
       [--min-track=3] [--trim=3.0] [--min-points=40]

Every photo of an SfM model as a camera in the city model's metric frame.

The SfM model knows how the photos stand to each other but not how large the
world is or where north is. One or more photos already placed on the city
model (photo_place.py's cams.json) give a first similarity; the SfM points are
then laid onto the city model's surfaces (sim3.fit_to_surface). With a single
anchor the scale is searched first.

Writes cams.json (all registered photos, same layout as photo_place.py, keyed
by the SfM image name without its extension), align.json (the similarity, the
fit, how far each anchor ended from where it was given) and top.png (surfaces
grey, SfM points red, cameras blue, anchors green).
"""
import json
import sys
import zlib  # noqa: F401  (pycolmap's wheel needs it loaded first)
from pathlib import Path

import numpy as np
import pycolmap
from scipy.spatial import cKDTree

import sim3


def intrinsics(cam):
    p = list(cam.params)
    model = cam.model.name
    if model in ("SIMPLE_PINHOLE", "SIMPLE_RADIAL", "RADIAL", "SIMPLE_RADIAL_FISHEYE"):
        f, cx, cy = p[:3]
        return [f, f, cx, cy], p[3:]
    if model in ("PINHOLE", "OPENCV", "FULL_OPENCV"):
        return p[:4], p[4:]
    raise SystemExit(f"camera model {model} is not handled")


def main(argv):
    opts = dict(a[2:].split("=") for a in argv if a.startswith("--"))
    pos = [a for a in argv if not a.startswith("--")]
    model_dir, img_dir, scene, out = Path(pos[0]), Path(pos[1]), pos[2], Path(pos[3])
    out.mkdir(parents=True, exist_ok=True)
    rec = pycolmap.Reconstruction(str(model_dir))
    images, seen = {}, {}
    for img in rec.images.values():
        if hasattr(img, "has_pose") and not img.has_pose:
            continue
        pose = img.cam_from_world() if callable(img.cam_from_world) else img.cam_from_world
        images[img.name] = (pose.rotation.matrix(), np.array(img.projection_center()), rec.cameras[img.camera_id])
        seen[img.name] = int(sum(1 for p in img.points2D if p.has_point3D()))
    real = {name: (img_dir / name).resolve() for name in images}

    anchors = {}
    for f in pos[4:]:
        for key, c in json.loads(Path(f).read_text()).items():
            hit = [n for n, p in real.items() if p == Path(c["photo"]).resolve()]
            if hit:
                anchors[hit[0]] = (np.array(c["Rw"]), np.array(c["eye"]))
            else:
                print("anchor", key, "is not in the SfM model")
    if not anchors:
        raise SystemExit("no anchor photo is registered in this SfM model")

    min_track = int(opts.get("min-track", 3))
    pts = np.array([p.xyz for p in rec.points3D.values() if p.track.length() >= min_track and p.error < 2.0])
    print(f"{len(images)} photos, {len(pts)} points with tracks >= {min_track}, anchors {list(anchors)}")

    tris = np.load(scene)["tris"].astype(np.float64)
    centre = np.mean([eye for _, eye in anchors.values()], axis=0)
    near = np.linalg.norm(tris.mean(axis=1)[:, :2] - centre[:2], axis=1) < float(opts.get("radius", 450))
    surf, normals = sim3.sample_surface(tris[near], spacing=0.5)
    tree = cKDTree(surf)

    names = list(anchors)
    sfm_side = [(images[n][0], images[n][1]) for n in names]
    world_side = [anchors[n] for n in names]
    sim0 = sim3.from_anchors(sfm_side, world_side)
    soft = [(images[n][1], anchors[n][1]) for n in names]
    trim = float(opts.get("trim", 3.0))
    tried = []
    if len(names) == 1:
        # scale unknown: put the median point 20..300 m from the anchor and keep the best fit
        C = images[names[0]][1]
        d = np.median(np.linalg.norm(pts - C, axis=1))
        scales = np.geomspace(20, 300, 25) / d
    else:
        scales = sim0[0] * np.array([0.85, 0.92, 1.0, 1.08, 1.18])
    A = sim0[1]
    Cs_mean = np.mean([c for _, c in sfm_side], axis=0)
    Cw_mean = np.mean([c for _, c in world_side], axis=0)
    sub = pts[:: max(1, len(pts) // 4000)]
    for s in scales:
        start = (s, A, Cw_mean - s * A @ Cs_mean)
        sim, med, frac = sim3.fit_to_surface(sub, surf, normals, start, anchors=soft, trim=trim, rounds=6, tree=tree)
        ok = sim3.plausible(sim, s)
        near1 = sim3.support(sub, tree, sim, within=1.0) if ok else 0.0
        tried.append((-near1, sim, med, frac, s))
        print(f"  start scale {s:8.3f} -> scale {sim[0]:8.3f}, median {med:.2f} m, kept {frac:.2f}, "
              f"within 1 m {near1:.2f}{'' if ok else ' (scale ran away, rejected)'}")
    tried.sort(key=lambda r: r[0])
    if tried[0][0] == 0.0:
        raise SystemExit("every start ran away: no alignment")
    sim, med, frac = sim3.fit_to_surface(pts, surf, normals, tried[0][1], anchors=soft, trim=trim, rounds=10, tree=tree)
    print(f"fit: scale {sim[0]:.4f}, median distance {med:.2f} m over {frac:.0%} of the points")

    cams, report = {}, {"scale": sim[0], "turn": sim[1].tolist(), "shift": sim[2].tolist(), "median_m": med,
                        "kept": frac, "within_1m": sim3.support(pts, tree, sim), "points": len(pts), "starts": [[r[4], r[1][0], r[2], r[3]] for r in tried],
                        "anchors": {}}
    min_points = int(opts.get("min-points", 40))
    for name, (Rs, Cs, cam) in images.items():
        if seen[name] < min_points and name not in anchors:
            # a photo hung on a handful of matches (an interior, a close-up of a poster) is registered but not placed
            print(f"left out, {seen[name]} points: {name[:70]}")
            continue
        Rw, eye = sim3.camera(sim, Rs, Cs)
        params, extra = intrinsics(cam)
        cams[Path(name).stem] = {"name": name, "photo": str(real[name]), "eye": eye.tolist(), "Rw": Rw.tolist(),
                                 "width": cam.width, "height": cam.height, "model": "PINHOLE", "params": params,
                                 "distortion": extra, "sfm_model": cam.model.name,
                                 "sfm_points": seen[name],   # few points: a pose not to trust
                                 "fov_v": float(np.degrees(2 * np.arctan(cam.height / 2 / params[1])))}
        if name in anchors:
            Ra, ea = anchors[name]
            turn = np.degrees(np.arccos(np.clip((np.trace(Rw @ Ra.T) - 1) / 2, -1, 1)))
            report["anchors"][name] = {"moved_m": float(np.linalg.norm(eye - ea)), "turned_deg": float(turn)}
            print(f"anchor {name[:60]}: {np.linalg.norm(eye - ea):.1f} m and {turn:.1f} deg from where it was given")
    (out / "cams.json").write_text(json.dumps(cams))
    (out / "align.json").write_text(json.dumps(report, indent=1))
    np.save(out / "points_world.npy", sim3.apply(sim, pts).astype(np.float32))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 11))
    wall = np.abs(normals[:, 2]) < 0.3
    ax.plot(surf[wall, 0], surf[wall, 1], ",", color="0.7")
    P = sim3.apply(sim, pts)
    ax.plot(P[:, 0], P[:, 1], ".", ms=1, color="tab:red")
    E = np.array([c["eye"] for c in cams.values()])
    F = np.array([np.array(c["Rw"])[2] for c in cams.values()])
    ax.quiver(E[:, 0], E[:, 1], F[:, 0], F[:, 1], color="tab:blue", scale=40, width=0.002)
    for n, (_, ea) in anchors.items():
        ax.plot(ea[0], ea[1], "o", color="tab:green")
    span = max(150.0, np.percentile(np.abs(E[:, :2] - centre[:2]), 95) * 1.3)
    ax.set_xlim(centre[0] - span, centre[0] + span); ax.set_ylim(centre[1] - span, centre[1] + span)
    ax.set_aspect("equal"); ax.set_title(f"{len(cams)} photos, scale {sim[0]:.3f}, median {med:.2f} m")
    fig.savefig(out / "top.png", dpi=110, bbox_inches="tight")


if __name__ == "__main__":
    main(sys.argv[1:])
