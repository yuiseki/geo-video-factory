"""The places photo_place.py searches: a grid within a radius, the fine grid around the best few places of a
coarse one, and the fine space (places and poses) around one pose."""
from itertools import product

import numpy as np


def seeded_places(coarse, cost, count, coarse_step, step, x0, y0, radius):
    """The fine grid around the `count` best coarse places that lie at least two coarse steps apart: every place
    within one coarse step of a seed, on the fine step, inside the search radius."""
    order = [i for i in np.argsort(cost) if np.isfinite(cost[i])]
    picked = []
    for i in order:
        if all(np.hypot(*(coarse[i, :2] - coarse[j, :2])) >= 2 * coarse_step for j in picked):
            picked.append(i)
        if len(picked) == count:
            break
    offs = np.arange(-coarse_step, coarse_step + step / 2, step)
    pts = {(round(float(coarse[i, 0] + dx), 3), round(float(coarse[i, 1] + dy), 3))
           for i in picked for dx in offs for dy in offs}
    pts = sorted(p for p in pts if np.hypot(p[0] - x0, p[1] - y0) <= radius)
    return np.array([[x, y, coarse[0, 2]] for x, y in pts])


def grid_places(x0, y0, radius, step, z):
    """Standing points on a square grid around (x0, y0), all at the height z: (n, 3), east running fastest, and the
    grid's east and north values."""
    xs = np.arange(x0 - radius, x0 + radius + step / 2, step)
    ys = np.arange(y0 - radius, y0 + radius + step / 2, step)
    gy, gx = np.meshgrid(ys, xs, indexing="ij")
    return np.stack([gx.ravel(), gy.ravel(), np.full(gx.size, float(z))], 1), xs, ys


def fine_space(coarse, half=4.0, step=0.5, angle=2.0, roll=2.0, fov=5):
    """The places and poses of the second search: half a metre and half a degree around the coarse answer, and `fov`
    fields of view within 4 % of it."""
    places, _, _ = grid_places(coarse["east"], coarse["north"], half, step, coarse["up"])
    scales = np.linspace(0.96, 1.04, fov) if fov > 1 else np.array([1.0])
    poses = list(product(np.arange(coarse["pitch"] - angle, coarse["pitch"] + angle + 0.01, 0.5),
                         np.arange(coarse["roll"] - roll, coarse["roll"] + roll + 0.01, 0.5),
                         coarse["hfov"] * scales))
    return places, poses
