"""python -m geo.upright <photo> <fx in pixels at full width>
The pitch and roll of a camera read from the picture alone: buildings stand upright, so the straight lines of their
walls and windows meet at one point of the picture, and where that point lies says how the camera is tilted.

Each segment of the picture and the eye span a plane; its normal n is K^-1 a x K^-1 b. A line of the world that
stands upright lies in its plane, so the world's up u (in camera axes: x right, y down, z forward) has n . u = 0 for
every such segment. u is found as the direction the most segment length agrees on (two segments drawn at a time,
weighted by length, a fixed seed), then fitted to those by least squares. With photo_place.camera's angles,
pitch = asin(u_z) and roll = atan2(u_x, -u_y).

It needs the focal length; heading and place it does not give. Of eight photos (two with a known camera) it read the
known ones within 0.2 degrees, from 35 to 169 segments holding 13 to 56 % of the segment length."""
import sys

import numpy as np

WORK_W = 1300
MIN_LENGTH = 0.04          # of the picture's height: shorter segments point nowhere in particular
AGREE_DEG = 1.0            # a segment agrees with an up that lies this close to its plane
DRAWS = 4000
PITCH, ROLL = (-25.0, 75.0), 12.0     # an up outside these is another family of lines (roof edges, the road)
# Fewer agreeing segments, or a smaller share of the length, than the weakest right reading had (35, 13 %).
MIN_LINES, MIN_SHARE = 20, 0.1
HALF_PITCH, HALF_ROLL = 2.0, 1.5      # the search kept around the reading; photo_place then goes on in half degrees


def _angles(u):
    return float(np.degrees(np.arcsin(np.clip(u[2], -1, 1)))), float(np.degrees(np.arctan2(u[0], -u[1])))


def up_from_lines(segments, f, cx, cy, seed=0):
    """{"pitch", "roll", "lines", "of", "share"} from segments (x0, y0, x1, y1) of a picture whose focal length is f
    pixels and whose middle is (cx, cy); None when no two segments give an up a camera held by hand could have."""
    seg = np.asarray(segments, float).reshape(-1, 4)
    if len(seg) < 2:
        return None
    length = np.hypot(seg[:, 2] - seg[:, 0], seg[:, 3] - seg[:, 1])
    a = np.c_[(seg[:, 0] - cx) / f, (seg[:, 1] - cy) / f, np.ones(len(seg))]
    b = np.c_[(seg[:, 2] - cx) / f, (seg[:, 3] - cy) / f, np.ones(len(seg))]
    n = np.cross(a, b)
    n /= np.linalg.norm(n, axis=1)[:, None]
    near = np.sin(np.radians(AGREE_DEG))
    rng = np.random.default_rng(seed)
    best, agree = 0.0, None
    for _ in range(DRAWS):
        i, j = rng.choice(len(n), 2, replace=False, p=length / length.sum())
        u = np.cross(n[i], n[j])
        k = np.linalg.norm(u)
        if k < 1e-3:
            continue
        u = u / k if u[1] < 0 else -u / k            # the world's up points to the top of the picture
        pitch, roll = _angles(u)
        if not (PITCH[0] <= pitch <= PITCH[1] and abs(roll) <= ROLL):
            continue
        inl = np.abs(n @ u) < near
        if length[inl].sum() > best:
            best, agree = length[inl].sum(), inl
    if agree is None:
        return None
    for _ in range(3):                               # least squares over those that agree
        u = np.linalg.svd(n[agree] * length[agree, None])[2][-1]
        u = u if u[1] < 0 else -u
        agree = np.abs(n @ u) < near
        if agree.sum() < 2:
            return None
    pitch, roll = _angles(u)
    return {"pitch": round(pitch, 1), "roll": round(roll, 1), "lines": int(agree.sum()), "of": len(n),
            "share": round(float(length[agree].sum() / length.sum()), 2)}


def upright(photo_path, fx, work_w=WORK_W, seed=0):
    """up_from_lines of a photo file's line segments; fx is the focal length in pixels at the photo's full width."""
    import cv2
    im = cv2.imread(str(photo_path), cv2.IMREAD_GRAYSCALE)
    if im is None:
        raise SystemExit(f"upright: {photo_path} is not a picture that can be read")
    s = work_w / im.shape[1]
    im = cv2.resize(im, (work_w, round(im.shape[0] * s)))
    h, w = im.shape
    found = cv2.createLineSegmentDetector().detect(im)[0]
    seg = np.zeros((0, 4)) if found is None else found.reshape(-1, 4)
    seg = seg[np.hypot(seg[:, 2] - seg[:, 0], seg[:, 3] - seg[:, 1]) > MIN_LENGTH * h]
    return up_from_lines(seg, fx * s, w / 2, h / 2, seed=seed)


def ranges(reading):
    """photo_place.place's pitch and roll ranges around a reading enough segments agree on; {} (the search as it
    was) when there is no reading or too few agree."""
    if not reading or reading["lines"] < MIN_LINES or reading["share"] < MIN_SHARE:
        return {}
    p, r = round(reading["pitch"] * 2) / 2, round(reading["roll"] * 2) / 2      # the half degrees place searches on
    return {"pitch": f"{p - HALF_PITCH:g}:{p + HALF_PITCH:g}:{HALF_PITCH:g}",
            "roll": f"{r - HALF_ROLL:g}:{r + HALF_ROLL:g}:{HALF_ROLL:g}"}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    print(upright(sys.argv[1], float(sys.argv[2])))
