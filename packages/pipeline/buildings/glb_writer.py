"""Rebuilding a GLB around its existing buffer views, for pp_bake: new accessors, textures, materials, primitives."""
from __future__ import annotations

import io
import json
import struct
from typing import Any

import numpy as np
from PIL import Image

from buildings import facade_tiles
from buildings.glb_strip import DRACO, TYPES

REPEAT, CLAMP, LINEAR, MIPMAP = 10497, 33071, 9729, 9987
BAKE_KEY = "plateau_pp_bake"


def encode(image: Image.Image, mime: str) -> bytes:
    buf = io.BytesIO()
    if mime == "image/webp":
        image.save(buf, "WEBP", quality=88, method=3)
    elif mime == "image/png":
        image.save(buf, "PNG")
    else:
        image.convert("RGB").save(buf, "JPEG", quality=90)
    return buf.getvalue()


class Writer:
    """Rebuilds a GLB: every existing buffer view kept at its index (optionally with new bytes), new ones added."""

    def __init__(self, document: dict[str, Any], binary: bytes, replace: dict[int, bytes] | None = None):
        self.doc, self.out, self.views = document, bytearray(), []
        replace = replace or {}
        for i, v in enumerate(document.get("bufferViews", [])):
            start = int(v.get("byteOffset", 0))
            raw = replace.get(i, binary[start:start + int(v["byteLength"])])
            new = self.view(raw)
            self.views[new].update({k: v[k] for k in ("byteStride", "target") if k in v and i not in replace})
        self.accessors = document.setdefault("accessors", [])
        self.materials = document.setdefault("materials", [])
        self.facades: dict[str, int] = {}

    def view(self, raw: bytes, target: int | None = None) -> int:
        self.out.extend(b"\0" * (-len(self.out) % 4))
        v = {"buffer": 0, "byteOffset": len(self.out), "byteLength": len(raw)}
        if target:
            v["target"] = target
        self.out.extend(raw)
        self.views.append(v)
        return len(self.views) - 1

    def accessor(self, data: np.ndarray, *, indices: bool = False, minmax: bool = False) -> int:
        if indices:
            raw = np.ascontiguousarray(data, np.uint32)
            acc = {"bufferView": self.view(raw.tobytes(), 34963), "componentType": 5125, "count": len(raw), "type": "SCALAR"}
        else:
            raw = np.ascontiguousarray(data, np.float32)
            acc = {"bufferView": self.view(raw.tobytes(), 34962), "componentType": 5126, "count": len(raw),
                   "type": TYPES[raw.shape[1]]}
            if minmax and len(raw):
                acc.update(min=raw.min(axis=0).tolist(), max=raw.max(axis=0).tolist())
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def texture(self, image: Image.Image, mime: str, wrap: int, name: str) -> int:
        images = self.doc.setdefault("images", [])
        images.append({"bufferView": self.view(encode(image, mime)), "mimeType": mime, "name": name})
        samplers = self.doc.setdefault("samplers", [])
        samplers.append({"magFilter": LINEAR, "minFilter": MIPMAP, "wrapS": wrap, "wrapT": wrap})
        textures = self.doc.setdefault("textures", [])
        textures.append({"source": len(images) - 1, "sampler": len(samplers) - 1})
        return len(textures) - 1

    def material(self, spec: dict[str, Any]) -> int:
        self.materials.append({"doubleSided": True, **spec})
        return len(self.materials) - 1

    def roof(self, photo: Image.Image) -> int:
        tex = self.texture(photo, "image/jpeg", CLAMP, "pp-roof-photo")
        return self.material({"name": "pp-roof", "pbrMetallicRoughness": {
            "baseColorTexture": {"index": tex}, "metallicFactor": 0.0, "roughnessFactor": 1.0}})

    def facade(self, style: str) -> int:
        if style not in self.facades:
            day, night = facade_tiles.tile(style)
            self.facades[style] = self.material({
                "name": f"pp-wall-{style}",
                "pbrMetallicRoughness": {"baseColorTexture": {"index": self.texture(day, "image/png", REPEAT, f"pp-{style}-day")},
                                         "metallicFactor": 0.0, "roughnessFactor": 0.88},
                "emissiveTexture": {"index": self.texture(night, "image/png", REPEAT, f"pp-{style}-night")},
                "emissiveFactor": [0.0, 0.0, 0.0]})
        return self.facades[style]

    def primitive(self, attrs: dict[str, np.ndarray], faces: np.ndarray | None, material: int) -> dict[str, Any]:
        """A primitive of the given vertices; with faces, only the vertices they use, reindexed."""
        n = len(attrs["POSITION"])
        if faces is None:
            faces = np.arange(n - n % 3).reshape(-1, 3)
        used = np.unique(faces.reshape(-1))
        remap = np.full(n, -1, np.int64)
        remap[used] = np.arange(len(used))
        new = {k: self.accessor(v[used], minmax=(k == "POSITION")) for k, v in attrs.items()}
        return {"attributes": new, "indices": self.accessor(remap[faces.reshape(-1)], indices=True), "material": material}

    def finish(self, version: str) -> bytes:
        doc = self.doc
        for m in doc.get("materials", []):
            pbr = m.setdefault("pbrMetallicRoughness", {})
            pbr["metallicFactor"] = 0.0
            pbr["roughnessFactor"] = max(float(pbr.get("roughnessFactor", 1.0)), 0.85)
            m["doubleSided"] = True
        if not any(DRACO in (p.get("extensions") or {}) for m in doc.get("meshes", []) for p in m["primitives"]):
            for key in ("extensionsUsed", "extensionsRequired"):
                if key in doc:
                    doc[key] = [x for x in doc[key] if x != DRACO]
                    if not doc[key]:
                        del doc[key]
        doc.setdefault("asset", {"version": "2.0"}).setdefault("extras", {})[BAKE_KEY] = version
        doc["bufferViews"] = self.views
        self.out.extend(b"\0" * (-len(self.out) % 4))
        doc["buffers"] = [{"byteLength": len(self.out)}]
        j = json.dumps(doc, separators=(",", ":")).encode()
        j += b" " * (-len(j) % 4)
        total = 12 + 8 + len(j) + 8 + len(self.out)
        return (struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(j), b"JSON") + j
                + struct.pack("<I4s", len(self.out), b"BIN\0") + bytes(self.out))
