"""camera_path.py <shots module> <scene tris.npz>
Camera moves as a few keys (eye, target, lens, roll) and the frames between them. With arguments, prints for
every shot how close the camera comes to a building, so that a move through a wall is caught before rendering.

Only numpy: Blender's Python imports this too (path_render.py)."""
import importlib
import sys

import numpy as np


def _vector(key):
    return np.array([*key["eye"], *key["target"], key.get("lens", 24.0), key.get("roll", 0.0)], float)


def sample(keys, frames, ease=True):
    """frames x 8 array (eye 3, target 3, lens, roll): a smooth curve through the keys. A key may carry "t"
    (0..1); without it the keys are evenly spaced. ease starts and ends the move at rest."""
    p = np.array([_vector(k) for k in keys])
    t = np.array([k.get("t", i / max(len(keys) - 1, 1)) for i, k in enumerate(keys)], float)
    if len(keys) == 1:
        return np.repeat(p, frames, axis=0)
    # Hermite spline, the tangent at a key from its two neighbours (one-sided at the ends)
    m = np.empty_like(p)
    m[1:-1] = (p[2:] - p[:-2]) / (t[2:] - t[:-2])[:, None]
    m[0], m[-1] = (p[1] - p[0]) / (t[1] - t[0]), (p[-1] - p[-2]) / (t[-1] - t[-2])
    s = np.linspace(0.0, 1.0, frames)
    if ease:
        s = s * s * (3 - 2 * s)
    i = np.clip(np.searchsorted(t, s, side="right") - 1, 0, len(t) - 2)
    h = (t[i + 1] - t[i])[:, None]
    u = ((s - t[i]) / (t[i + 1] - t[i]))[:, None]
    return ((2 * u ** 3 - 3 * u ** 2 + 1) * p[i] + (u ** 3 - 2 * u ** 2 + u) * h * m[i]
            + (-2 * u ** 3 + 3 * u ** 2) * p[i + 1] + (u ** 3 - u ** 2) * h * m[i + 1])


def look_matrix(eye, target, roll=0.0):
    """4x4 world matrix of a Blender camera (it looks down its -Z, +Y is up) at eye, looking at target,
    turned roll degrees about the line of sight. Straight up or down takes north as up."""
    eye, target = np.asarray(eye, float), np.asarray(target, float)
    f = target - eye
    f /= np.linalg.norm(f)
    r = np.cross(f, [0.0, 0.0, 1.0])
    if np.linalg.norm(r) < 1e-6:
        r = np.cross(f, [0.0, 1.0, 0.0])
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    a = np.radians(roll)
    r, u = np.cos(a) * r + np.sin(a) * u, np.cos(a) * u - np.sin(a) * r
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = r, u, -f, eye
    return m


def circle(centre, radius, z, bearing0, bearing1, n=9):
    """n points on a ring around centre (x, y): compass bearings bearing0..bearing1 in degrees."""
    b = np.radians(np.linspace(bearing0, bearing1, n))
    return [[centre[0] + radius * np.sin(a), centre[1] + radius * np.cos(a), z] for a in b]


def clearance(points, surface):
    """Distance from each point to the nearest surface sample."""
    from scipy.spatial import cKDTree
    return cKDTree(surface).query(points)[0]


def main(argv):
    import sim3
    shots = importlib.import_module(argv[0]).SHOTS
    tris = np.load(argv[1])["tris"].astype(float)
    surf, _ = sim3.sample_surface(tris[np.linalg.norm(tris.mean(axis=1)[:, :2], axis=1) < 400], spacing=1.0)
    for name, shot in shots.items():
        path = sample(shot["keys"], shot["frames"], shot.get("ease", True))
        d = clearance(path[:, :3], surf)
        print(f"{name:16s} {shot['frames']:4d} frames, nearest building {d.min():5.1f} m at frame {int(d.argmin())}"
              f"{'  TOO CLOSE' if d.min() < 2.0 else ''}")


if __name__ == "__main__":
    main(sys.argv[1:])
