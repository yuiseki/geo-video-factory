"""sfm_try.py <photos_root> <work_dir> <subfolder> [<subfolder> ...] [--threads=N] [--camera=single]
Feasibility test: can COLMAP (pycolmap) register the collected Shibuya crossing photos into one model?
Photos are symlinked flat as <folder>__<file> into work/images, SIFT (darkness adaptive) at 1600 px,
exhaustive matching, incremental mapping. Prints how many images each model registered.
--threads caps the extraction threads (default: all cores). Each thread holds one image's SIFT pyramid,
so on a many-core host under a memory cap the default can be killed: match it to the CPU quota.
--camera=single shares one set of intrinsics among all photos: only for a set taken with one camera at
one zoom (the default estimates a focal length per photo, which a mixed collection needs)."""
import sys
import time
from pathlib import Path

import pycolmap

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "world_model"))
import photo_guard  # noqa: E402  photo_blocklist.tsv: never take these in

threads = [int(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--threads=")]
single = "--camera=single" in sys.argv
sys.argv = [a for a in sys.argv if not a.startswith("--")]
root, work = Path(sys.argv[1]), Path(sys.argv[2])
img_dir = work / "images"
img_dir.mkdir(parents=True, exist_ok=True)
n = 0
for sub in sys.argv[3:]:
    for p in sorted((root / sub).iterdir()):
        if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            try:
                photo_guard.check(p)
            except photo_guard.BlockedPhoto as e:
                print("dropped", e, flush=True)
                continue
            link = img_dir / f"{sub.replace('/', '_')}__{p.name}"
            if not link.exists():
                link.symlink_to(p)
            n += 1
print("images", n, flush=True)

db = work / "database.db"
t = time.time()
if not db.exists():
    ex = pycolmap.FeatureExtractionOptions()
    ex.max_image_size = 1600
    ex.sift.max_num_features = 8192
    ex.sift.darkness_adaptivity = True
    ex.sift.estimate_affine_shape = False
    if threads:
        ex.num_threads = threads[0]
    mode = pycolmap.CameraMode.SINGLE if single else pycolmap.CameraMode.PER_IMAGE
    pycolmap.extract_features(db, img_dir, camera_mode=mode, extraction_options=ex)
    print("extract", round(time.time() - t), "s", flush=True)
    t = time.time()
    pycolmap.match_exhaustive(db)
    print("match", round(time.time() - t), "s", flush=True)
t = time.time()
out = work / "sparse"
out.mkdir(exist_ok=True)
maps = pycolmap.incremental_mapping(db, img_dir, out)
print("map", round(time.time() - t), "s", flush=True)
for k, rec in sorted(maps.items(), key=lambda kv: -kv[1].num_reg_images()):
    print(f"model {k}: {rec.num_reg_images()} images, {rec.num_points3D()} points, "
          f"err {rec.compute_mean_reprojection_error():.2f}px")
    names = sorted(img.name for img in rec.images.values())
    print("  ", " ".join(names))
