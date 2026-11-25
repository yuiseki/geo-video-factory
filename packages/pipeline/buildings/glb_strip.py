"""Remove whole buildings (batch features) from a PLATEAU GLB tile.

drop_features(payload, ids) rewrites every primitive that holds a triangle of one of the features: it is
decoded (Draco or plain accessors), the triangles of those features and the vertices only they use are left
out, and the rest is written back as plain accessors with the same attributes and material. Primitives
without such triangles, images and every other buffer view are copied byte for byte. A payload with nothing
to drop is returned as it is.
"""
from __future__ import annotations

import json
import struct
from typing import Any

import numpy as np

from buildings.glb_spatial import _accessor_values, _feature_attribute
from buildings.plateau_3d import glb_chunks

try:
    import DracoPy
except ImportError:  # pragma: no cover - requirements-dev.txt installs it
    DracoPy = None

DRACO = "KHR_draco_mesh_compression"
TYPES = {1: "SCALAR", 2: "VEC2", 3: "VEC3", 4: "VEC4"}


def _decode(document: dict[str, Any], binary: bytes, prim: dict[str, Any]) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """{attribute: (n, k) float32} and (m, 3) triangle indices of one primitive."""
    ext = (prim.get("extensions") or {}).get(DRACO)
    if ext:
        if DracoPy is None:
            raise RuntimeError("Draco-compressed GLB needs DracoPy (see packages/pipeline/requirements-dev.txt)")
        view = document["bufferViews"][ext["bufferView"]]
        start = int(view.get("byteOffset", 0))
        mesh = DracoPy.decode(binary[start:start + int(view["byteLength"])])
        attrs = {}
        for name, uid in ext["attributes"].items():
            a = mesh.get_attribute_by_unique_id(int(uid))
            data = np.asarray(a["data"], np.float32)
            attrs[name] = data.reshape(len(data), -1)
        return attrs, np.asarray(mesh.faces, np.int64).reshape(-1, 3)
    attrs = {name: np.asarray(_accessor_values(document, binary, idx), np.float32)
             for name, idx in prim["attributes"].items()}
    n = len(next(iter(attrs.values())))
    if "indices" in prim:
        faces = np.asarray(_accessor_values(document, binary, prim["indices"]), np.int64).reshape(-1, 3)
    else:
        faces = np.arange(n - n % 3, dtype=np.int64).reshape(-1, 3)
    return attrs, faces


def drop_features(payload: bytes, drop_ids: set[int]) -> bytes:
    document, binary, _ = glb_chunks(payload)
    drop = np.array(sorted(drop_ids), np.int64)
    rewrites = {}
    for mi, mesh in enumerate(document.get("meshes", [])):
        for pi, prim in enumerate(mesh.get("primitives", [])):
            feature = _feature_attribute(prim.get("attributes", {}))
            if feature is None:
                continue
            attrs, faces = _decode(document, binary, prim)
            ids = np.rint(attrs[feature][:, 0]).astype(np.int64)
            gone = np.isin(ids[faces[:, 0]], drop)
            if gone.any():
                rewrites[(mi, pi)] = (attrs, faces[~gone])
    if not rewrites:
        return payload

    out = bytearray()
    views = []

    def add_view(raw: bytes, target: int | None = None) -> int:
        out.extend(b"\0" * (-len(out) % 4))
        view = {"buffer": 0, "byteOffset": len(out), "byteLength": len(raw)}
        if target:
            view["target"] = target
        out.extend(raw)
        views.append(view)
        return len(views) - 1

    for v in document.get("bufferViews", []):          # everything else keeps its bytes and its index
        start = int(v.get("byteOffset", 0))
        new = add_view(binary[start:start + int(v["byteLength"])])
        views[new].update({k: v[k] for k in ("byteStride", "target") if k in v})
    accessors = document.setdefault("accessors", [])
    for (mi, pi), (attrs, faces) in rewrites.items():
        prim = document["meshes"][mi]["primitives"][pi]
        used = np.unique(faces.reshape(-1))
        remap = np.full(len(next(iter(attrs.values()))), -1, np.int64)
        remap[used] = np.arange(len(used))
        new_attrs = {}
        for name, data in attrs.items():
            kept = np.ascontiguousarray(data[used], np.float32)
            acc = {"bufferView": add_view(kept.tobytes(), 34962), "componentType": 5126, "count": len(kept),
                   "type": TYPES[kept.shape[1]]}
            if name == "POSITION" and len(kept):
                acc.update(min=kept.min(axis=0).tolist(), max=kept.max(axis=0).tolist())
            accessors.append(acc)
            new_attrs[name] = len(accessors) - 1
        index = remap[faces.reshape(-1)].astype(np.uint32)
        accessors.append({"bufferView": add_view(index.tobytes(), 34963), "componentType": 5125,
                          "count": len(index), "type": "SCALAR"})
        prim["attributes"] = new_attrs
        prim["indices"] = len(accessors) - 1
        (prim.get("extensions") or {}).pop(DRACO, None)
        if "extensions" in prim and not prim["extensions"]:
            del prim["extensions"]
    if not any(DRACO in (p.get("extensions") or {}) for m in document.get("meshes", []) for p in m["primitives"]):
        for key in ("extensionsUsed", "extensionsRequired"):
            if key in document:
                document[key] = [x for x in document[key] if x != DRACO]
                if not document[key]:
                    del document[key]
    document["bufferViews"] = views
    out.extend(b"\0" * (-len(out) % 4))
    document["buffers"] = [{"byteLength": len(out)}]
    j = json.dumps(document, separators=(",", ":")).encode()
    j += b" " * (-len(j) % 4)
    total = 12 + 8 + len(j) + 8 + len(out)
    return (struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(j), b"JSON") + j
            + struct.pack("<I4s", len(out), b"BIN\0") + bytes(out))
