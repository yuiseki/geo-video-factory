"""Camera moves that only a model can do: nobody can stand, fly or wait where these cameras go.
Local east/north/up metres; the crossing's centre is (10, -20) and its ground is at z = 52.8.
Check with: python world_camera.py magic_shots <scene tris.npz>"""
import math

from world_camera import circle

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


def maplibre_eye(centre_xy, ground, zoom, pitch, bearing, fov_v=36.87, height_px=720, lat=35.6595):
    """Where a MapLibre camera (centre on the ground, zoom, pitch, bearing, vertical fov) stands, in local
    metres, and the Blender lens (36 mm sensor across a 16:9 frame) with the same field of view."""
    import math
    m_per_px = 2 * math.pi * 6378137 * math.cos(math.radians(lat)) / (512 * 2 ** zoom)
    d = 0.5 * height_px / math.tan(math.radians(fov_v) / 2) * m_per_px
    h, v = d * math.sin(math.radians(pitch)), d * math.cos(math.radians(pitch))
    b = math.radians(bearing)
    eye = (centre_xy[0] - h * math.sin(b), centre_xy[1] - h * math.cos(b), ground + v)
    fov_h = 2 * math.atan(math.tan(math.radians(fov_v) / 2) * 16 / 9)
    return eye, 18 / math.tan(fov_h / 2)


HAND = {"zoom": 18.7, "pitch": 55, "bearing": -24}     # the last camera of the PLATEAU++ descent (map)


def _handover_dive():
    # from the map's last camera down to the zebra crossing, then skim towards QFRONT
    eye, lens = maplibre_eye(X, G, **HAND)
    return [_k(eye, (X[0], X[1], G), lens, t=0.0),
            _k((44, -96, G + 58), (X[0] - 6, X[1] + 8, G + 4), lens, t=0.35),
            _k((26, -56, G + 32), (QF[0], QF[1], G + 6), 22, t=0.6),
            _k((16, -36, G + 6), (QF[0], QF[1], G + 10), 18, t=0.82),
            _k((10, -22, G + 1.6), (QF[0], QF[1], G + 14), 15, t=1.0)]


SHOTS["handover_dive"] = {"frames": 240, "keys": _handover_dive()}


def _burst_out():
    # out of the inside of QFRONT through its screen wall, over the crossing, turning towards the Ekimae building
    d = (0.407, -0.914)                       # the screen face looks to bearing 156
    at = lambda s, z: (QF[0] + s * d[0], QF[1] + s * d[1], G + z)
    return [_k(at(-2.5, 20), at(40, 12), 16, t=0.0),
            _k(at(14, 15), at(60, 6), 16, t=0.3),
            _k((12, -14, G + 6), (EK[0], EK[1], G + 8), 18, t=0.7),
            _k((22, -30, G + 2.0), (EK[0], EK[1], G + 14), 18, t=1.0)]


SHOTS["burst_out"] = {"frames": 210, "keys": _burst_out()}


ST = (241.0, -254.0)                          # Shibuya Stream (OSM way 521438304), 180 m tall


def _stream_to_qfront():
    # out of the wall of Shibuya Stream, where the map dive went in, north-west over the station side, down to
    # the front of QFRONT
    look = (QF[0], QF[1], G + 20)
    return [_k((212, -230, G + 37), look, 18, t=0.0),
            _k((150, -185, G + 37), look, 18, t=0.25),
            _k((80, -120, G + 30), look, 18, t=0.5),
            _k((20, -46, G + 14), look, 16, t=0.78),
            _k((2, 2, G + 2.0), (QF[0], QF[1], G + 16), 15, t=1.0)]


SHOTS["stream_to_qfront"] = {"frames": 270, "keys": _stream_to_qfront()}


def _orbit(centre_xyz, radius, height, a0, a1, lens):
    # orbit_render.py: camera on the ring at ground + height, looking at the centre point
    ring = circle(centre_xyz[:2], radius, G - 0.2 + height, a0, a1, n=25)
    return [_k(p, centre_xyz, lens) for p in ring]


# the moves of the v5 clips (orbit_render.py), so that they can be drawn from any saved scene
SHOTS["pan"] = {"frames": 360, "ease": False, "keys": [
    _k((10, -20, G - 0.2 + 2.2), p, 18) for p in circle((10, -20), 100, G - 0.2 + 18, 180, 540, n=49)]}
SHOTS["arc_qfront"] = {"frames": 180, "ease": False, "keys": _orbit((-12, 43, 75), 85, 30, 130, 210, 24)}
SHOTS["arc_ekimae"] = {"frames": 180, "ease": False, "keys": _orbit((-53, -33, 70), 70, 25, 45, 140, 24)}


def _stream_dive_qfront():
    # the PLATEAU++ descent ends falling straight down onto the Stream tower, north up: carry on falling inside
    # it the same way, level out at 70 m, turn to QFRONT and come out of the tower's west wall. The straight
    # line to QFRONT runs through Shibuya Scramble Square (230 m, centre about (156, -126)), so the way out
    # passes south of it, between it and Sakura Stage, and turns to QFRONT over the station.
    # Until the camera is out, the target is 100 m along the line of sight, so the spline turns the view
    # instead of swinging a far target around.
    tower, top = (270.0, -272.0), 160
    face = (QF[0], QF[1], G + 22)

    def look(eye, east, north, up):
        m = math.sqrt(east * east + north * north + up * up)
        return (eye[0] + 100 * east / m, eye[1] + 100 * north / m, eye[2] + 100 * up / m)

    def toward(eye):
        return look(eye, face[0] - eye[0], face[1] - eye[1], face[2] - eye[2])

    e0, e1, e2 = (*tower, G + top), (*tower, G + 85), (*tower, G + 74)
    e3 = (262.0, -268.0, G + 71)
    e4 = (205.0, -235.0, G + 70)
    e5 = (140.0, -205.0, G + 68)
    return [
        _k(e0, look(e0, 0, 0.02, -1), 18, t=0.0),
        _k(e1, look(e1, 0, 0.25, -1), 18, t=0.20),
        _k(e2, look(e2, 0, 1, -0.35), 18, t=0.30),
        _k(e3, toward(e3), 18, t=0.38),
        _k(e4, toward(e4), 18, t=0.50),
        _k(e5, toward(e5), 18, t=0.62),
        _k((60.0, -140.0, G + 55), face, 20, t=0.76),
        _k((22.0, -50.0, G + 25), face, 22, t=0.90),
        _k((2, 2, G + 2), (QF[0], QF[1], G + 12), 22, t=1.0)]


SHOTS["stream_dive_qfront"] = {"frames": 300, "ease": False, "keys": _stream_dive_qfront()}
