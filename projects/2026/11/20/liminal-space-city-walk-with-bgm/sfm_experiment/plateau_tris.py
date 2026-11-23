"""plateau_tris.py <pipeline_dir> <buildings_dir> <out.npz> [lon lat]
Read every PLATEAU GLB tile in a geo-video-factory manifest and save all triangles in a local ENU frame
(metres, x east, y north, z up from the ellipsoid) around lon/lat (default: the scramble crossing)."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, sys.argv[1])
import glb_spatial as gs  # noqa: E402
from plateau_3d import glb_chunks  # noqa: E402

bdir, out = Path(sys.argv[2]), sys.argv[3]
lon0, lat0 = (float(sys.argv[4]), float(sys.argv[5])) if len(sys.argv) > 5 else (139.70055, 35.65950)
o = np.array(gs._ecef(lon0, lat0, 0))
lo, la = np.radians(lon0), np.radians(lat0)
E = np.array([-np.sin(lo), np.cos(lo), 0])
N = np.array([-np.sin(la) * np.cos(lo), -np.sin(la) * np.sin(lo), np.cos(la)])
U = np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
M = np.stack([E, N, U])

man = json.loads((bdir / "manifest.json").read_text())
tris = []
for t in man["tiles"]:
    doc, binary, _ = glb_chunks((bdir / t["glb"]).read_bytes())
    mats = gs._mesh_world_matrices(doc)
    rtc = np.array(t["rtc"])
    for mi, mesh in enumerate(doc.get("meshes", [])):
        for prim in mesh.get("primitives", []):
            ext = (prim.get("extensions") or {}).get("KHR_draco_mesh_compression")
            if ext:
                import DracoPy
                v = doc["bufferViews"][ext["bufferView"]]
                s = v.get("byteOffset", 0)
                m = DracoPy.decode(binary[s:s + v["byteLength"]])
                pos = np.asarray(m.points, np.float64).reshape(-1, 3)
                faces = np.asarray(m.faces, np.int64).reshape(-1, 3)
            else:
                pos = np.array(gs._accessor_values(doc, binary, prim["attributes"]["POSITION"]), np.float64)
                if "indices" in prim:
                    faces = np.array(gs._accessor_values(doc, binary, prim["indices"]), np.int64).reshape(-1, 3)
                else:
                    faces = np.arange(len(pos)).reshape(-1, 3)
            for mat in mats.get(mi) or [gs._identity_mat4()]:
                A = np.array(mat)
                w = pos @ A[:3, :3].T + A[:3, 3]
                ecef = np.c_[rtc[0] + w[:, 0], rtc[1] - w[:, 2], rtc[2] + w[:, 1]]
                enu = (ecef - o) @ M.T
                tris.append(enu[faces])
tris = np.concatenate(tris).astype(np.float32)
np.savez_compressed(out, tris=tris, origin=np.array([lon0, lat0]))
print("triangles", len(tris), "x", tris[..., 0].min(), tris[..., 0].max(), "y", tris[..., 1].min(), tris[..., 1].max(),
      "z", tris[..., 2].min(), tris[..., 2].max())
