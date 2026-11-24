"""Camera moves that only a model can do: nobody can stand, fly or wait where these cameras go.
Local east/north/up metres; the crossing's centre is (10, -20) and its ground is at z = 52.8.
Check with: python camera_path.py magic_shots <scene tris.npz>"""
from camera_path import circle

X = (10.0, -20.0)          # the centre of the crossing
G = 52.8                   # ground
QF = (-12.0, 32.0)         # the screen face of QFRONT
EK = (-53.0, -33.0)        # Shibuya Ekimae building


def _k(eye, target, lens, roll=0.0, t=None):
    k = {"eye": list(eye), "target": list(target), "lens": lens, "roll": roll}
    if t is not None:
        k["t"] = t
    return k


def _lookup_spin():
    # lie on the crossing and look up: every facade leans in over the lens while the sky turns
    ring = circle(X, 14, G + 34, 0, 400, n=13)
    return [_k((X[0], X[1], G + 1.2 + 0.25 * i), p, 9.5 + 0.2 * i) for i, p in enumerate(ring)]


def _dolly_zoom():
    # back away from QFRONT while zooming in: the building holds its size and the city behind it swells
    import math
    a = math.radians(160)
    out = []
    for r in (26, 49, 72, 95):
        out.append(_k((QF[0] + r * math.sin(a), QF[1] + r * math.cos(a), G + 1.8 + (r - 26) * 0.05),
                      (QF[0], QF[1], G + 20), 10.0 * r / 26))
    return out


def _skim_climb():
    # skim the zebra crossing towards QFRONT, then ride up its face to the sign
    return [_k((2, -54, G + 1.5), (QF[0], QF[1], G + 10), 15),
            _k((8, -24, G + 1.5), (QF[0], QF[1], G + 13), 15),
            _k((5, 2, G + 6), (QF[0], QF[1], G + 20), 14),
            _k((3, 8, G + 24), (QF[0], QF[1], G + 28), 13),
            _k((5, 3, G + 42), (QF[0], QF[1], G + 40), 13)]


def _topdown_spin():
    # fall towards the stripes, turning
    return [_k((X[0], X[1], G + 95), (X[0], X[1], G), 22, roll=0),
            _k((X[0], X[1], G + 45), (X[0], X[1], G), 20, roll=100),
            _k((X[0], X[1], G + 14), (X[0], X[1], G), 16, roll=170)]


def _inception_roll():
    # fly west out of the crossing into the street while the world turns over: the stripes become the sky
    far = (-160, 8, G + 22)
    return [_k((42, 2, G + 3), far, 13, roll=0),
            _k((12, 2, G + 5), far, 13, roll=30),
            _k((-18, 3, G + 7), far, 13, roll=150),
            _k((-48, 3, G + 8), far, 13, roll=180)]


def _time_arc():
    # swing around the Ekimae building; the day layer gives way to the night layer on the way (time_blend.py)
    ring = circle(EK, 70, G + 25, 45, 128, n=6)
    return [_k(p, (EK[0], EK[1], G + 17), 24) for p in ring]


SHOTS = {
    "lookup_spin": {"frames": 300, "ease": False, "keys": _lookup_spin()},
    "dolly_zoom": {"frames": 150, "keys": _dolly_zoom()},
    "skim_climb": {"frames": 240, "keys": _skim_climb()},
    "topdown_spin": {"frames": 180, "keys": _topdown_spin()},
    "inception_roll": {"frames": 180, "keys": _inception_roll()},
    "time_arc": {"frames": 180, "keys": _time_arc()},
}
