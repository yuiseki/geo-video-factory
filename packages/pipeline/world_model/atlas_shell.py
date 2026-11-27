"""Where an atlas's vertices go so that it lies a little off the faces it paints (pp_scene), with closed edges.

build_atlas writes every triangle with its own vertices. Pushed out along each triangle's own normal, a wall and the
roof above it part at their shared edge, and the building below shows through a crack along every edge of every
painted building (the veranda of Minowa). The copies of a vertex at one place move together instead, along the
area-weighted mean normal of the faces that meet there.
"""
from __future__ import annotations

import numpy as np


def push_out(vertices, faces, distance: float = 0.15, snap: float = 0.01) -> np.ndarray:
    """New positions (n, 3): every vertex moved `distance` along the mean normal of the faces at its place
    (positions within `snap` metres are one place)."""
    v = np.asarray(vertices, float)
    f = np.asarray(faces, np.int64).reshape(-1, 3)
    n = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])          # length = 2 x area: area-weighted
    key = np.round(v / snap).astype(np.int64)
    _, place = np.unique(key, axis=0, return_inverse=True)
    place = place.ravel()
    acc = np.zeros((place.max() + 1, 3))
    for k in range(3):
        np.add.at(acc, place[f[:, k]], n)
    length = np.linalg.norm(acc, axis=1, keepdims=True)
    unit = np.where(length > 1e-12, acc / np.maximum(length, 1e-12), [0.0, 0.0, 1.0])
    return v + distance * unit[place]
