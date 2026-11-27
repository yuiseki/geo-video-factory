"""The places photo_place.py searches: a grid within a radius, the fine grid around the best few places of a
coarse one, and the fine space (places and poses) around one pose; and the picture of their costs."""
from itertools import product

import numpy as np
from PIL import Image, ImageDraw


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


RAMP = np.array([[253, 231, 37], [33, 145, 140], [68, 1, 84]], float)  # low cost to high


def costmap(per_place, xs, ys, tris, ground, given, found, size=800):
    """The cost of the best pose at every standing point as a picture, north up: yellow is low, purple is the median
    or worse. White lines are the model near the ground, the red ring the given point, the white cross the found."""
    m = np.asarray(per_place, float).reshape(len(ys), len(xs))
    lo, hi = np.nanmin(m), np.nanpercentile(m, 50)
    t = np.clip((np.nan_to_num(m, nan=hi) - lo) / max(hi - lo, 1e-9), 0, 1) * 2
    i = np.minimum(t.astype(int), 1)
    rgb = RAMP[i] + (RAMP[i + 1] - RAMP[i]) * (t - i)[..., None]
    k = max(1, size // max(m.shape))
    im = Image.fromarray(rgb[::-1].astype(np.uint8)).resize((len(xs) * k, len(ys) * k), Image.NEAREST)
    step = xs[1] - xs[0] if len(xs) > 1 else 1.0

    def px(e, n):
        return (e - xs[0] + step / 2) / step * k, (ys[-1] + step / 2 - n) / step * k

    draw = ImageDraw.Draw(im)
    ctr = tris.mean(1)
    inside = ((np.abs(ctr[:, 0] - xs.mean()) < np.ptp(xs) / 2 + 30) & (np.abs(ctr[:, 1] - ys.mean()) < np.ptp(ys) / 2 + 30)
              & (np.abs(tris[:, :, 2].min(1) - ground) < 3))
    for tri in tris[inside][::7]:
        draw.line([px(*p[:2]) for p in tri[[0, 1, 2, 0]]], fill=(255, 255, 255), width=1)
    gx, gy = px(*given)
    draw.ellipse([gx - 7, gy - 7, gx + 7, gy + 7], outline=(255, 0, 0), width=2)
    fx, fy = px(*found)
    draw.line([fx - 7, fy - 7, fx + 7, fy + 7], fill=(255, 255, 255), width=3)
    draw.line([fx - 7, fy + 7, fx + 7, fy - 7], fill=(255, 255, 255), width=3)
    return im
