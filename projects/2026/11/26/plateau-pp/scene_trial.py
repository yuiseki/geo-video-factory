"""Write out/<name>/scene.json: what compare_blender.py and compare_three.mjs both place and look at.

    python projects/2026/11/26/plateau-pp/scene_trial.py <name>

For every tile of out/<name>/manifest.json (city-shadow left out): the 4x4 matrix from the GLB as Blender imports
it (Z-up) to local east/north/up metres around the manifest centre, heights on the ellipsoid; then the ground
height and a camera over the area. Computed once here so the two renderers differ only in drawing.
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[4] / "packages" / "pipeline"))
from buildings import blender_geo as bg  # noqa: E402
from buildings.glb_spatial import _identity_mat4, _mesh_world_matrices  # noqa: E402
from buildings.glb_strip import _decode  # noqa: E402
from buildings.plateau_3d import glb_chunks  # noqa: E402

GEOID_M = 36.7      # ellipsoid minus orthometric height around western Tokyo: puts the filled-in tiles (orthometric) on PLATEAU's ground


def heights(payload: bytes, matrix) -> np.ndarray:
    doc, binary, _ = glb_chunks(payload)
    world = _mesh_world_matrices(doc)
    m = np.asarray(matrix, float)
    zs = []
    for mi, mesh in enumerate(doc.get("meshes", [])):
        n = np.asarray((world.get(mi) or [_identity_mat4()])[0], float)
        for prim in mesh["primitives"]:
            p = _decode(doc, binary, prim)[0]["POSITION"].astype(float) @ n[:3, :3].T + n[:3, 3]
            zs.append((np.stack([p[:, 0], -p[:, 2], p[:, 1]], axis=1) @ m[:3, :3].T + m[:3, 3])[:, 2])
    return np.concatenate(zs) if zs else np.zeros(0)


def main() -> None:
    area = HERE / "out" / sys.argv[1]
    manifest = json.loads((area / "manifest.json").read_text(encoding="utf-8"))
    centre = manifest["center"]
    tiles, ground = [], []
    for tile in manifest["tiles"]:
        if tile.get("kind") == "city-shadow":
            continue
        if tile.get("frame") == "enu":
            matrix = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, GEOID_M], [0, 0, 0, 1]]
            z = heights((area / tile["glb"]).read_bytes(), matrix)
            if not any(t["kind"] == "plateau" for t in tiles) and len(z):
                ground.append(float(np.percentile(z, 2)))
        else:
            matrix = bg.plateau_tile_matrix(tile["rtc"], centre, 0.0)
            ground.append(float(np.percentile(heights((area / tile["glb"]).read_bytes(), matrix), 2)))
        tiles.append({"glb": tile["glb"], "kind": tile.get("kind", "plateau"), "matrix": [list(map(float, r)) for r in matrix]})
    g = float(np.median(ground)) if ground else GEOID_M
    w, s, e, n = manifest["bbox_degrees"]
    half = max(bg.local_meters((e, n), centre))
    scene = {"centre": centre, "ground": g, "tiles": tiles,
             "camera": {"eye": [half * 0.9, -half * 1.3, g + half * 1.0], "target": [0.0, 0.0, g], "fov": 45.0,
                        "width": 1280, "height": 720}}
    (area / "scene.json").write_text(json.dumps(scene, indent=1) + "\n", encoding="utf-8")
    print(f"ground {g:.1f} m, {len(tiles)} tiles -> {area / 'scene.json'}")


if __name__ == "__main__":
    main()
