"""Tone of PLATEAU++ as the renderer used to set it at draw time (renderer/src/page/city-tone.ts, plateau-texture-tone.ts,
plateau-materials.ts), now applied once when the GLBs are baked (pp_bake)."""
from __future__ import annotations

import io
from typing import Any

import numpy as np
from PIL import Image

from buildings.glb_writer import encode as _encode

# renderer/src/page/city-tone.ts, measured on renders of Tokyo and Osaka
PLATEAU_PHOTO_GAMMA = 0.6
PALETTE_WALL_GAIN = 0.62
PROXY_WALL_GAIN = 0.45
STUDY_MODEL_WHITE = 0.57


def palette_rgba(hex_colour: str | None) -> list[float]:
    """Wall colour as the renderer used it: palette bytes / 255 x PALETTE_WALL_GAIN (no palette: study white)."""
    if not hex_colour:
        return [STUDY_MODEL_WHITE] * 3 + [1.0]
    h = hex_colour.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 * PALETTE_WALL_GAIN for i in (0, 2, 4)] + [1.0]


def texture_tone(image: Image.Image) -> float:
    """renderer plateau-texture-tone.ts: 0.64 or 0.78 for washed-out photo atlases, otherwise 1."""
    rgba = np.asarray(image.convert("RGBA").resize((32, 32), Image.BILINEAR), float)
    keep = rgba[..., 3] >= 16
    if not keep.any():
        return 1.0
    y = (0.2126 * rgba[..., 0] + 0.7152 * rgba[..., 1] + 0.0722 * rgba[..., 2])[keep] / 255
    mean, share = float(y.mean()), float((y > 0.78).mean())
    if share > 0.42 or mean > 0.74:
        return 0.64
    if share > 0.24 or mean > 0.64:
        return 0.78
    return 1.0


def _photo_lut() -> np.ndarray:
    c = np.arange(256) / 255
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4) ** PLATEAU_PHOTO_GAMMA
    out = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)
    return np.round(out * 255).astype(np.uint8)


def texture_source(texture: dict[str, Any]) -> int | None:
    """The image of a glTF texture, also when it is given through EXT_texture_webp (as plateau_3d writes them)."""
    if "source" in texture:
        return texture["source"]
    return (texture.get("extensions") or {}).get("EXT_texture_webp", {}).get("source")


def _photo_materials(document: dict[str, Any], binary: bytes) -> dict[int, bytes]:
    """Tone the photo-textured materials as the renderer did; returns new bytes for the photos' buffer views."""
    lut = _photo_lut()
    images = document.get("images", [])
    by_image: dict[int, list[dict[str, Any]]] = {}
    for m in document.get("materials", []):
        tex = m.get("pbrMetallicRoughness", {}).get("baseColorTexture")
        if tex is not None:
            source = texture_source(document["textures"][tex["index"]])
            if source is not None:
                by_image.setdefault(source, []).append(m)
    replace = {}
    for index, materials in by_image.items():
        image = images[index]
        if "bufferView" not in image:
            continue
        view = document["bufferViews"][image["bufferView"]]
        start = int(view.get("byteOffset", 0))
        photo = Image.open(io.BytesIO(binary[start:start + int(view["byteLength"])]))
        tone = texture_tone(photo)
        for m in materials:
            alpha = float((m["pbrMetallicRoughness"].get("baseColorFactor") or [1, 1, 1, 1])[3])
            m["pbrMetallicRoughness"]["baseColorFactor"] = [tone, tone, tone, alpha]
        mode = "RGBA" if photo.mode in ("RGBA", "LA", "P") else "RGB"
        photo = photo.convert(mode)
        bands = [b.point(lut.tolist()) for b in photo.split()[:3]] + list(photo.split()[3:])
        replace[image["bufferView"]] = _encode(Image.merge(mode, bands), image.get("mimeType", "image/jpeg"))
    return replace
