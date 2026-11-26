"""Repeating window patterns for the walls PLATEAU++ bakes into its GLBs (pp_bake).

tile(style) -> (day, night): two RGB images of BAYS x STOREYS cells, CELL pixels each, the bottom row being the
ground storey. day multiplies the wall's own colour (COLOR_0): 1 on paint, darker on glass, slab lines, siding;
night is the light of the windows that are lit, for emissiveTexture. module(style, id) gives one building's bay
and storey in metres, so a wall maps to UV = (metres along / (bay x BAYS), -metres up / (storey x STOREYS)).

The patterns follow the renderer's shaders they replace (renderer/src/page/plateau-facade-glsl.ts
UNTEXTURED_FACADE for untextured PLATEAU walls, city-facade-glsl.ts CITY_FACADE for filled-in buildings):
storey heights, bay widths, window rectangles, glass colours, which bays a house glazes. Differences, all for the
sake of plain glTF: glass multiplies the wall colour instead of replacing it (mix towards glass / WALL_REF),
glass does not reflect a sky that changes with height, and a factory's band of high windows under the eave is
left out (it depends on each building's eave). Illustrations for the picture, never a survey of real facades.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache

import numpy as np
from PIL import Image

BAYS, STOREYS, CELL = 8, 4, 64
WALL_REF = 1.0                      # glass colour / WALL_REF multiplies the wall colour (itself about 0.3 to 0.5)
PROXY_STYLES = {0: "house", 1: "rc", 2: "shed", 3: "apartment", 4: "factory", 5: "office", 6: "old_house"}
STYLES = ("curtain", "house", "rc", "shed", "apartment", "factory", "office", "old_house")

# storey (m), bay = base + spread x rnd (m), window half width and rows (share of a cell), glazed-column share
SPEC = {
    "curtain":   dict(storey=3.7, storey_spread=0.5, bay=1.35, spread=0.7, x=(0.07, 0.93), y=(0.24, 0.93), cols=1.0, mix=0.9, lit=0.7),
    "house":     dict(storey=2.85, bay=3.3, spread=1.3, x=(0.28, 0.72), y=(0.32, 0.82), cols=0.65, mix=0.72, lit=0.6, siding=0.42),
    "old_house": dict(storey=2.85, bay=3.3, spread=1.3, x=(0.33, 0.67), y=(0.32, 0.82), cols=0.65, mix=0.72, lit=0.6, boards=0.24),
    "rc":        dict(storey=3.2, bay=2.6, spread=0.8, x=(0.16, 0.84), y=(0.32, 0.82), cols=1.0, mix=0.72, lit=0.6, band=True),
    "apartment": dict(storey=3.2, bay=3.0, spread=0.6, x=(0.04, 0.96), y=(0.40, 0.92), cols=1.0, mix=0.72, lit=0.6, band=True, balcony=True),
    "office":    dict(storey=3.2, bay=1.6, spread=0.4, x=(0.02, 0.98), y=(0.38, 0.88), cols=1.0, mix=0.72, lit=0.6, band=True),
    "shed":      dict(storey=3.2, bay=3.0, spread=0.0, cols=0.0, slats=0.55),
    "factory":   dict(storey=4.5, bay=4.0, spread=1.0, cols=0.0, ribs=0.32),
}


def _hash01(*parts) -> float:
    return int(hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def module(style: str, identifier: str) -> tuple[float, float]:
    """(bay, storey) in metres of this building's facade."""
    s = SPEC[style]
    bay = s["bay"] + s["spread"] * _hash01("bay", identifier)
    storey = s["storey"] + s.get("storey_spread", 0.0) * _hash01("storey", identifier)
    return bay, storey


def _srgb(linear: np.ndarray) -> np.ndarray:
    c = np.clip(linear, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


@lru_cache(maxsize=None)
def _tile(style: str) -> tuple[bytes, bytes]:
    s = SPEC[style]
    h, w = STOREYS * CELL, BAYS * CELL
    py, px = np.mgrid[0:h, 0:w]
    storey = (STOREYS - 1) - py // CELL           # 0 at the bottom row
    bay = px // CELL
    fy = 1 - ((py % CELL) + 0.5) / CELL           # 0 at the bottom of a storey
    fx = ((px % CELL) + 0.5) / CELL
    day = np.ones((h, w, 3))
    night = np.zeros((h, w, 3))
    cell_rnd = np.vectorize(lambda b, st, salt: _hash01(style, salt, b, st))
    if s["cols"] > 0:
        x0, x1 = s["x"]
        y0, y1 = s["y"]
        glazed = np.vectorize(lambda b: _hash01(style, "column", b) < s["cols"])(bay)
        window = glazed & (fx > x0) & (fx < x1) & (fy > y0) & (fy < y1)
        r = cell_rnd(bay, storey, "glass")
        if style == "curtain":
            glass = np.stack([0.33 + 0.33 * r, 0.40 + 0.33 * r, 0.48 + 0.32 * r], axis=-1) * 0.7
        elif style == "office":
            glass = np.stack([0.30 + 0.1 * r, 0.40 + 0.1 * r, 0.50 + 0.1 * r], axis=-1)
        elif style in ("house", "old_house"):
            glass = np.broadcast_to([0.24, 0.28, 0.33], (h, w, 3))
        else:
            glass = np.stack([0.20 + 0.22 * r, 0.24 + 0.24 * r, 0.29 + 0.27 * r], axis=-1)
            if style == "apartment":
                glass = glass * 0.4 + np.array([0.16, 0.18, 0.21]) * 0.6
        multiplier = np.minimum(glass / WALL_REF, 1.0)
        day = np.where(window[..., None], 1 - s["mix"] + s["mix"] * multiplier, day)
        lit = window & (cell_rnd(bay, storey, "lit") < s["lit"])
        warm = np.where((cell_rnd(bay, storey, "tint") > 0.6)[..., None], [0.72, 0.88, 1.0], [1.0, 0.75, 0.45])
        night = np.where(lit[..., None], warm, night)
    if s.get("band") or style == "curtain":
        edge = np.minimum(fy, 1 - fy) < (0.06 if style == "curtain" else 0.05)
        day = day * np.where(edge, 1 - (0.18 if style == "curtain" else 0.08), 1.0)[..., None]
    if s.get("balcony"):
        rail = (storey >= 1) & (fy > 0.02) & (fy < 0.30)
        day = np.where(rail[..., None], day * 0.45 + 0.55, day)        # a light railing (0.86 lit, over WALL_REF: 1)
    metres_y = (storey + fy) * s["storey"]
    metres_x = (bay + fx) * s["bay"]
    for key, axis, depth, share in (("siding", metres_y, 0.10, 0.12), ("boards", metres_x, 0.12, 0.15),
                                    ("slats", metres_x, 0.12, 0.25), ("ribs", metres_x, 0.14, 0.35)):
        if key in s:
            line = (axis / s[key]) % 1.0 < share
            day = day * np.where(line, 1 - depth, 1.0)[..., None]
    to8 = lambda a: (np.round(_srgb(a) * 255)).astype(np.uint8).tobytes()  # noqa: E731
    return to8(day), to8(night)


def tile(style: str) -> tuple[Image.Image, Image.Image]:
    day, night = _tile(style)
    size = (BAYS * CELL, STOREYS * CELL)
    return Image.frombytes("RGB", size, day), Image.frombytes("RGB", size, night)
