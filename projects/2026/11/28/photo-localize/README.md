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

Tests: `python -m unittest discover -s tests`.
