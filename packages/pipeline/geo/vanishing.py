"""Which way a photograph's level lines run, against the walls of the city model: the turn of the camera.

The lines of the world that are level (window rows, eaves, kerbs, the courses of a facade) meet at vanishing points on
the horizon, one per compass direction (mod 180 degrees). Where the camera's pitch and roll are known, every edge pixel
of the picture says which direction its line runs, with no line fitting and no vanishing point to find:

    photo   the image line through an edge pixel (across its brightness gradient) and the camera's centre span a plane;
            a level line in it runs along the plane's level direction. Votes per degree of azimuth mod 180, from the
            pixels whose plane is far from upright (an upright line says nothing of the compass)
    model   the level edges of the city model's walls near the standing point, per degree mod 180, by length
    turn    1 - the correlation of the two at every turn of the photo (degrees); the walls of a street grid are
            square, so a turn is found mod 90 at best

Measured (projects/2026/11/26/plateau-pp-ultra-after/vanishing_eval.py): on Shibuya's 31 SfM-aligned street photos at
their true pitch, roll and place, the best turn is within 3 degrees (mod 90) for 4 photos, the median error is 20 degrees
and the truth ranks 34th of 90 turns; by chance 2.3, 22.5 and 45. Keeping only the pixels looking 15 degrees up (the
facades, not the people) gives 4, 17 and 38. The photos' strong level edges (signs, awnings, screens, people) do not run
along PLATEAU's walls often enough, so photo_place does not use it; it is kept so the next attempt starts from here.
"""
import numpy as np

from geo import skyline_match as sm


def ray_vectors(az, el):
    """Unit vectors (east, north, up) of rays given as azimuth and elevation in degrees."""
    a, e = np.radians(az), np.radians(el)
    return np.stack([np.sin(a) * np.cos(e), np.cos(a) * np.cos(e), np.sin(e)], -1)


def blur(hist, width):
    """A circular box blur of a histogram over +-width bins."""
    out = np.zeros_like(np.asarray(hist, float))
    for s in range(-width, width + 1):
        out += np.roll(hist, s)
    return out


def photo_azimuths(az, el, gray, sky=None, top=0.1, upright=20.0, bins=180):
    """Votes per azimuth degree (mod 180) of the level lines of the picture. az, el are the rays of the pixels
    (skyline_match.pixel_rays, step=1) and gray the brightness, all of one shape; sky (bool) is left out. An edge pixel
    is among the `top` strongest gradients; it votes with weight 1 - nz^2 (nz the upright part of its plane's normal),
    and not at all when its line is within `upright` degrees of upright."""
    gray = np.asarray(gray, float)
    ray = ray_vectors(az, el)
    gy, gx = np.gradient(gray)
    g = np.hypot(gx, gy)
    keep = np.ones(gray.shape, bool) if sky is None else ~np.asarray(sky, bool)
    if not keep.any():
        return np.zeros(bins)
    keep &= g > max(np.quantile(g[keep], 1 - top), 1e-9)
    ry, rx = np.gradient(ray, axis=(0, 1))
    tx, ty = -gy / np.maximum(g, 1e-12), gx / np.maximum(g, 1e-12)
    d = rx * tx[..., None] + ry * ty[..., None]          # where the line goes, as a change of the ray
    n = np.cross(ray, d)
    n /= np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-12)
    nz = np.abs(n[..., 2])
    keep &= nz > np.sin(np.radians(upright))
    line_az = np.degrees(np.arctan2(n[..., 1], -n[..., 0])) % 180     # (n_y, -n_x, 0) lies in the plane, level
    k = np.floor(line_az[keep] * bins / 180).astype(np.int64) % bins
    return np.bincount(k, weights=(1 - nz[keep] ** 2), minlength=bins)


def model_azimuths(tris, eye, radius=120.0, min_len=1.0, max_slope=0.05, bins=180):
    """Length of the level edges of the model within `radius` of eye, per azimuth degree (mod 180)."""
    a, b = sm.unique_edges(tris)
    d = b - a
    run = np.hypot(d[:, 0], d[:, 1])
    mid = (a[:, :2] + b[:, :2]) / 2 - np.asarray(eye[:2], float)
    keep = (run >= min_len) & (np.abs(d[:, 2]) <= max_slope * run) & (np.hypot(mid[:, 0], mid[:, 1]) <= radius)
    az = np.degrees(np.arctan2(d[keep, 0], d[keep, 1])) % 180
    return np.bincount(np.floor(az * bins / 180).astype(np.int64) % bins, weights=run[keep], minlength=bins)


def turn_cost(photo, model):
    """1 - the correlation of photo[b] with model[b + s] for every turn s (bins): an array as long as the histograms."""
    p = np.asarray(photo, float) - np.mean(photo)
    m = np.asarray(model, float) - np.mean(model)
    num = np.fft.irfft(np.conj(np.fft.rfft(p)) * np.fft.rfft(m), n=len(p))
    den = np.linalg.norm(p) * np.linalg.norm(m)
    return 1 - num / den if den > 0 else np.ones(len(p))
