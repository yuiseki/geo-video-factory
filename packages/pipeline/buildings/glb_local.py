"""Placing a GLB tile in the local frame before Blender reads it, in float64 (see localised_glb)."""
from __future__ import annotations

from typing import Sequence


def localised_glb(payload: bytes, matrix: Sequence[Sequence[float]]) -> bytes:
    """Return the GLB with `matrix` (Blender z-up world matrix, as plateau_tile_matrix gives it) folded into the
    transforms of its scene's root nodes, in float64, so that it imports at the identity.

    Tiles that keep their place in node transforms (RTC [0, 0, 0], Taito ward) carry an ECEF translation of about
    6.4e6 m. Blender keeps object matrices in float32, where that rounds by up to 0.5 m: composed there, the tile
    stood 0.2-0.5 m off the photo atlas built from the same mesh in float64 and poked through it. Composed here, the
    node holds local metres, which float32 keeps to well under a millimetre."""
    import json
    import struct

    import numpy as np

    magic, version, _total = struct.unpack_from("<4sII", payload)
    if magic != b"glTF" or version != 2:
        raise ValueError("payload is not a GLB v2")
    length, kind = struct.unpack_from("<I4s", payload, 12)
    if kind != b"JSON":
        raise ValueError("first GLB chunk must be JSON")
    document = json.loads(payload[20:20 + length].rstrip(b" \t\r\n\0"))
    yup = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)   # glTF y-up -> Blender z-up
    world = np.linalg.inv(yup) @ np.array(matrix, float) @ yup                          # the same move, in glTF axes
    scenes = document.get("scenes") or [{"nodes": list(range(len(document.get("nodes", []))))}]
    roots = sorted({i for scene in scenes for i in scene.get("nodes", [])})
    for i in roots:
        node = document["nodes"][i]
        local = _node_matrix(node)
        for key in ("translation", "rotation", "scale"):
            node.pop(key, None)
        node["matrix"] = (world @ local).T.reshape(-1).tolist()        # glTF matrices are column-major
    raw = json.dumps(document, separators=(",", ":")).encode()
    raw += b" " * ((-len(raw)) % 4)
    rest = payload[20 + length:]
    return struct.pack("<4sII", b"glTF", 2, 20 + len(raw) + len(rest)) + struct.pack("<I4s", len(raw), b"JSON") + raw + rest


def _node_matrix(node):
    """4x4 float64 local transform of a glTF node (matrix, or translation/rotation/scale)."""
    import numpy as np

    if "matrix" in node:
        return np.array(node["matrix"], float).reshape(4, 4).T
    x, y, z, w = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * np.array(node.get("scale", [1.0, 1.0, 1.0]), float)
    m[:3, 3] = node.get("translation", [0.0, 0.0, 0.0])
    return m
