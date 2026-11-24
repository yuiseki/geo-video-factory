"""plateau_mesh.py <buildings_dir> <out.npz> <lon> <lat>
Every triangle of the PLATEAU tiles that plateau_3d.py prepared (<buildings_dir>/manifest.json and its GLB files),
in one local frame: metres east, north and up from the ellipsoid at <lon> <lat>. This is the mesh that the
skyline search (skyline_match.py, photo_place.py) and the photo projection read; the renderer's own tiles stay
as they are. Writes tris (n, 3, 3) float32 and origin (lon, lat). Draco-compressed tiles need DracoPy."""
import sys as _sys
from pathlib import Path as _Path
if str(_Path(__file__).resolve().parents[1]) not in _sys.path:
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
import json
import sys
from pathlib import Path

import numpy as np

from buildings import glb_spatial as gs
from buildings.plateau_3d import glb_chunks


def enu_frame(lon, lat):
    """(origin in ECEF, 3x3 matrix whose rows are east, north and up) at a point on the ellipsoid."""
    lo, la = np.radians(lon), np.radians(lat)
    east = np.array([-np.sin(lo), np.cos(lo), 0])
    north = np.array([-np.sin(la) * np.cos(lo), -np.sin(la) * np.sin(lo), np.cos(la)])
    up = np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
    return np.array(gs._ecef(lon, lat, 0)), np.stack([east, north, up])


def _primitive(doc, binary, prim):
    """(positions (n, 3), faces (m, 3)) of one glTF primitive in its mesh's own frame."""
    ext = (prim.get("extensions") or {}).get("KHR_draco_mesh_compression")
    if ext:
        import DracoPy
        view = doc["bufferViews"][ext["bufferView"]]
        start = view.get("byteOffset", 0)
        mesh = DracoPy.decode(binary[start:start + view["byteLength"]])
        return (np.asarray(mesh.points, np.float64).reshape(-1, 3), np.asarray(mesh.faces, np.int64).reshape(-1, 3))
    pos = np.array(gs._accessor_values(doc, binary, prim["attributes"]["POSITION"]), np.float64)
    if "indices" in prim:
        return pos, np.array(gs._accessor_values(doc, binary, prim["indices"]), np.int64).reshape(-1, 3)
    return pos, np.arange(len(pos)).reshape(-1, 3)


def glb_parts(payload, rtc):
    """Yields (vertices in ECEF (n, 3), faces (m, 3)) for every placement of every primitive of a tile. The tile
    is y-up around rtc (the centre that plateau_3d.py took out of the file and recorded in the manifest)."""
    doc, binary, _ = glb_chunks(payload)
    mats = gs._mesh_world_matrices(doc)
    rtc = np.asarray(rtc, float)
    for index, mesh in enumerate(doc.get("meshes", [])):
        for prim in mesh.get("primitives", []):
            pos, faces = _primitive(doc, binary, prim)
            for mat in mats.get(index) or [gs._identity_mat4()]:
                a = np.array(mat)
                w = pos @ a[:3, :3].T + a[:3, 3]
                yield np.c_[rtc[0] + w[:, 0], rtc[1] - w[:, 2], rtc[2] + w[:, 1]], faces


def glb_triangles(payload, rtc):
    """Every triangle of one tile in ECEF, (n, 3, 3)."""
    parts = [ecef[faces] for ecef, faces in glb_parts(payload, rtc)]
    return np.concatenate(parts) if parts else np.zeros((0, 3, 3))


def manifest_triangles(buildings_dir, lon, lat):
    """Every triangle of every tile of a manifest, in the east-north-up frame at lon, lat: (n, 3, 3) float32."""
    folder = Path(buildings_dir)
    origin, frame = enu_frame(lon, lat)
    tris = []
    for tile in json.loads((folder / "manifest.json").read_text())["tiles"]:
        for ecef, faces in glb_parts((folder / tile["glb"]).read_bytes(), tile["rtc"]):
            tris.append(((ecef - origin) @ frame.T)[faces])
    if not tris or not sum(len(t) for t in tris):
        raise ValueError(f"no triangles in the tiles of {folder / 'manifest.json'}")
    return np.concatenate(tris).astype(np.float32)


def main(argv):
    if len(argv) != 4:
        raise SystemExit(__doc__)
    lon, lat = float(argv[2]), float(argv[3])
    tris = manifest_triangles(argv[0], lon, lat)
    np.savez_compressed(argv[1], tris=tris, origin=np.array([lon, lat]))
    print("triangles", len(tris), "x", tris[..., 0].min(), tris[..., 0].max(), "y", tris[..., 1].min(),
          tris[..., 1].max(), "z", tris[..., 2].min(), tris[..., 2].max())


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
