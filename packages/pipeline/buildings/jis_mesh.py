"""JIS X 0410 third-level mesh: cells of 30" latitude by 45" longitude (about 1 km), named by 8 digits.

PLATEAU++ calibrates the heights of filled-in buildings per cell, on the PLATEAU buildings of that cell only, so
a building's height does not depend on the box it was built in (plateau_pp).
"""
from __future__ import annotations

import math

LAT_STEP = 30 / 3600
LON_STEP = 45 / 3600


def mesh3(lon: float, lat: float) -> str:
    """The cell holding (lon, lat); a point on a cell's south or west edge belongs to it."""
    i = math.floor(lat / LAT_STEP + 1e-9)          # third-level rows from the equator
    j = math.floor((lon - 100) / LON_STEP + 1e-9)  # third-level columns from 100 degrees east
    p, rest_i = divmod(i, 80)
    q, r = divmod(rest_i, 10)
    u, rest_j = divmod(j, 80)
    v, w = divmod(rest_j, 10)
    return f"{p:02d}{u:02d}{q}{v}{r}{w}"


def mesh3_bounds(code: str) -> list[float]:
    """[west, south, east, north] of a cell."""
    p, u, q, v, r, w = int(code[0:2]), int(code[2:4]), int(code[4]), int(code[5]), int(code[6]), int(code[7])
    south = (p * 80 + q * 10 + r) * LAT_STEP
    west = 100 + (u * 80 + v * 10 + w) * LON_STEP
    return [west, south, west + LON_STEP, south + LAT_STEP]


def mesh3_cells(bbox: list[float]) -> list[str]:
    """Every cell that overlaps the box [west, south, east, north], sorted."""
    w, s, e, n = bbox
    rows = range(math.floor(s / LAT_STEP + 1e-9), math.ceil(n / LAT_STEP - 1e-9))
    cols = range(math.floor((w - 100) / LON_STEP + 1e-9), math.ceil((e - 100) / LON_STEP - 1e-9))
    return sorted({mesh3(100 + (j + 0.5) * LON_STEP, (i + 0.5) * LAT_STEP) for i in rows for j in cols})
