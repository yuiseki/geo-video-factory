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

## The silhouette camera (deterministic)

Picking pixels by hand is the one step a person does differently each time. `silhouette` gives each photo a second
camera that no one picks: SAM cuts the target building out of the photo, and `world_model.silhouette_pose` pulls the
building's PLATEAU outline onto SAM's outline (upper half only: people, cars and trees hide the foot), from five
fixed starts around the hand camera, keeping the one that misses least.

1. `python -m world_model.silhouette_pose prompt <file.json>` writes SAM's prompt (the target's middle and box as
   the hand camera draws it).
2. `python -m world_model.sam_mask <file.json>`, from an environment with torch and transformers, writes SAM's three
   masks under `masks/` (the same photo and prompt give byte-identical masks).
3. `python -m world_model.silhouette_pose keep <file.json>` writes the camera found, its median miss in pixels and
   each start's miss (`inf`: the start lost the building, a failure that shows).

`tests/test_silhouette_pose.py` checks the kept silhouette cameras are what the masks give (when the PLATEAU++ tile
store is there). The focal length stays the photo's: freed, one building's outline gives a different lens and place
from each start with the same miss.

For `AKIBA_Sofmap_1gouten_1.jpg` (eye height given, 1.6 m above the street) the camera found is 2.0 m and 0.6
degrees from the hand camera, the eye 3.5 m above the building's foot; the eye height first held only as one term
against thousands of outline points and sank or rose by metres until it was weighed by their number. For the
main-store photo (no eye height given) four starts of five reach the same camera, 4.3 m and 3.7 degrees from the
hand camera, with the eye 4.8 m above the foot instead of 7.6; both draw the building equally well.

## Solved from the photo alone (`photo_solve/`)

`photo_solve/solved.json` keeps photos that `python -m geo.photo_solve <photo> <work_dir> --vision-python=...` placed
from nothing but the file (pixels and EXIF), with no person picking or looking: the EXIF read, the sky read, the
skyline search's place, the building chosen, SAM's masks (`photo_solve/masks/`) and the camera, with every gate it
passed. These are the photographer's own photos, added with leave; they are not CC0. `tests/test_photo_solve.py`
checks each camera is what its coarse camera and masks give, and `tests/test_photo_place_frozen.py` that the
skyline search still finds each place (in under 5 minutes).

## Photos

| file | creator | licence |
|---|---|---|
| `photos/Sofmap_Tokyo_Akihabara_main_store.jpg` | Tokumeigakarinoaoshima, [Commons](https://commons.wikimedia.org/wiki/File:Sofmap_Tokyo_Akihabara_main_store.JPG) | CC0 |
| `photos/AKIBA_Sofmap_1gouten_1.jpg` | Saoyagi2, [Commons](https://commons.wikimedia.org/wiki/File:AKIBA_Sofmap_1gouten_1.jpg) | CC0 |
| `photos/ueno_okachimachi_20261127_1019.jpg` | the photographer's own (Gyazo), added with leave | not CC0 |
| `photos/shibuya_20230321_1432.jpg` | the photographer's own (Gyazo), added with leave | not CC0 |

Building shapes: PLATEAU (MLIT), 3D city model of Chiyoda ward 2025.
