"""python -m buildings.plateau_building <lon> <lat> <gml_id>...
One PLATEAU building's own triangles, by gml_id, from the PLATEAU++ tile store (pp_tiles.store()), in the
east-north-up frame at lon, lat (plateau_mesh.enu_frame). Run as a module it lists each building's roof levels from
the top, with the corners at each: the corners to pick in a photo when placing it (world_model/corner_pose.py).

A building is taken by the feature id every vertex carries (_BATCHID), not by the triangles that fall inside its
footprint: a neighbour's wall or a lower wing standing within the outline is not this building."""
import json
import sys
from pathlib import Path

import numpy as np

from buildings import glb_spatial as gs
from buildings.plateau_3d import glb_chunks
from buildings.plateau_mesh import _primitive, enu_frame


def _features(doc, binary, prim):
    """Feature index of every vertex of a primitive, in the order _primitive gives the positions."""
    name = gs._feature_attribute(prim.get("attributes", {}))
    if name is None:
        return None
    if (prim.get("extensions") or {}).get("KHR_draco_mesh_compression"):
        _, feats = gs._decode_draco_primitive(doc, binary, prim, name)
    else:
        feats = gs._accessor_values(doc, binary, prim["attributes"][name])
    return np.array([int(round(f[0])) for f in feats]) if feats else None


def feature_triangles(payload, rtc, tile_ids, wanted):
    """{gml_id: ECEF triangles (n, 3, 3)} of the wanted features of one tile (y-up around rtc)."""
    doc, binary, _ = glb_chunks(payload)
    mats = gs._mesh_world_matrices(doc)
    index = {i: str(g) for i, g in enumerate(tile_ids) if str(g) in wanted}
    out = {}
    for mesh_index, mesh in enumerate(doc.get("meshes", [])):
        for prim in mesh.get("primitives", []):
            feats = _features(doc, binary, prim)
            if feats is None:
                continue
            pos, faces = _primitive(doc, binary, prim)
            face_feat = feats[faces]
            for mat in mats.get(mesh_index) or [gs._identity_mat4()]:
                a = np.array(mat)
                w = pos @ a[:3, :3].T + a[:3, 3]
                ecef = np.c_[rtc[0] + w[:, 0], rtc[1] - w[:, 2], rtc[2] + w[:, 1]]
                for i, gid in index.items():
                    mine = (face_feat == i).all(axis=1)
                    if mine.any():
                        out.setdefault(gid, []).append(ecef[faces[mine]])
    return {g: np.concatenate(t) for g, t in out.items()}


def building_triangles(gml_ids, origin, store=None):
    """{gml_id: triangles (n, 3, 3) in metres east, north and up (ellipsoid) from origin (lon, lat)}."""
    if store is None:
        from buildings.pp_tiles import store as pp_store
        store = pp_store()
    store = Path(store)
    want = set(gml_ids)
    ecef = {}
    for entry_path in sorted(store.glob("plateau/*/*.json")):
        entry = json.loads(entry_path.read_text())
        here = want & {str(i) for i in entry.get("ids", [])}
        if not here:
            continue
        found = feature_triangles((store / entry["glb"]).read_bytes(), [float(v) for v in entry["rtc"]],
                                  entry["ids"], here)
        for g, t in found.items():
            ecef.setdefault(g, []).append(t)
    missing = want - set(ecef)
    if missing:
        raise KeyError(f"no PLATEAU++ tile in {store} holds {sorted(missing)}")
    o, frame = enu_frame(*origin)
    return {g: ((np.concatenate(t).reshape(-1, 3) - o) @ frame.T).reshape(-1, 3, 3) for g, t in ecef.items()}


def roof_levels(tris, step=0.5):
    """[{z, corners [[x, y], ...]}] of the building's vertex heights, from the top: what to pick in a photo."""
    v = np.unique(np.asarray(tris, float).reshape(-1, 3).round(2), axis=0)
    zs = np.round(v[:, 2] / step) * step
    levels = []
    for z in sorted(set(zs.tolist()), reverse=True):
        corners = np.unique(v[zs == z][:, :2].round(1), axis=0)
        levels.append({"z": round(float(v[zs == z][:, 2].mean()), 2), "corners": corners.tolist()})
    return levels


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    lon, lat = float(argv[0]), float(argv[1])
    for gid, tris in building_triangles(argv[2:], (lon, lat)).items():
        print(gid, len(tris), "triangles")
        for lv in roof_levels(tris):
            many = len(lv["corners"]) > 20      # a patterned roof or wall: too many to pick from
            print(f"  z {lv['z']:7.2f}:", f"{len(lv['corners'])} corners" if many else lv["corners"])


if __name__ == "__main__":
    main(sys.argv[1:])
