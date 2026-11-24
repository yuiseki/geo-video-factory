"""Replace sign faces in a photo with our own artwork, keeping each sign's light.

A sign's light is already baked into its surroundings (spill on walls, awnings, wet road), so the
replacement keeps the original's coarse colour field (block means over a small grid) and only swaps
the fine detail (letters, logos, faces) for a deterministic text-free pattern. Faces are handled in
their own frontal frame through the homography of their four corners (TL, TR, BR, BL), so the art
follows the photo's perspective.

CLI: sign_replace.py <photo> <signs.json> <out.png>
signs.json: {"signs": [{"name", "corners": [[u, v] x4], "pattern"?, "grid"?: [gx, gy], "seed"?}]}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

PATTERNS = ("led", "stripes", "blocks", "bands", "dots")


def homography(src, dst) -> np.ndarray:
    """3x3 matrix mapping four src points to four dst points."""
    rows, rhs = [], []
    for (x, y), (u, v) in zip(src, dst):
        rows.append([x, y, 1, 0, 0, 0, -x * u, -y * u])
        rows.append([0, 0, 0, x, y, 1, -x * v, -y * v])
        rhs += [u, v]
    h = np.linalg.solve(np.array(rows, float), np.array(rhs, float))
    return np.append(h, 1.0).reshape(3, 3)


def apply_homography(h: np.ndarray, point):
    x, y, w = h @ np.array([point[0], point[1], 1.0])
    return x / w, y / w


def _pil_coeffs(h: np.ndarray):
    h = h / h[2, 2]
    return tuple(h.flatten()[:8])


def rectify(photo: Image.Image, corners, size) -> Image.Image:
    """Frontal view of the quad `corners` as a `size` image."""
    w, h = size
    rect = [(0, 0), (w, 0), (w, h), (0, h)]
    return photo.transform(size, Image.PERSPECTIVE, _pil_coeffs(homography(rect, corners)), Image.BICUBIC)


def colour_field(face: Image.Image, grid) -> np.ndarray:
    """Block-mean colours of `face` on a gx x gy grid, shape (gy, gx, 3)."""
    gx, gy = grid
    a = np.asarray(face, np.float32)
    h, w = a.shape[:2]
    out = np.zeros((gy, gx, 3), np.float32)
    for j in range(gy):
        for i in range(gx):
            block = a[j * h // gy:(j + 1) * h // gy, i * w // gx:(i + 1) * w // gx]
            out[j, i] = block.reshape(-1, 3).mean(0)
    return out


def pattern(kind: str, size, rng: np.random.Generator) -> np.ndarray:
    """Deterministic text-free luminance pattern (h, w) with mean 1."""
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    if kind == "led":  # soft blobs under a fine LED pixel grid (screens)
        p = np.ones((h, w), np.float32)
        for _ in range(3):
            cx, cy, r = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(0.25, 0.6) * max(w, h)
            p += 0.6 * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * r * r))
        p *= 0.85 + 0.15 * (((xx % 3) > 0) & ((yy % 3) > 0))
    elif kind == "stripes":
        n = int(rng.integers(3, 7))
        p = 0.7 + 0.6 * ((np.floor(xx / w * n) % 2) if w >= h else (np.floor(yy / h * n) % 2))
    elif kind == "blocks":
        p = np.full((h, w), 0.8, np.float32)
        for _ in range(int(rng.integers(2, 5))):
            bw, bh = rng.uniform(0.2, 0.5) * w, rng.uniform(0.15, 0.4) * h
            x0, y0 = rng.uniform(0, w - bw), rng.uniform(0, h - bh)
            p[(xx >= x0) & (xx < x0 + bw) & (yy >= y0) & (yy < y0 + bh)] = 1.35
    elif kind == "bands":
        p = 0.8 + 0.5 * (np.sin(yy / max(1, h) * np.pi * rng.uniform(2, 5)) > 0.3)
    elif kind == "dots":
        step = max(4, min(w, h) // 6)
        p = 0.75 + 0.8 * ((((xx % step) - step / 2) ** 2 + ((yy % step) - step / 2) ** 2) < (step / 4) ** 2)
    else:
        raise ValueError(kind)
    p = p.astype(np.float32)
    return p / p.mean()


def recolour(face: Image.Image, luminance: np.ndarray, grid=(4, 3), blur: float = 0.0) -> Image.Image:
    """Art with `face`'s block-mean colours and `luminance`'s detail; block means are preserved."""
    w, h = face.size
    field = colour_field(face, grid)
    # A smooth gradient through the block means (no visible tiles), on which the pattern sits.
    small = Image.fromarray(np.clip(field, 0, 255).astype(np.uint8))
    smooth = np.asarray(small.resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(min(w, h) / (2 * max(grid)))), np.float32)
    p = luminance / max(1e-6, float(luminance.mean()))
    # Soften the pattern where the field is bright, so nothing clips and the colour balance holds.
    headroom = 255.0 / np.maximum(1.0, smooth.max(axis=2)) - 1.0
    excess = np.maximum(p - 1.0, 1e-6)
    p = np.where(p - 1.0 > headroom, 1.0 + excess * np.clip(headroom / excess, 0, 1), p)
    out = smooth * p[..., None]
    art = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    return art.filter(ImageFilter.GaussianBlur(blur)) if blur else art


def paste_quad(photo: Image.Image, art: Image.Image, corners, feather: float = 1.0) -> Image.Image:
    """Warp `art` onto the quad `corners` of `photo`."""
    w, h = art.size
    rect = [(0, 0), (w, 0), (w, h), (0, h)]
    warped = art.transform(photo.size, Image.PERSPECTIVE, _pil_coeffs(homography(corners, rect)), Image.BICUBIC)
    mask = Image.new("L", photo.size, 0)
    ImageDraw.Draw(mask).polygon([tuple(c) for c in corners], fill=255)
    if feather:
        mask = mask.filter(ImageFilter.GaussianBlur(feather))
    return Image.composite(warped, photo, mask)


def replace_signs(photo: Image.Image, signs) -> Image.Image:
    out = photo.copy()
    for index, sign in enumerate(signs):
        corners = [tuple(c) for c in sign["corners"]]
        width = int(max(np.hypot(*np.subtract(corners[1], corners[0])), np.hypot(*np.subtract(corners[2], corners[3]))))
        height = int(max(np.hypot(*np.subtract(corners[3], corners[0])), np.hypot(*np.subtract(corners[2], corners[1]))))
        size = (max(8, width * 2), max(8, height * 2))
        face = rectify(photo, corners, size)
        rng = np.random.default_rng(sign.get("seed", 1000 + index))
        kind = sign.get("pattern") or PATTERNS[int(rng.integers(len(PATTERNS)))]
        grid = tuple(sign.get("grid", (4, 3) if size[0] >= size[1] else (2, 5)))
        art = recolour(face, pattern(kind, size, rng), grid=grid, blur=0.6)
        out = paste_quad(out, art, corners, feather=sign.get("feather", 1.0))
    return out


def main() -> None:  # pragma: no cover - thin CLI
    photo = Image.open(sys.argv[1]).convert("RGB")
    signs = json.loads(Path(sys.argv[2]).read_text())["signs"]
    replace_signs(photo, signs).save(sys.argv[3])
    print(f"replaced {len(signs)} sign faces -> {sys.argv[3]}")


if __name__ == "__main__":  # pragma: no cover
    main()
