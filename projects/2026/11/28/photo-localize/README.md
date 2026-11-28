# photo-localize: placing a photo without the PLATEAU++ silhouette

`geo.photo_solve` needs a position to start from: the EXIF GPS, within a few
hundred metres. This project tries three outside tools that could give or check
that position from the pixels alone, on the CC0 photos of
`projects/2026/11/20/liminal-space-city-walk-with-bgm/` and the owner's own CC0
phone photos.

| Tool | What it does | Read at | Licence |
|---|---|---|---|
| MegaLoc | one global descriptor per image, nearest photo by cosine | `gmberton/MegaLoc` 5fe0dd6 (2026-07-28), weights `gberton/MegaLoc` a0f3472 | MIT, weights MIT |
| AnyLoc | DINOv2 ViT-G/14 patch features aggregated by VLAD | `AnyLoc/AnyLoc` a9fda68 (2024-03-13), `facebookresearch/dinov2` 7764ea0 | BSD-3-Clause, DINOv2 Apache-2.0 |
| visloc-rs | SfM of unordered photos with GPS priors, then PnP of a new photo against that map | `rsasaki0109/visloc-rs` f692931 (2026-11-27) | MIT OR Apache-2.0 |

None of their code is copied here: the scripts load MegaLoc through torch.hub,
import AnyLoc's `demo/utilities.py` from a clone, and run visloc-rs as a program.

## Visual place recognition (MegaLoc, AnyLoc)

`vpr_eval.py collect` lists every CC0 photo with coordinates (the database) and
every owner photo with GPS (queries only). `describe.py` writes one descriptor per
photo, and `vpr_eval.py score` ranks the database for each photo.

- A database photo is also a query, leave-one-out. It may not match a photo by the
  same creator on the same day, which would be a near copy from the same walk.
- A query is right at k when one of its k best photos stands within 25 m, the usual
  VPR threshold. Recall counts only queries whose nearest eligible photo is within
  25 m at all; the rest cannot be right whatever the model does.
- The positions are the photographers' own: Commons coordinates and phone GPS, both
  off by tens of metres at times, so neither recall reaches 1 even for a perfect
  model.

```bash
python vpr_eval.py collect <cc0 research> <cc0 photos> <gyazo cache> work/items.jsonl
python describe.py megaloc work/items.jsonl work/megaloc.npy
python describe.py anyloc work/items.jsonl work/anyloc.npy <AnyLoc clone> work/anyloc_vocab
python vpr_eval.py score work/items.jsonl work/megaloc.npy work/megaloc_rows.jsonl
```

`work/` holds the lists, descriptors and rows; it is not committed, since the
owner's rows carry photo service IDs.

### Results (2026-11-28)

627 CC0 photos in the database (9 areas of central Tokyo), 555 owner photos as
queries. Recall at 25 m, counting only queries with an eligible photo within 25 m:

| Model | CC0 leave-one-out (201 reachable) R@1 / R@5 / R@10 | top-1 within 250 m (all 627) | owner photos (14 reachable) R@1 |
|---|---|---|---|
| MegaLoc | 0.26 / 0.47 / 0.57 | 0.40 | 0.71 |
| AnyLoc (our vocabulary, half precision) | 0.30 / 0.45 / 0.50 | 0.39 | 0.36 |

Two in five CC0 photos get a top-1 in another district (more than 1 km away). The
database is too thin for retrieval to replace the GPS start of `geo.photo_solve`:
most photos have no other photo of the same view, and the 25 m results of the
literature come with street-view databases taken every few metres. MegaLoc ran in
11 minutes for 1,182 photos on an 8 GB laptop GPU, AnyLoc in 31 minutes (ViT-G at
1,024 px). The two are level: of the 215 reachable queries 52 are right at 1 for
both, 11 only for MegaLoc and 13 only for AnyLoc. The owner column rests on 14
photos and does not separate them.

Environment: Python 3.12, torch 2.11 (CUDA 12.8), torchvision, huggingface_hub,
safetensors, pillow, numpy, einops, fast_pytorch_kmeans and psutil (which
fast_pytorch_kmeans imports without declaring).

## Georeferenced SfM (visloc-rs)

`unordered_sfm_demo` with `--gps-priors-from-exif` (sigma 10 m horizontal, 30 m
vertical), SIFT up to 8,192 keypoints, exhaustive pairs. Full-size 12 MP photos
ran out of an 8 GB memory cap within 3 s even on 4 threads, so the photos are
scaled to a 2,040 or 2,048 px long side first (`prep_sfm.py` for mixed cameras,
one PINHOLE camera per photo from the EXIF 35 mm focal length).
`sfm_vs_gps.py` draws the model's cameras against the GPS fixes on GSI photos.

| Set | Photos | Registered | Mean reprojection | GPS vs model | Time, memory |
|---|---|---|---|---|---|
| Owner, one phone, Akihabara Yodobashi facade, one walk | 40 | 40 | 1.14 px | RMSE 20.5 m | 2 min 18 s, 6.3 GB |
| CC0, Shibuya crossing, 5 creators, years apart | 126 | 28 | 0.52 px | RMSE 25.9 m, 16 of 28 agree | 16 min, 7.0 GB |

- Akihabara: the model holds together (all 40 registered at 1.1 px), but its
  compass is wrong. The phone wrote only 10
  distinct fixes for 40 photos (8 photos share one), the fixes scatter about 20 m
  over a walk of about 20 m, and the robust Sim(3) to them turns the model: every
  photo shows the west face of the store, which stands south-east of the cameras,
  but the model looks north to north-west, about 130 degrees off. GPS noise as
  large as the capture cannot fix the heading; one camera placed by
  `geo.photo_solve` could, and would then place the other 39.
- Shibuya: 248 of 7,875 pairs verify. What registers is mostly one photographer's
  elevated views from Shibuya Stream, and the headings of the three checked by eye
  point at the station as the photos show. Night, crowds, construction and years between photos keep the
  rest apart.

## Five SfM tools on the same photos (2026-11-28)

The same street photos went through five SfM tools on equal terms: long side 1,600 px,
SIFT up to 8,192 features, exhaustive pairs, one camera per photo from its EXIF. Each
model is put on the photos' GPS and scored against 12 cameras that `geo.photo_solve`
placed independently (`sfm_compare.py`; all components of a model are scored, a photo in
two components taking the larger one's pose).

| Tool | Version, licence | How GPS enters | Script |
|---|---|---|---|
| visloc-rs | f692931 | priors in bundle adjustment | `unordered_sfm_demo` (above) |
| COLMAP | pycolmap 4.2.1, BSD-3-Clause | Sim(3) afterwards (`world_model.sim3`) | `colmap_sfm.py` |
| OpenSfM | 1d1f9a3 (last commit with green CI), BSD-2-Clause | priors in bundle adjustment | docker build of the repository |
| AliceVision (Meshroom's engine) | 3.3.0 release binaries, MPL-2.0 | Sim(3) afterwards | `av_sfm.sh`, `av_intrinsics.py` |
| openMVG | v2.1, MPL-2.0 | priors in bundle adjustment | `omvg_sfm.sh`, `omvg_tools.py` |

ODM's OpenSfM fork is AGPL and was not used.

Ueno, 200 photos from one phone around the station's pedestrian deck and the pavements
below it:

| Tool | Registered (components) | Truths placed | Offset from photo_solve, median / max | Turn, median | Time | Peak memory |
|---|---|---|---|---|---|---|
| visloc-rs | 199 (1) | 12 | 19.8 m / 241.6 m | 45.6 deg | 23 min | 6.8 GB |
| COLMAP | 202 (154 + 48) | 12 | 4.9 m / 14.6 m | 7.6 deg | 34 min | 3.6 GB |
| OpenSfM | 199 (151 + 48) | 12 | 4.6 m / 13.6 m | 4.7 deg | 12 min | not measured |
| AliceVision | 89 (1) | 9 | 5.6 m / 12.6 m | 10.8 deg | 88 min | 4.9 GB |
| openMVG | 150 (1) | 10 | 9.0 m / 14.2 m | 5.0 deg | 6 min | not measured |

The other set had 130 photos: a home balcony, the street outside and the walk to a station
between tall buildings. No photo_solve truth was available for it, so only registration
was compared:

- visloc-rs: 43
- COLMAP: 112 in one model
- OpenSfM: 54 + 43 + 13 + 2
- AliceVision: 43
- openMVG: 33

- COLMAP and OpenSfM split Ueno at the same place, into about 150 and 48 photos. Two tools
  agreeing suggests the break is in the photos, not in either tool.
- Photos 018 and 025 sit 12 to 14 m from photo_solve in every model except visloc-rs, all
  in the same direction. That points at photo_solve's answer for those two, not at the
  tools.
- GPS inside bundle adjustment hurts when the GPS error is as large as the walk:
  - visloc-rs pulls the whole model toward the noisy fixes and turns it.
  - openMVG keeps the shape but scatters the cameras.
- A Sim(3) fitted after a purely visual model (COLMAP, AliceVision) keeps the model's
  shape. OpenSfM's priors are weak enough to do the same.
- AliceVision got the heading right (1 to 3 deg) but was tilted 8 to 12 deg. The up
  direction is taken as the cameras' mean up, and 89 cameras leave that estimate biased.
- AliceVision spent 97% of its time in CPU feature matching.
- openMVG's INCREMENTALV2 never grew past its two-view seed on 130 or 200 photos, with
  either the STELLAR or the MAX_PAIR initialiser. The classic INCREMENTAL engine works.

How to run them:

- AliceVision: `av_sfm.sh` with `AV_ROOT` pointing at the release.
- openMVG: `omvg_sfm.sh` with `OMVG_IMAGE` pointing at a docker image built from the
  repository's Dockerfile.
- Both scripts write `geo/0/`, which `sfm_compare.py` reads.

Tests: `python -m unittest discover -s tests`.
