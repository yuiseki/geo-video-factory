"""The look of untextured PLATEAU buildings, written into the GLB so every renderer shows the same thing.

bake_untextured(payload, rtc, ids, facade_colors, roof_photo, roof_bounds) rewrites each primitive whose material
has no photo texture of its own into two, in plain glTF that any loader draws without a custom shader:

- pp-roof: the faces within ~37 degrees of the local vertical (|cos| > ROOF_COS, either winding), with the GSI
  photo cut to the tile's roofs and embedded, and TEXCOORD_0 projecting it straight down (lon/lat -> image).
- pp-wall: every other face, white, with COLOR_0 per vertex from facade_colors[building] (city_proxy.wall_hex:
  sRGB hex, alpha byte = facade style), turned linear as glTF requires.

Primitives with their own texture are copied byte for byte, and so is every image and buffer view. A tile that
has nothing untextured left (already baked, or all photo-textured) comes back as it is.

Positions follow the PLATEAU tiles: node matrices, then glTF Y-up offsets from the RTC centre in ECEF,
ECEF = rtc + (x, -z, y) (glb_spatial._feature_ecef_points).
"""
from __future__ import annotations

import io
import json
import math
import struct
from typing import Any

import numpy as np
from PIL import Image

from buildings.glb_spatial import _feature_attribute, _identity_mat4, _mesh_world_matrices
from buildings.glb_strip import DRACO, TYPES, _decode
from buildings.plateau_3d import glb_chunks

ROOF_COS = 0.8
DEFAULT_WALL = "#a0a0a0ff"
WGS84_A, WGS84_E2 = 6378137.0, 6.69437999014e-3


def _geodetic(ecef: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(lon, lat) in radians of (n, 3) ECEF points."""
    x, y, z = ecef[:, 0], ecef[:, 1], ecef[:, 2]
    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    lat = np.arctan2(z, p * (1 - WGS84_E2))
    for _ in range(5):
        n = WGS84_A / np.sqrt(1 - WGS84_E2 * np.sin(lat) ** 2)
        h = p / np.cos(lat) - n
        lat = np.arctan2(z, p * (1 - WGS84_E2 * n / (n + h)))
    return lon, lat


def _up(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    return np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], axis=1)


def linear_rgba(hex_colour: str | None) -> list[float]:
    """'#rrggbb[aa]' (sRGB) -> linear RGBA with alpha 1 (the alpha byte is a style flag, not opacity)."""
    h = (hex_colour or DEFAULT_WALL).lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb] + [1.0]


def _untextured(document: dict[str, Any], prim: dict[str, Any]) -> bool:
    if "material" not in prim:
        return True
    material = document.get("materials", [])[prim["material"]]
    if str(material.get("name", "")).startswith("pp-"):
        return False
    return "baseColorTexture" not in material.get("pbrMetallicRoughness", {})


def _roof_crop(photo: Image.Image, bounds: list[float], lon: np.ndarray, lat: np.ndarray, max_texture: int):
    """The photo over the roofs' extent (degrees) with a 2-pixel margin -> (image, [w, s, e, n] of the crop)."""
    w, s, e, n = bounds
    iw, ih = photo.size
    x0 = int(np.clip(math.floor((lon.min() - w) / (e - w) * iw) - 2, 0, iw - 1))
    x1 = int(np.clip(math.ceil((lon.max() - w) / (e - w) * iw) + 2, x0 + 1, iw))
    y0 = int(np.clip(math.floor((n - lat.max()) / (n - s) * ih) - 2, 0, ih - 1))
    y1 = int(np.clip(math.ceil((n - lat.min()) / (n - s) * ih) + 2, y0 + 1, ih))
    crop = photo.convert("RGB").crop((x0, y0, x1, y1))
    if max(crop.size) > max_texture:
        k = max_texture / max(crop.size)
        crop = crop.resize((max(1, round(crop.width * k)), max(1, round(crop.height * k))), Image.LANCZOS)
    return crop, [w + x0 / iw * (e - w), n - y1 / ih * (n - s), w + x1 / iw * (e - w), n - y0 / ih * (n - s)]


def bake_untextured(payload: bytes, rtc: list[float], tile_ids: list[str], facade_colors: list[str | None],
                    roof_photo: Image.Image, roof_bounds: list[float], *, roof_cos: float = ROOF_COS,
                    max_texture: int = 2048) -> bytes:
    document, binary, _ = glb_chunks(payload)
    matrices = _mesh_world_matrices(document)
    jobs = []
    for mi, mesh in enumerate(document.get("meshes", [])):
        m = np.asarray((matrices.get(mi) or [_identity_mat4()])[0], float)
        for pi, prim in enumerate(mesh.get("primitives", [])):
            if not _untextured(document, prim):
                continue
            attrs, faces = _decode(document, binary, prim)
            if not len(faces):
                continue
            pos = attrs["POSITION"].astype(float)
            world = pos @ m[:3, :3].T + m[:3, 3]
            ecef = np.asarray(rtc, float) + np.stack([world[:, 0], -world[:, 2], world[:, 1]], axis=1)
            lon, lat = _geodetic(ecef)
            tri = ecef[faces]
            normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            length = np.linalg.norm(normal, axis=1)
            up = _up(lon[faces].mean(axis=1), lat[faces].mean(axis=1))
            cos = np.abs((normal * up).sum(axis=1)) / np.maximum(length, 1e-12)
            jobs.append((mi, pi, attrs, faces, (cos > roof_cos) & (length > 0), np.degrees(lon), np.degrees(lat)))
    if not jobs:
        return payload

    roof_lon = np.concatenate([lon[faces[roof]].reshape(-1) for _, _, _, faces, roof, lon, _ in jobs])
    roof_lat = np.concatenate([lat[faces[roof]].reshape(-1) for _, _, _, faces, roof, _, lat in jobs])

    out = bytearray()
    views: list[dict[str, Any]] = []

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
    materials = document.setdefault("materials", [])

    def add_accessor(data: np.ndarray, *, indices: bool = False, minmax: bool = False) -> int:
        if indices:
            raw = np.ascontiguousarray(data, np.uint32)
            acc = {"bufferView": add_view(raw.tobytes(), 34963), "componentType": 5125, "count": len(raw), "type": "SCALAR"}
        else:
            raw = np.ascontiguousarray(data, np.float32)
            acc = {"bufferView": add_view(raw.tobytes(), 34962), "componentType": 5126, "count": len(raw),
                   "type": TYPES[raw.shape[1]]}
            if minmax and len(raw):
                acc.update(min=raw.min(axis=0).tolist(), max=raw.max(axis=0).tolist())
        accessors.append(acc)
        return len(accessors) - 1

    wall_material = len(materials)
    materials.append({"name": "pp-wall", "pbrMetallicRoughness": {
        "baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0, "roughnessFactor": 0.9}})
    roof_material, crop_bounds = None, None
    if len(roof_lon):
        crop, crop_bounds = _roof_crop(roof_photo, roof_bounds, roof_lon, roof_lat, max_texture)
        jpeg = io.BytesIO()
        crop.save(jpeg, "JPEG", quality=90)
        images = document.setdefault("images", [])
        images.append({"bufferView": add_view(jpeg.getvalue()), "mimeType": "image/jpeg", "name": "pp-roof-photo"})
        samplers = document.setdefault("samplers", [])
        samplers.append({"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071})
        textures = document.setdefault("textures", [])
        textures.append({"source": len(images) - 1, "sampler": len(samplers) - 1})
        roof_material = len(materials)
        materials.append({"name": "pp-roof", "pbrMetallicRoughness": {
            "baseColorTexture": {"index": len(textures) - 1}, "metallicFactor": 0.0, "roughnessFactor": 1.0}})

    def part(attrs: dict[str, np.ndarray], faces: np.ndarray, extra: dict[str, np.ndarray]) -> dict[str, Any]:
        used = np.unique(faces.reshape(-1))
        remap = np.full(len(attrs["POSITION"]), -1, np.int64)
        remap[used] = np.arange(len(used))
        keep = [k for k in attrs if k in ("POSITION", "NORMAL") or k == _feature_attribute(attrs)]
        new = {k: add_accessor(attrs[k][used], minmax=(k == "POSITION")) for k in keep}
        for k, data in extra.items():
            new[k] = add_accessor(data[used])
        return {"attributes": new, "indices": add_accessor(remap[faces.reshape(-1)], indices=True)}

    for mi, pi, attrs, faces, roof, lon, lat in jobs:
        mesh = document["meshes"][mi]
        feature = _feature_attribute(attrs)
        ids = np.rint(attrs[feature][:, 0]).astype(np.int64) if feature else np.full(len(attrs["POSITION"]), -1)
        palette = np.asarray([linear_rgba(c) for c in facade_colors] + [linear_rgba(None)], np.float32)
        colour = palette[np.where((ids >= 0) & (ids < len(facade_colors)), ids, len(facade_colors))]
        prims = []
        if (~roof).any():
            prims.append({**part(attrs, faces[~roof], {"COLOR_0": colour}), "material": wall_material})
        if roof.any():
            w, s, e, n = crop_bounds
            uv = np.stack([(lon - w) / (e - w), (n - lat) / (n - s)], axis=1)
            prims.append({**part(attrs, faces[roof], {"TEXCOORD_0": uv}), "material": roof_material})
        mesh["primitives"][pi] = prims[0]
        mesh["primitives"].extend(prims[1:])

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
