"""A filled-in tile from local east/up/south metres around its own centre to ECEF offsets from an RTC centre.

city_proxy writes the filled-in buildings and their ground shadow in a local frame: x east, y up (orthometric, the
GSI DEM), z south, in metres around a centre. PLATEAU's tiles are ECEF offsets from an RTC centre in glTF's Y-up
order (ecef = rtc + (x, -z, y)). Turned into the same form, a filled-in tile is placed by every consumer as a
PLATEAU tile is, needs no box centre, and can be kept once per tile for every box (buildings.pp_tiles). Heights go
from orthometric to the ellipsoid with the geoid height (plateau_mesh.GEOID_M around Tokyo), as PLATEAU's are.
"""
from __future__ import annotations

import json
import math
import struct

import numpy as np

from buildings.glb_spatial import _ecef
from buildings.plateau_3d import glb_chunks


def _frame(lon: float, lat: float) -> np.ndarray:
    lam, phi = math.radians(lon), math.radians(lat)
    east = [-math.sin(lam), math.cos(lam), 0.0]
    north = [-math.sin(phi) * math.cos(lam), -math.sin(phi) * math.sin(lam), math.cos(phi)]
    up = [math.cos(phi) * math.cos(lam), math.cos(phi) * math.sin(lam), math.sin(phi)]
    return np.array([east, north, up]).T            # columns: east, north, up in ECEF


def to_rtc(payload: bytes, lon0: float, lat0: float, geoid_m: float) -> tuple[bytes, list[float]]:
    """(the GLB with every POSITION and NORMAL rewritten as ECEF offsets in Y-up order, the RTC centre)."""
    document, binary, chunks = glb_chunks(payload)
    if any(n.get("matrix") or n.get("translation") or n.get("rotation") or n.get("scale")
           for n in document.get("nodes", [])):
        raise ValueError("a filled-in tile has no node transforms")
    data = bytearray(binary)
    r = _frame(lon0, lat0)
    rtc = list(_ecef(lon0, lat0, 0.0))
    done: set[int] = set()
    for mesh in document.get("meshes", []):
        for prim in mesh.get("primitives", []):
            for name, translate in (("POSITION", True), ("NORMAL", False)):
                index = prim.get("attributes", {}).get(name)
                if index is None or index in done:
                    continue
                done.add(index)
                acc = document["accessors"][index]
                view = document["bufferViews"][acc["bufferView"]]
                if acc["componentType"] != 5126 or acc["type"] != "VEC3" or view.get("byteStride", 12) != 12:
                    raise ValueError(f"{name} must be tightly packed float VEC3")
                start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
                end = start + 12 * acc["count"]
                v = np.frombuffer(bytes(data[start:end]), np.float32).reshape(-1, 3).astype(np.float64)
                enu = np.c_[v[:, 0], -v[:, 2], v[:, 1] + (geoid_m if translate else 0.0)]
                d = enu @ r.T
                out = np.c_[d[:, 0], d[:, 2], -d[:, 1]].astype(np.float32)
                data[start:end] = out.tobytes()
                if translate:
                    acc["min"], acc["max"] = out.min(0).tolist(), out.max(0).tolist()
    text = json.dumps(document, separators=(",", ":")).encode()
    text += b" " * (-len(text) % 4)
    parts = [(b"JSON", text), (b"BIN\0", bytes(data))] + [(k, d) for k, d in chunks if k not in (b"JSON", b"BIN\0")]
    body = b"".join(struct.pack("<I4s", len(d), k) + d for k, d in parts)
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body, rtc
