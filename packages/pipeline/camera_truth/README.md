# camera_truth

Photos placed by hand once, kept so they are never placed by hand again.

Each `*.json` holds the photos of one place. For every photo it keeps:

- the photo (`file`, its `sha256` and size, `ref`, licence, creator and Commons page);
- the PLATEAU buildings it was placed against (`buildings`, by `gml_id`);
- the picks: roof corners (`points`, a 3D corner to its pixel) and edges (`lines`, two 3D points of an edge to one
  pixel on it), in the file's local frame (`origin`, `frame`) and in full-resolution pixels;
- the focal length and where it came from (`fx`, `fx_from`; `null` when it was solved for), and `eye_z` when the
  photographer's eye height was given instead;
- the camera the picks give (`camera`: `eye`, `Rw` world to camera, `params` fx fy cx cy) and the largest pixel
  miss (`residual_px_max`).

`python -m world_model.corner_pose <file.json>` solves every photo again from its picks;
`tests/test_corner_pose.py` checks that each kept camera is still what its picks give and that each kept photo is
the one its pixels were picked in. Only CC0 and public-domain photos are kept here.

## Adding a photo

1. Find the buildings in PLATEAU (the shop's place from OpenStreetMap, then the PLATEAU footprint around it) and
   read their roof corners in the local frame.
2. Pick the corners and edges in the photo (a grid over a downscaled copy, then a crop at full resolution).
3. Solve with `world_model.corner_pose.solve`, draw the buildings over the photo and look: a camera inside a
   building or floating above the street is a wrong fit even with small misses. Few corners cannot tell a long lens
   far away from a short one close by; take the focal length from EXIF, or give `eye_z`.
4. Keep the picks and the camera here, with the photo.

## Photos

| file | creator | licence |
|---|---|---|
| `photos/Sofmap_Tokyo_Akihabara_main_store.jpg` | Tokumeigakarinoaoshima, [Commons](https://commons.wikimedia.org/wiki/File:Sofmap_Tokyo_Akihabara_main_store.JPG) | CC0 |
| `photos/AKIBA_Sofmap_1gouten_1.jpg` | Saoyagi2, [Commons](https://commons.wikimedia.org/wiki/File:AKIBA_Sofmap_1gouten_1.jpg) | CC0 |

Building shapes: PLATEAU (MLIT), 3D city model of Chiyoda ward 2025.
