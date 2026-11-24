"""Whip pan that swaps one rendered scene for another: timing, shutter sampling, the travelling wipe.

The shot is walk -> turn the head (pan) -> push in. Scene A is rendered up to the end of the pan and
scene B from its start; during the pan both are rendered from the same camera and mixed here.

Why a wipe and not a dissolve: the two scenes are photos projected on the same city model with separate
alignment errors, so in the bearings both cover they disagree by several percent of the frame. A dissolve
shows both at once over the whole frame (a double image, then a jump). A wipe whose edge travels with the
blur shows each pixel from one scene only, apart from a soft band of a few degrees.

Why sub-frames are averaged in linear light: a camera sums light, not display codes. Averaged as codes,
lit signs on a night street fade to grey streaks; in linear light they stay bright, as motion blur does.

Pure functions only (no file or renderer access); the caller maps progress to camera poses and images.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

GAMMA = 2.2


def clamp01(t: float) -> float:
    return min(1.0, max(0.0, t))


def ease(t: float) -> float:
    """Cosine ease in and out, clamped to [0, 1]."""
    return 0.5 - 0.5 * math.cos(math.pi * clamp01(t))


def push_out(t: float) -> float:
    """Quadratic ease out: starts at full speed. Right after a camera that has stopped, it reads as a jolt."""
    return 1 - (1 - clamp01(t)) ** 2


def push_inout(t: float, ramp: float = 0.25) -> float:
    """Starts from rest, reaches full speed after `ramp` of the time, then slows linearly to rest.
    Speed is proportional to min(t / ramp, 1) * (1 - t)."""
    t = clamp01(t)

    def up(x):
        return x * x / (2 * ramp) - x ** 3 / (3 * ramp)

    def down(x):
        return x - x * x / 2

    total = up(ramp) + down(1.0) - down(ramp)
    return (up(t) if t <= ramp else up(ramp) + down(t) - down(ramp)) / total


def lerp_angle(a: float, b: float, t: float) -> float:
    """From bearing a to bearing b (degrees) the short way round."""
    return a + ((b - a + 180) % 360 - 180) * t


def turn_direction(a: float, b: float) -> int:
    """+1 when the short way from bearing a to b is clockwise (to the right), -1 when to the left."""
    return 1 if (b - a + 180) % 360 - 180 >= 0 else -1


@dataclass(frozen=True)
class Timing:
    """Seconds. overlap_in starts the pan that long before the walk ends; overlap_out starts the push
    that long before the pan ends. With both 0 the camera stops between the parts."""
    fps: int
    walk: float
    pan: float
    push: float
    overlap_in: float = 0.0
    overlap_out: float = 0.0

    @property
    def pan_start(self) -> float:
        return self.walk - self.overlap_in

    @property
    def pan_end(self) -> float:
        return self.pan_start + self.pan

    @property
    def push_start(self) -> float:
        return self.pan_end - self.overlap_out

    @property
    def total(self) -> float:
        return self.push_start + self.push

    @property
    def frames(self) -> int:
        return round(self.total * self.fps)

    def progress(self, t: float):
        """(walk, pan, push) progress at time t, each a linear 0-1 fraction of its own part."""
        return (clamp01(t / self.walk), clamp01((t - self.pan_start) / self.pan),
                clamp01((t - self.push_start) / self.push))


def schedule(timing: Timing, sub: int):
    """One entry per video frame: {"scene": "a" | "ab" | "b", "times": [seconds, ...]}.
    Frames inside the pan ("ab") carry `sub` sample times that start when the frame starts and fill its
    interval evenly, so averaging the first n of them is a shutter open for n / sub of the frame."""
    eps = 1e-9
    out = []
    for i in range(timing.frames):
        t = i / timing.fps
        if t < timing.pan_start - eps:
            out.append({"scene": "a", "times": [t]})
        elif t < timing.pan_end - eps:
            out.append({"scene": "ab", "times": [t + k / (sub * timing.fps) for k in range(sub)]})
        else:
            out.append({"scene": "b", "times": [t]})
    return out


def shutter_count(sub: int, shutter: float) -> int:
    """How many of a frame's `sub` samples to average for a shutter open `shutter` (0-1) of the frame."""
    return min(sub, max(1, round(sub * shutter)))


def pixel_bearing_offsets(width: int, height: int, fov_v_deg: float, pitch_deg: float) -> np.ndarray:
    """(height, width) degrees: how far right of the camera's bearing each pixel looks, for a level
    (no roll) pinhole camera pitched up by pitch_deg. Looking up, the top rows span more bearing."""
    fy = (height / 2) / math.tan(math.radians(fov_v_deg) / 2)
    tx = (np.arange(width) + 0.5 - width / 2) / fy
    ty = (height / 2 - (np.arange(height) + 0.5)) / fy
    p = math.radians(pitch_deg)
    return np.degrees(np.arctan2(tx[None, :], math.cos(p) - ty[:, None] * math.sin(p))).astype(np.float32)


def wipe_progress(u: float, start: float, end: float) -> float:
    """Wipe progress for pan progress u: 0 before `start`, 1 after `end`, eased between. Keeping the wipe
    inside the fast middle of the pan hides its edge in the blur."""
    return ease((u - start) / (end - start))


def wipe_weight(offsets: np.ndarray, progress: float, direction: int, soft_deg: float) -> np.ndarray:
    """Weight of scene B per pixel. The edge enters from the side the camera turns toward (direction -1 =
    left) and leaves on the other side; it is soft_deg wide. progress 0 is all A, 1 is all B."""
    lead = offsets * direction
    half = float(np.abs(offsets).max()) + soft_deg / 2
    x = np.clip((lead - half * (1 - 2 * progress)) / soft_deg + 0.5, 0.0, 1.0)
    return (x * x * (3 - 2 * x)).astype(np.float32)


def _to_linear(img: np.ndarray, gamma: float) -> np.ndarray:
    return (np.asarray(img, np.float32) / 255.0) ** gamma


def _to_code(lin: np.ndarray, gamma: float) -> np.ndarray:
    return (np.clip(lin, 0.0, 1.0) ** (1.0 / gamma) * 255.0).astype(np.float32)


def blend_linear(a: np.ndarray, b: np.ndarray, weight_b: np.ndarray, gamma: float = GAMMA) -> np.ndarray:
    """Per-pixel mix of two 0-255 images in linear light; weight_b is (h, w)."""
    w = np.asarray(weight_b, np.float32)[..., None]
    return _to_code((1 - w) * _to_linear(a, gamma) + w * _to_linear(b, gamma), gamma)


def mean_linear(images, gamma: float = GAMMA) -> np.ndarray:
    """Mean of 0-255 images in linear light (the exposure of an open shutter)."""
    acc = None
    n = 0
    for img in images:
        lin = _to_linear(img, gamma)
        acc = lin if acc is None else acc + lin
        n += 1
    return _to_code(acc / n, gamma)
