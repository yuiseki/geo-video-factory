"""Bake a trial PLATEAU++ (out/<name>-v1) into out/<name>-v1-baked, and write the scene both renderers share.

    python projects/2026/11/26/plateau-pp/bake_trial.py <name>-v1 [--suffix=baked]

PLATEAU tiles go through buildings.pp_bake (roof photo and wall colour into the GLB); the filled-in tiles are
copied as they are. scene.json holds, for every tile, the 4x4 matrix from the GLB as Blender imports it (Z-up)
to local east/north/up metres around the manifest centre (heights on the ellipsoid), the ground height and a
camera, so compare_blender.py and compare_three.html place and look at exactly the same thing.
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[4] / "packages" / "pipeline"))
from buildings import blender_geo as bg  # noqa: E402
from buildings.glb_spatial import _identity_mat4, _mesh_world_matrices  # noqa: E402
from buildings.glb_strip import _decode  # noqa: E402
from buildings.plateau_3d import glb_chunks  # noqa: E402
from buildings.pp_bake import bake_untextured  # noqa: E402

GEOID_M = 36.7      # ellipsoid minus orthometric height around western Tokyo: puts the filled-in tiles (orthometric) on PLATEAU's ground


def heights(payload: bytes, matrix: list[list[float]]) -> np.ndarray:
    doc, binary, _ = glb_chunks(payload)
    world = _mesh_world_matrices(doc)
    m = np.asarray(matrix, float)
    zs = []
    for mi, mesh in enumerate(doc.get("meshes", [])):
        n = np.asarray((world.get(mi) or [_identity_mat4()])[0], float)
        for prim in mesh["primitives"]:
            pos = _decode(doc, binary, prim)[0]["POSITION"].astype(float)
            p = pos @ n[:3, :3].T + n[:3, 3]
            zup = np.stack([p[:, 0], -p[:, 2], p[:, 1]], axis=1)
            zs.append((zup @ m[:3, :3].T + m[:3, 3])[:, 2])
    return np.concatenate(zs) if zs else np.zeros(0)


def main() -> None:
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--"))
    name = [a for a in sys.argv[1:] if not a.startswith("--")][0]
    src = HERE / "out" / name
    dst = HERE / "out" / f"{name}-{opts.get('suffix', 'baked')}"
    if dst.exists():
        raise SystemExit(f"{dst} exists: pass a new --suffix")
    manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    centre = manifest["center"]
    roof = manifest["roof_texture"]
    photo = Image.open(src / roof["image"]).convert("RGB")
    (dst / "models").mkdir(parents=True)
    tiles, ground = [], []
    for tile in manifest["tiles"]:
        raw = (src / tile["glb"]).read_bytes()
        if tile.get("frame") == "enu":
            if tile.get("kind") == "city-shadow":
                continue
            matrix = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, GEOID_M], [0, 0, 0, 1]]
            out = raw
        else:
            matrix = bg.plateau_tile_matrix(tile["rtc"], centre, 0.0)
            out = bake_untextured(raw, tile["rtc"], [str(i) for i in tile["ids"]], tile.get("facade_colors") or [],
                                  photo, roof["bounds"])
            ground.append(np.percentile(heights(out, matrix), 2))
        (dst / tile["glb"]).write_bytes(out)
        tiles.append({"glb": tile["glb"], "kind": tile.get("kind", "plateau"), "matrix": [list(map(float, r)) for r in matrix]})
        print(f"{tile['glb']}: {len(raw) / 1e6:.1f} -> {len(out) / 1e6:.1f} MB", flush=True)
    g = float(np.median(ground)) if ground else GEOID_M
    w, s, e, n = manifest["bbox_degrees"]
    half = max(bg.local_meters((e, n), centre)[0], bg.local_meters((e, n), centre)[1])
    scene = {"centre": centre, "ground": g, "tiles": tiles,
             "camera": {"eye": [half * 0.9, -half * 1.3, g + half * 1.0], "target": [0.0, 0.0, g], "fov": 45.0,
                        "width": 1280, "height": 720}}
    (dst / "scene.json").write_text(json.dumps(scene, indent=1) + "\n", encoding="utf-8")
    shutil.copy2(src / "manifest.json", dst / "manifest.source.json")
    print(f"ground {g:.1f} m, {len(tiles)} tiles -> {dst}")


if __name__ == "__main__":
    main()
