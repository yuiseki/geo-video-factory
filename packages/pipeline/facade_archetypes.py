"""Guess what a building's walls look like from its roof in the aerial photo.

Heuristic: buildings whose roofs look alike tend to have walls that look alike. From the
orthophoto pixels inside the footprint we measure the roof color (median), saturation,
brightness and texture (spread of luminance: rooftop equipment makes a roof speckled), and
combine them with floor area, height, the GSI structure class and pitched/flat:

  house      small, pitched, colored roof           -> light siding, small windows
  old_house  small, pitched, dark grey tile         -> darker mortar / boards
  apartment  flat, speckled grey, several storeys   -> balconies on every floor
  office     flat, smooth grey, several storeys     -> ribbon windows
  factory    large, flat, uniform metal roof        -> corrugated panels, high windows
  shed       roof without walls (GSI 3111/3112)     -> slats

An OSM `building=*` type, when mapped, wins over the roof. Everything here is an estimate for
the picture and is labelled as such on screen.
"""
from __future__ import annotations

import colorsys
import hashlib
import math
from typing import Any

from PIL import Image, ImageDraw

# Facade styles understood by the renderer's city-proxy shader (_STYLE.x).
STYLE_CODES = {'house': 0, 'rc': 1, 'shed': 2, 'apartment': 3, 'factory': 4, 'office': 5, 'old_house': 6}

OSM_TYPES = {
    'house': 'house', 'detached': 'house', 'residential': 'house', 'semidetached_house': 'house', 'terrace': 'house',
    'apartments': 'apartment', 'dormitory': 'apartment',
    'warehouse': 'factory', 'industrial': 'factory', 'factory': 'factory', 'manufacture': 'factory',
    'retail': 'office', 'commercial': 'office', 'office': 'office', 'supermarket': 'office', 'school': 'office',
    'hospital': 'office', 'public': 'office', 'civic': 'office',
    'shed': 'shed', 'garage': 'shed', 'garages': 'shed', 'carport': 'shed', 'roof': 'shed',
}

PALETTES = {
    'house': ['#ece7dc', '#e2dacb', '#d9d3c8', '#e8dfcd', '#f0ebe0', '#dadad5', '#d6cbb8', '#cbc1b0'],
    'old_house': ['#8a7d6b', '#9c8f7a', '#7a7368', '#a59a88', '#6f665c'],
    'apartment': ['#e8e4dc', '#ddd6c8', '#d6d2cb', '#cfc3b0', '#e2dccf', '#c9c4ba'],
    'office': ['#c9c6bf', '#b8b4ad', '#d3cdc0', '#a9a7a3', '#bfb5a5'],
    'factory': ['#c8ccd0', '#b9c2c8', '#d8d4c4', '#a7b3bb', '#cfd2cc'],
    'shed': ['#8f8c86', '#9b968c', '#7f7c75'],
    'rc': ['#d2cdc3', '#c0baaf', '#d8d2c6', '#aca69d', '#cabca6'],
}


def _hash01(identifier: str, salt: str) -> float:
    return int(hashlib.sha256(f'{salt}:{identifier}'.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def roof_stats(image: Image.Image, ring: list[list[float]], bbox_degrees: list[float]) -> dict[str, Any] | None:
    """Color and texture of the orthophoto inside a lon/lat ring (None when it has no pixels there)."""
    import numpy as np

    west, south, east, north = bbox_degrees
    points = [((lon - west) / (east - west) * image.width, (north - lat) / (north - south) * image.height) for lon, lat in ring]
    x0 = max(0, math.floor(min(p[0] for p in points)))
    y0 = max(0, math.floor(min(p[1] for p in points)))
    x1 = min(image.width, math.ceil(max(p[0] for p in points)) + 1)
    y1 = min(image.height, math.ceil(max(p[1] for p in points)) + 1)
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    mask = Image.new('L', (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(mask).polygon([(x - x0, y - y0) for x, y in points], fill=255)
    pixels = np.asarray(image.crop((x0, y0, x1, y1)).convert('RGB'), dtype=np.float32)[np.asarray(mask) > 0]
    pixels = pixels[pixels.max(axis=1) >= 12]
    if len(pixels) < 3:
        return None
    rgb = tuple(int(v) for v in np.median(pixels, axis=0))
    luma = (0.2126 * pixels[:, 0] + 0.7152 * pixels[:, 1] + 0.0722 * pixels[:, 2]) / 255
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    return {'rgb': rgb, 'hue': h, 'sat': s, 'val': v, 'texture': float(luma.std()), 'pixels': int(len(pixels))}


def classify_facade(stats: dict[str, Any] | None, area_m2: float, height_m: float, vt_code: str, *,
                    pitched: bool, osm_building: str | None = None) -> str:
    """One of STYLE_CODES' names (except 'rc', kept for callers without a photo)."""
    if osm_building and osm_building in OSM_TYPES:
        return OSM_TYPES[osm_building]
    if str(vt_code) in ('3111', '3112'):
        return 'shed'
    low = height_m <= 7.5
    if stats is None:
        if low and area_m2 < 300:
            return 'house'
        return 'factory' if area_m2 >= 1500 else 'apartment' if height_m >= 9 else 'office'
    smooth = stats['texture'] < 0.10
    if area_m2 >= 1500 and not pitched and smooth:
        return 'factory'
    if pitched or (low and area_m2 < 300):
        if stats['val'] < 0.32 and stats['sat'] < 0.15:
            return 'old_house'
        return 'house'
    if height_m >= 8:
        return 'office' if smooth else 'apartment'
    return 'factory' if smooth and area_m2 >= 300 else 'office'


def facade_wall_color(archetype: str, stats: dict[str, Any] | None, identifier: str) -> tuple[float, float, float]:
    """Linear-ish 0..1 sRGB wall color: a palette by kind, houses leaning a little toward the roof hue."""
    palette = PALETTES.get(archetype, PALETTES['rc'])
    hexcolor = palette[int(_hash01(identifier, 'facade') * len(palette)) % len(palette)]
    r, g, b = (int(hexcolor[i:i + 2], 16) / 255 for i in (1, 3, 5))
    k = 0.95 + 0.08 * _hash01(identifier, 'facade-v')
    r, g, b = (min(1.0, c * k) for c in (r, g, b))
    if stats is not None and archetype in ('house', 'old_house') and stats['sat'] > 0.12:
        tr, tg, tb = colorsys.hsv_to_rgb(stats['hue'], 0.35, 0.85)
        w = 0.18
        r, g, b = (c * (1 - w) + t * w for c, t in zip((r, g, b), (tr, tg, tb)))
    return (r, g, b)
