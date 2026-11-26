"""The look of PLATEAU++ written into its GLBs, so every renderer shows the same city with plain glTF.

Until now the renderer gave PLATEAU++ its look at draw time (renderer/src/page: plateau-materials.ts,
plateau-facade-glsl.ts, city-materials.ts, city-facade-glsl.ts, city-tone.ts) and other renderers (Blender) did not.
Baking moves every such decision here:

bake_untextured(payload, rtc, ids, facade_colors, roof_photo, roof_bounds), for a PLATEAU tile:
- each primitive without a photo texture splits into pp-roof (faces within ~37 degrees of the local vertical,
  either winding, showing the GSI photo cut to the tile's roofs, projected straight down) and one pp-wall-<style>
  per facade style (curtain for a tall building, house for a low one: the alpha byte of city_proxy.wall_hex).
  Walls carry COLOR_0 = the palette bytes x PALETTE_WALL_GAIN (the renderer reads the bytes as they are) and a
  repeating window pattern (facade_tiles) in metres: along the wall (east or north, whichever the wall faces
  away from) and up from the building's lowest point.
- photo-textured materials keep their geometry and get what the renderer did to them: rough non-metal, double
  sided, the 0.7 base colour factor dropped, washed-out atlases toned down (texture_tone), and the photo itself
  raised to the aerial photo's tone (linear ^ PLATEAU_PHOTO_GAMMA, written back into the image).

bake_proxy(payload, ids, roof_photo, roof_bounds_m), for a city_proxy tile (Y-up local metres, uv = metres along
the wall and above ground, _STYLE = facade style): roofs (|normal.y| >= 0.35) show the photo, walls keep their
colour x PROXY_WALL_GAIN and get the window pattern of their style.

Window lights at night are emissiveTexture with emissiveFactor 0: a renderer raises the factor to light them.
That and a light that returns the albedo of an upward face are all a renderer has to agree on.
A baked GLB carries asset.extras.plateau_pp_bake and is returned as it is when baked again.
Positions of PLATEAU tiles: node matrices, then ECEF = rtc + (x, -z, y) (glb_spatial._feature_ecef_points).
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from PIL import Image

from buildings import facade_tiles
from buildings.glb_writer import Writer as _Writer
from buildings.pp_tone import (PALETTE_WALL_GAIN, PLATEAU_PHOTO_GAMMA, PROXY_WALL_GAIN, STUDY_MODEL_WHITE,  # noqa: F401
                               _photo_materials, palette_rgba, texture_source, texture_tone)
from buildings.glb_spatial import _feature_attribute, _identity_mat4, _mesh_world_matrices
from buildings.glb_strip import _decode
from buildings.plateau_3d import glb_chunks

BAKE_VERSION = "0.1.0"
ROOF_COS = 0.8
PROXY_ROOF_UP = 0.35
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


def _enu_rows(lon: float, lat: float) -> np.ndarray:
    return np.array([[-math.sin(lon), math.cos(lon), 0.0],
                     [-math.sin(lat) * math.cos(lon), -math.sin(lat) * math.sin(lon), math.cos(lat)],
                     [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]])


def _crop(photo: Image.Image, bounds: list[float], xs: np.ndarray, ys: np.ndarray, max_texture: int):
    """The photo over xs/ys (bounds' units, y up) with a 2-pixel margin -> (image, [w, s, e, n] of the crop)."""
    w, s, e, n = bounds
    iw, ih = photo.size
    x0 = int(np.clip(math.floor((xs.min() - w) / (e - w) * iw) - 2, 0, iw - 1))
    x1 = int(np.clip(math.ceil((xs.max() - w) / (e - w) * iw) + 2, x0 + 1, iw))
    y0 = int(np.clip(math.floor((n - ys.max()) / (n - s) * ih) - 2, 0, ih - 1))
    y1 = int(np.clip(math.ceil((n - ys.min()) / (n - s) * ih) + 2, y0 + 1, ih))
    crop = photo.convert("RGB").crop((x0, y0, x1, y1))
    if max(crop.size) > max_texture:
        k = max_texture / max(crop.size)
        crop = crop.resize((max(1, round(crop.width * k)), max(1, round(crop.height * k))), Image.LANCZOS)
    return crop, [w + x0 / iw * (e - w), n - y1 / ih * (n - s), w + x1 / iw * (e - w), n - y0 / ih * (n - s)]


def wall_uv(along: np.ndarray, up: np.ndarray, style: str, identifier: str) -> np.ndarray:
    """Metres along and up a wall -> UV in the style's pattern, with this building's bay, storey and column offset."""
    bay, storey = facade_tiles.module(style, identifier)
    shift = int(facade_tiles._hash01("offset", identifier) * facade_tiles.BAYS) / facade_tiles.BAYS
    return np.stack([along / (bay * facade_tiles.BAYS) + shift, -up / (storey * facade_tiles.STOREYS)], axis=1)


def _baked(document: dict[str, Any]) -> bool:
    return "plateau_pp_bake" in (document.get("asset", {}).get("extras") or {})


def _untextured(document: dict[str, Any], prim: dict[str, Any]) -> bool:
    if "material" not in prim:
        return True
    return "baseColorTexture" not in document["materials"][prim["material"]].get("pbrMetallicRoughness", {})


def bake_untextured(payload: bytes, rtc: list[float], tile_ids: list[str], facade_colors: list[str | None],
                    roof_photo: Image.Image, roof_bounds: list[float], *, roof_cos: float = ROOF_COS,
                    max_texture: int = 2048) -> bytes:
    document, binary, _ = glb_chunks(payload)
    if _baked(document):
        return payload
    matrices = _mesh_world_matrices(document)
    rtc = np.asarray(rtc, float)
    lon0, lat0 = (float(v[0]) for v in _geodetic(rtc[None, :]))
    enu_rows = _enu_rows(lon0, lat0)
    jobs = []
    for mi, mesh in enumerate(document.get("meshes", [])):
        m = np.asarray((matrices.get(mi) or [_identity_mat4()])[0], float)
        for pi, prim in enumerate(mesh.get("primitives", [])):
            if not _untextured(document, prim):
                continue
            attrs, faces = _decode(document, binary, prim)
            if not len(faces):
                continue
            world = attrs["POSITION"].astype(float) @ m[:3, :3].T + m[:3, 3]
            ecef = rtc + np.stack([world[:, 0], -world[:, 2], world[:, 1]], axis=1)
            lon, lat = _geodetic(ecef)
            tri = ecef[faces]
            normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            length = np.linalg.norm(normal, axis=1)
            up = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], axis=1)[faces].mean(axis=1)
            cos = np.abs((normal * up).sum(axis=1)) / np.maximum(length, 1e-12)
            feature = _feature_attribute(attrs)
            ids = np.rint(attrs[feature][:, 0]).astype(np.int64) if feature else np.full(len(ecef), -1)
            jobs.append(dict(mi=mi, pi=pi, attrs=attrs, faces=faces, roof=(cos > roof_cos) & (length > 0),
                             lon=np.degrees(lon), lat=np.degrees(lat), enu=(ecef - rtc) @ enu_rows.T,
                             normal=normal @ enu_rows.T, ids=ids, feature=feature))

    replace = _photo_materials(document, binary)
    w = _Writer(document, binary, replace)
    if not jobs:
        return w.finish(BAKE_VERSION)

    ground: dict[int, float] = {}
    top: dict[int, float] = {}
    for j in jobs:
        for i in np.unique(j["ids"]):
            z = j["enu"][j["ids"] == i, 2]
            ground[int(i)] = min(ground.get(int(i), np.inf), float(z.min()))
            top[int(i)] = max(top.get(int(i), -np.inf), float(z.max()))

    def style_of(i: int) -> str:
        c = facade_colors[i] if 0 <= i < len(facade_colors) else None
        if c and len(c.lstrip("#")) == 8:
            return "curtain" if c.lstrip("#")[6:8].lower() == "ff" else "house"
        return "curtain" if top.get(i, 0) - ground.get(i, 0) >= 12 else "house"

    def name_of(i: int) -> str:
        return str(tile_ids[i]) if 0 <= i < len(tile_ids) else str(i)

    roof_material, crop_bounds = None, None
    roof_lon = np.concatenate([j["lon"][j["faces"][j["roof"]]].reshape(-1) for j in jobs])
    roof_lat = np.concatenate([j["lat"][j["faces"][j["roof"]]].reshape(-1) for j in jobs])
    if len(roof_lon):
        crop, crop_bounds = _crop(roof_photo, roof_bounds, roof_lon, roof_lat, max_texture)
        roof_material = w.roof(crop)

    for j in jobs:
        attrs, faces, roof = j["attrs"], j["faces"], j["roof"]
        keep = {k: v for k, v in attrs.items() if k in ("POSITION", "NORMAL") or k == j["feature"]}
        prims = []
        walls = faces[~roof]
        if len(walls):
            flat = walls.reshape(-1)                                   # unindexed: UVs depend on the face
            n = j["normal"][~roof]
            east_facing = np.repeat(np.abs(n[:, 0]) > np.abs(n[:, 1]), 3)
            enu = j["enu"][flat]
            ids = j["ids"][flat]
            along = np.where(east_facing, enu[:, 1], enu[:, 0])
            up = enu[:, 2] - np.array([ground.get(int(i), 0.0) for i in ids])
            styles = np.array([style_of(int(i)) for i in ids])
            colour = np.array([palette_rgba(facade_colors[i] if 0 <= i < len(facade_colors) else None) for i in ids], np.float32)
            uv = np.zeros((len(flat), 2))
            for i in np.unique(ids):
                sel = ids == i
                uv[sel] = wall_uv(along[sel], up[sel], style_of(int(i)), name_of(int(i)))
            for style in sorted(set(styles.tolist())):
                tri = np.repeat((styles.reshape(-1, 3)[:, 0] == style), 3)
                sub = {k: v[flat][tri] for k, v in keep.items()}
                sub.update(COLOR_0=colour[tri], TEXCOORD_0=uv[tri])
                prims.append(w.primitive(sub, None, w.facade(style)))
        if roof.any():
            west, south, east, north = crop_bounds
            sub = dict(keep, TEXCOORD_0=np.stack([(j["lon"] - west) / (east - west), (north - j["lat"]) / (north - south)], axis=1))
            prims.append(w.primitive(sub, faces[roof], roof_material))
        mesh = document["meshes"][j["mi"]]
        mesh["primitives"][j["pi"]] = prims[0]
        mesh["primitives"].extend(prims[1:])
    return w.finish(BAKE_VERSION)


def bake_proxy(payload: bytes, tile_ids: list[str], roof_photo: Image.Image, roof_bounds_m: list[float], *,
               max_texture: int = 4096) -> bytes:
    """A city_proxy tile: roofs show the photo (bounds in the tile's local east/north metres), walls get windows."""
    document, binary, _ = glb_chunks(payload)
    if _baked(document):
        return payload
    w = _Writer(document, binary)
    jobs = []
    for mi, mesh in enumerate(document.get("meshes", [])):
        for pi, prim in enumerate(mesh.get("primitives", [])):
            attrs, faces = _decode(document, binary, prim)
            flat = faces.reshape(-1)
            attrs = {k: v[flat] for k, v in attrs.items()}               # unindexed, three vertices per face
            if "NORMAL" in attrs:
                up = np.abs(attrs["NORMAL"][:, 1].reshape(-1, 3).mean(axis=1))
            else:
                p = attrs["POSITION"].reshape(-1, 3, 3)
                nrm = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
                up = np.abs(nrm[:, 1]) / np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)
            jobs.append((mi, pi, attrs, up >= PROXY_ROOF_UP))
    roofs = [a["POSITION"][np.repeat(r, 3)] for _, _, a, r in jobs if r.any()]
    roof_material, crop_bounds = None, None
    if roofs:
        pts = np.concatenate(roofs)
        crop, crop_bounds = _crop(roof_photo, roof_bounds_m, pts[:, 0], -pts[:, 2], max_texture)
        roof_material = w.roof(crop)
    for mi, pi, attrs, roof in jobs:
        keep = {k: v for k, v in attrs.items() if k in ("POSITION", "NORMAL", "_BATCHID")}
        prims = []
        wall = np.repeat(~roof, 3)
        if wall.any():
            batch = np.rint(attrs["_BATCHID"][:, 0]).astype(np.int64) if "_BATCHID" in attrs else np.zeros(len(wall), np.int64)
            style_code = np.rint(attrs["_STYLE"][:, 0]).astype(np.int64) if "_STYLE" in attrs else np.zeros(len(wall), np.int64)
            uv0 = attrs.get("TEXCOORD_0", np.zeros((len(wall), 2), np.float32))
            colour = attrs.get("COLOR_0", np.full((len(wall), 3), STUDY_MODEL_WHITE, np.float32)).copy()
            colour[:, :3] *= PROXY_WALL_GAIN
            uv = np.zeros((len(wall), 2))
            styles = np.array([facade_tiles.PROXY_STYLES.get(int(c), "house") for c in style_code])
            for b in np.unique(batch[wall]):
                sel = wall & (batch == b)
                name = str(tile_ids[b]) if 0 <= b < len(tile_ids) else str(b)
                uv[sel] = wall_uv(uv0[sel, 0], uv0[sel, 1], styles[sel][0], name)
            for style in sorted(set(styles[wall].tolist())):
                sel = wall & (styles == style)
                sub = {k: v[sel] for k, v in keep.items()}
                sub.update(COLOR_0=colour[sel], TEXCOORD_0=uv[sel])
                prims.append(w.primitive(sub, None, w.facade(style)))
        if roof.any():
            sel = np.repeat(roof, 3)
            west, south, east, north = crop_bounds
            p = attrs["POSITION"][sel]
            sub = {k: v[sel] for k, v in keep.items()}
            sub["TEXCOORD_0"] = np.stack([(p[:, 0] - west) / (east - west), (north + p[:, 2]) / (north - south)], axis=1)
            prims.append(w.primitive(sub, None, roof_material))
        mesh = document["meshes"][mi]
        mesh["primitives"][pi] = prims[0]
        mesh["primitives"].extend(prims[1:])
    return w.finish(BAKE_VERSION)
