"""Where a photograph was taken, from the vertical corners of the buildings it shows.

The roofline (skyline_match.py) says nothing in a photo without sky: a street canyon, an arcade, a night shot.
The corners of the buildings are still there. A vertical line of the world keeps one azimuth all along its height,
whatever the camera's pitch and roll, so a corner is a direction of the compass, like a bin of the roofline:

    model   from a standing point, the azimuths of the vertical edges of the city model (PLATEAU's wall corners)
            that are not hidden behind a nearer wall, seen at one height (a few metres above the eye)
    photo   per azimuth bin, the share of the picture's cells (bin x el_step) holding an edge whose brightness
            changes across the azimuth (along the gradient of the azimuth): a vertical edge of the world
    cost    1 - the correlation of the two over the bins the photo sees, for every place and every turn (FFT)

Measured (projects/2026/11/26/plateau-pp-ultra-after, placement_eval.py and its README): on Shibuya's street photos
placed by SfM, the corner cost at the true pose is about 1 (no correlation) and the truth ranks in the middle of all
places and turns, also when only long vertical runs of edges are counted. The photos' vertical edges (signs, pillars,
people) do not stand where PLATEAU LOD2's wall corners stand. So photo_place --corners stays off by default; this is
kept so the next attempt starts from the measurement.

Angles are degrees; azimuth is clockwise from north in bins of 360 / bins degrees, bin i covering
[i, i + 1) * 360 / bins, as in skyline_match.py. The turn s lays the photo's bin b on the model's bin b + s.
"""
import numpy as np

from geo import skyline_match as sm


def prepare(tris, height, min_rise=3.0, max_run=0.5):
    """What model_corners needs of the triangles (n, 3, 3), once for all standing points: the corners (vertical
    edges at least min_rise high, at most max_run across, standing through `height`) and the walls cut at `height`."""
    tris = np.asarray(tris, float)
    a, b = sm.unique_edges(tris)
    rise = np.abs(b[:, 2] - a[:, 2])
    run = np.hypot(b[:, 0] - a[:, 0], b[:, 1] - a[:, 1])
    lo, hi = np.minimum(a[:, 2], b[:, 2]), np.maximum(a[:, 2], b[:, 2])
    keep = (rise >= min_rise) & (run <= max_run) & (lo <= height) & (hi >= height)
    corners = np.unique(np.round((a[keep, :2] + b[keep, :2]) / 2, 1), axis=0)
    h = height + 1e-4                                 # off any vertex
    z = tris[:, :, 2] - h
    ends = []
    for i, j in ((0, 1), (1, 2), (2, 0)):
        cross = z[:, i] * z[:, j] < 0
        t = np.where(cross, z[:, i] / np.where(cross, z[:, i] - z[:, j], 1.0), 0.0)
        p = tris[:, i, :2] + t[:, None] * (tris[:, j, :2] - tris[:, i, :2])
        ends.append((cross, p))
    n = sum(c.astype(int) for c, _ in ends)
    two = n == 2
    first = np.where(ends[0][0][:, None], ends[0][1], ends[1][1])
    second = np.where(ends[2][0][:, None], ends[2][1], ends[1][1])
    return dict(corners=corners.reshape(-1, 2), seg_a=first[two], seg_b=second[two])


def depth(prep, eye, bins=720):
    """The distance to the nearest wall (cut at the prepared height) at the centre of every azimuth bin; inf where
    there is none."""
    pa = prep["seg_a"] - np.asarray(eye[:2], float)
    pb = prep["seg_b"] - np.asarray(eye[:2], float)
    out = np.full(bins, np.inf)
    if len(pa) == 0:
        return out
    w = 2 * np.pi / bins
    al0 = np.arctan2(pa[:, 0], pa[:, 1])
    turn = (np.arctan2(pb[:, 0], pb[:, 1]) - al0 + np.pi) % (2 * np.pi) - np.pi
    lo = np.where(turn >= 0, al0, al0 + turn)
    span = np.abs(turn)
    k0 = np.ceil(lo / w - 0.5).astype(np.int64)
    k1 = np.floor((lo + span) / w - 0.5).astype(np.int64)
    n = np.where(span < np.pi - 1e-9, np.maximum(k1 - k0 + 1, 0), 0)
    if n.sum() == 0:
        return out
    e = np.repeat(np.arange(len(n)), n)
    k = k0[e] + np.arange(len(e)) - np.repeat(np.cumsum(n) - n, n)
    th = (k + 0.5) * w
    ux, uy = np.sin(th), np.cos(th)
    d = pb[e] - pa[e]
    den = d[:, 0] * uy - d[:, 1] * ux
    den = np.where(np.abs(den) < 1e-12, 1e-12, den)
    t = np.clip(-(pa[e, 0] * uy - pa[e, 1] * ux) / den, 0.0, 1.0)
    p = pa[e] + t[:, None] * d
    np.minimum.at(out, k % bins, np.hypot(p[:, 0], p[:, 1]))
    return out


def model_corners(prep, eye, bins=720, max_dist=250.0, slack=1.0):
    """1 in every azimuth bin where a corner stands that no nearer wall hides (within max_dist), else 0."""
    rel = prep["corners"] - np.asarray(eye[:2], float)
    dist = np.hypot(rel[:, 0], rel[:, 1])
    k = np.floor((np.degrees(np.arctan2(rel[:, 0], rel[:, 1])) % 360) / (360 / bins)).astype(np.int64) % bins
    near = depth(prep, eye, bins)
    seen = (dist <= max_dist) & (dist > 0.5) & (near[k] >= dist - slack)
    out = np.zeros(bins)
    out[k[seen]] = 1.0
    return out


def photo_corners(az, el, gray, sky, bins=720, el_step=0.25, align=0.9, top=0.1, min_count=4):
    """Per azimuth bin, the share of the picture's cells (not sky) that hold a vertical edge of the world; nan where
    the bin is not in the picture. az, el are the rays of the pixels (skyline_match.pixel_rays, step=1) and gray the
    brightness, all of one shape. An edge pixel is among the `top` strongest gradients and its gradient lies within
    acos(sqrt(align)) of the gradient of the azimuth."""
    az, el, gray = (np.asarray(v, float) for v in (az, el, gray))
    sky = np.asarray(sky, bool)
    gy, gx = np.gradient(gray)
    turn = np.exp(1j * np.radians(az))
    ty, tx = np.gradient(turn)
    ay, ax = np.imag(np.conj(turn) * ty), np.imag(np.conj(turn) * tx)    # the gradient of the azimuth, unwrapped
    g2 = gx * gx + gy * gy
    dot = gx * ax + gy * ay
    aligned = dot * dot >= align * g2 * (ax * ax + ay * ay) + 1e-12
    ground = ~sky
    strong = g2 > max(np.quantile(g2[ground], 1 - top), 1e-9) if ground.any() else np.zeros_like(sky)
    edge = strong & aligned & ground
    ne = int(round(180 / el_step))
    ai = np.floor(az / (360 / bins)).astype(np.int64) % bins
    ei = np.clip(np.floor((el + 90) / el_step).astype(np.int64), 0, ne - 1)
    cell = (ai * ne + ei)[ground]
    count = np.bincount(cell, minlength=bins * ne).reshape(bins, ne)
    hits = np.bincount(cell, weights=edge[ground], minlength=bins * ne).reshape(bins, ne)
    seen = count >= min_count
    n_seen = seen.sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n_seen > 0, (seen & (hits > 0)).sum(1) / n_seen, np.nan)


def corner_cost(photo, model, shifts=None, min_bins=20, blur=1):
    """1 - the correlation of the photo's corner profile (nan where it sees nothing) with every place's (places,
    bins) model_corners, widened by `blur` bins, at every turn: an array (places, shifts). nan when the photo sees
    fewer than min_bins bins or shows no corner at all; 1 where the model has no corner in the photo's view."""
    photo = np.asarray(photo, float)
    model = np.atleast_2d(np.asarray(model, float))
    places, bins = model.shape
    shifts = np.arange(bins) if shifts is None else np.asarray(shifts)
    idx = np.flatnonzero(~np.isnan(photo))
    if len(idx) < min_bins or np.ptp(photo[idx]) == 0:
        return np.full((places, len(shifts)), np.nan)
    wide = model.copy()
    for s in range(1, blur + 1):
        wide = np.maximum(wide, np.maximum(np.roll(model, s, 1), np.roll(model, -s, 1)))
    p = np.zeros(bins)
    p[idx] = photo[idx] - photo[idx].mean()
    m = np.zeros(bins)
    m[idx] = 1.0
    n = len(idx)

    def xcorr(x, y):         # out[:, s] = sum_b x[b] y[:, b + s]
        return np.fft.irfft(np.conj(np.fft.rfft(x))[None, :] * np.fft.rfft(y, axis=1), n=bins, axis=1)

    num = xcorr(p, wide)
    s1, s2 = xcorr(m, wide), xcorr(m, wide * wide)
    var = np.maximum(s2 - s1 * s1 / n, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = num / (np.sqrt(var) * np.sqrt((p * p).sum()))
    cost = np.where(var > 1e-9, 1.0 - corr, 1.0)
    return cost[:, shifts]
