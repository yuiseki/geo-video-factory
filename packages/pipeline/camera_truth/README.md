# camera_truth

Photos placed by hand once, kept so they are never placed by hand again.

Each `*.json` holds the photos of one place. For every photo it keeps:

- the photo (`file`, its `sha256` and size, `ref`, licence, creator and Commons page);
- the PLATEAU buildings it was placed against (`buildings`, by `gml_id`), and others in view that were not picked
  but are drawn to check the camera against (`seen`);
- the picks: roof corners (`points`, a 3D corner to its pixel) and edges (`lines`, two 3D points of an edge to one
  pixel on it), in the file's local frame (`origin`, `frame`) and in full-resolution pixels;
- the focal length and where it came from (`fx`, `fx_from`; `null` when it was solved for), and `eye_z` when the
  photographer's eye height was given instead;
- the camera the picks give (`camera`: `eye`, `Rw` world to camera, `params` fx fy cx cy) and the largest pixel
  miss (`residual_px_max`).

`python -m world_model.corner_pose <file.json>` solves every photo again from its picks;
`python -m world_model.truth_view draw <file.json> <out_dir>` draws the buildings over every photo through its kept
camera; `python -m buildings.plateau_building <lon> <lat> <gml_id>` lists a building's roof corners to pick and
`python -m world_model.truth_view grid <photo> <out.jpg> [--crop=u,v,r]` lays a pixel grid over a photo to pick them on;
`tests/test_corner_pose.py` checks that each kept camera is still what its picks give and that each kept photo is
the one its pixels were picked in. Only CC0 and public-domain photos are kept here.

## Adding a photo

1. Find the buildings in PLATEAU: the shop's place from OpenStreetMap, then the PLATEAU footprint there, and list
   their roof corners with `python -m buildings.plateau_building <lon> <lat> <gml_id>...`.
2. Pick the corners and edges in the photo on `truth_view grid` (a downscaled copy, then `--crop` at full
   resolution) and write them as a photo entry: `ref`, `file`, `sha256`, size, licence, `buildings`, `points`,
   `lines`, `fx` (or `null` with `eye_z`) and a `guess_eye` near where it was taken.
3. `python -m world_model.corner_pose keep <file.json> <photo.json>` solves it and writes it in, then
   `python -m world_model.truth_view draw <file.json> <out_dir>` draws it. Look before keeping it: a camera inside a
   building or floating above the street is a wrong fit even with small misses. Few corners cannot tell a long lens
   far away from a short one close by; take the focal length from EXIF, or give `eye_z`.
4. Put the photo under `photos/` and commit the file with it.

## Photos

| file | creator | licence |
|---|---|---|
| `photos/Sofmap_Tokyo_Akihabara_main_store.jpg` | Tokumeigakarinoaoshima, [Commons](https://commons.wikimedia.org/wiki/File:Sofmap_Tokyo_Akihabara_main_store.JPG) | CC0 |
| `photos/AKIBA_Sofmap_1gouten_1.jpg` | Saoyagi2, [Commons](https://commons.wikimedia.org/wiki/File:AKIBA_Sofmap_1gouten_1.jpg) | CC0 |

Building shapes: PLATEAU (MLIT), 3D city model of Chiyoda ward 2025.
