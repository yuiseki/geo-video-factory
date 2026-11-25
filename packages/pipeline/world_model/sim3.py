"""Put an SfM model (arbitrary scale, turn and place) into the metric frame of the city model.

A similarity is (s, A, t): x_world = s * A @ x_sfm + t. A camera of the SfM
model, x_cam = R_s @ (x_sfm - C_s), becomes x_cam ~ R_w @ (x_world - eye) with
R_w = R_s @ A.T and eye = s * A @ C_s + t.

from_anchors: a first similarity from photos whose pose is known in both frames.
fit_to_surface: trimmed point-to-plane ICP of the SfM points onto the city
model's surfaces, started from that. The scale is only observable when the
points lie on faces that look in different directions (a single facade lets the
model slide and swell along the viewing rays), so the anchors stay in the
problem as soft residuals.
"""
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation


def apply(sim, points):
    s, A, t = sim
    return s * np.asarray(points) @ A.T + t


def camera(sim, R_s, C_s):
    """World pose (Rw, eye) of an SfM camera."""
    s, A, t = sim
    return R_s @ A.T, s * A @ C_s + t


def from_anchors(sfm, world):
    """sfm, world: lists of (R, centre) of the same photos in the two frames (one or more).

    The turn is the mean of what each photo says; the scale comes from the
    distances between the centres (1.0 for a single photo: fit it afterwards).
    """
    turns = Rotation.from_matrix([Rw.T @ Rs for (Rs, _), (Rw, _) in zip(sfm, world)])
    A = turns.mean().as_matrix()
    Cs = np.array([c for _, c in sfm], float)
    Cw = np.array([c for _, c in world], float)
    if len(sfm) > 1:
        ds = np.linalg.norm(Cs - Cs.mean(axis=0), axis=1).sum()
        dw = np.linalg.norm(Cw - Cw.mean(axis=0), axis=1).sum()
        s = dw / ds
    else:
        s = 1.0
    t = Cw.mean(axis=0) - s * A @ Cs.mean(axis=0)
    return s, A, t


def sample_surface(tris, spacing=0.5, seed=0):
    """Points spread over the triangles (about one per spacing^2) and their normals."""
    tris = np.asarray(tris, float)
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    area = np.linalg.norm(n, axis=1) / 2
    keep = area > 1e-9
    tris, n, area = tris[keep], n[keep], area[keep]
    n /= (2 * area)[:, None]
    count = np.maximum(1, np.round(area / spacing ** 2).astype(int))
    idx = np.repeat(np.arange(len(tris)), count)
    rng = np.random.default_rng(seed)
    u, v = rng.random(len(idx)), rng.random(len(idx))
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    pts = tris[idx, 0] + u[:, None] * (tris[idx, 1] - tris[idx, 0]) + v[:, None] * (tris[idx, 2] - tris[idx, 0])
    return pts, n[idx]


def _unpack(p, sim0):
    s0, A0, t0 = sim0
    return s0 * np.exp(p[6]), Rotation.from_rotvec(p[:3]).as_matrix() @ A0, t0 + p[3:6]


def fit_to_surface(points, surf_pts, surf_normals, sim0, anchors=(), anchor_sigma=3.0, trim=3.0,
                   rounds=12, tree=None):
    """Refine sim0 so the points lie on the surface. anchors: (C_sfm, eye_world) pairs kept as soft residuals.

    Each round pairs every point with its nearest surface sample, drops pairs
    farther than `trim` metres (points on things the model does not have:
    signs, trees, people), and solves the point-to-plane problem with a robust
    loss. The trim shrinks to `trim` from four times that over the rounds.
    Returns (sim, median distance of the kept points, fraction kept).
    """
    tree = tree or cKDTree(surf_pts)
    points = np.asarray(points, float)
    sim = sim0
    med = frac = None
    for r in range(rounds):
        reach = trim * (1 + 3 * max(0, (rounds - 2 - r)) / max(1, rounds - 2))
        moved = apply(sim, points)
        d, j = tree.query(moved)
        keep = d < reach
        P, Q, N = points[keep], surf_pts[j[keep]], surf_normals[j[keep]]

        def res(p, base=sim):
            cur = _unpack(p, base)
            out = [np.einsum("ij,ij->i", apply(cur, P) - Q, N)]
            for Cs, eye in anchors:
                out.append((apply(cur, Cs) - eye) / anchor_sigma * np.sqrt(len(P) / 50.0))
            return np.concatenate([np.ravel(o) for o in out])

        sol = least_squares(res, np.zeros(7), loss="soft_l1", f_scale=0.5)
        sim = _unpack(sol.x, sim)
        d2 = np.abs(np.einsum("ij,ij->i", apply(sim, P) - Q, N))
        med, frac = float(np.median(d2)), float(keep.mean())
    return sim, med, frac


def support(points, tree, sim, within=1.0):
    """Fraction of the points that land within `within` metres of the surface samples in `tree`.

    This, not the median residual, is what to compare fits by: a fit that
    shrinks the whole cloud onto one wall has a perfect median and is wrong,
    and it is caught by also bounding how far the scale may drift (see
    plausible()).
    """
    d, _ = tree.query(apply(sim, np.asarray(points, float)))
    return float((d < within).mean())


def plausible(sim, start_scale, drift=1.6):
    """False when the refined scale left [start/drift, start*drift]: the cloud collapsed or blew up."""
    return start_scale / drift <= sim[0] <= start_scale * drift
