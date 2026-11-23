"""sfm_try.py <photos_root> <work_dir> <subfolder> [<subfolder> ...]
Feasibility test: can COLMAP (pycolmap) register the collected Shibuya crossing photos into one model?
Photos are symlinked flat as <folder>__<file> into work/images, SIFT (darkness adaptive) at 1600 px,
exhaustive matching, incremental mapping. Prints how many images each model registered."""
import sys
import time
from pathlib import Path

import pycolmap

root, work = Path(sys.argv[1]), Path(sys.argv[2])
img_dir = work / "images"
img_dir.mkdir(parents=True, exist_ok=True)
n = 0
for sub in sys.argv[3:]:
    for p in sorted((root / sub).iterdir()):
        if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
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
    pycolmap.extract_features(db, img_dir, camera_mode=pycolmap.CameraMode.PER_IMAGE, extraction_options=ex)
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
