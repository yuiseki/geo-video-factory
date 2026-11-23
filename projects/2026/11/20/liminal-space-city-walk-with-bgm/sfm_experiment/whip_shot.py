"""whip_shot.py plan <cams.json> <work_dir>        write frames_a.json / frames_b.json (camera per render)
   whip_shot.py splice <work_dir> <out.mp4>         average sub-frames, mix the two scenes, encode

The "magic" shot: walk from photo A's pose toward Q-FRONT (scene A = photo A projected), whip-pan left,
and during the pan swap to scene B (photo B projected) so the pan ends exactly at photo B's pose, where
B's projection is the photo itself whatever the alignment error; then push in a little.

--swap=dissolve (default, the recipe up to v0.6.2): walk 6 s, pan 1 s (5 sub-frames per frame, averaged),
push 3 s at 24 fps. Scene A renders the walk and the first 60 % of the pan, scene B the last 60 % of the
pan and the push; the overlap is cross-faded over the whole frame.

--swap=wipe (v0.6.3 on): both scenes render the whole pan from the same cameras, and scene B wipes in
from the side the camera turns toward (packages/pipeline/whip_pan.py says why). plan also writes plan.json.
  plan:   --sub=16 (samples per pan frame)  --pan=1.0 (s)  --render=<key> (the render_key given to
          blender_projection.py; its fov places the wipe; default --a)
          --overlap-in=0 (s: the pan starts this long before the walk ends)
          --overlap-out=0 (s: the push starts this long before the pan ends)  --push-ease=out|inout
          --land=bearing[,pitch] (deg: where the pan ends looking, instead of along photo B's axis)
          --eye-z=<z> (m: the landing eye height in the model's frame, instead of photo B's)
  splice: --shutter=0.5 (part of each frame the shutter is open)  --soft=10 (deg, width of the wipe's edge)
          --wipe=0.15,0.85 (the part of the pan the wipe takes)
Common: --a= --b= (photo keys)  --start=x,y | --start-back=m  --walk= --push= (s)
"""
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "packages" / "pipeline"))
import whip_pan as wp  # noqa: E402

FPS, WALK, PAN, PUSH, SUB = 24, 6.0, 1.0, 3.0, 5
AIM = (-15.0, 30.0)          # Q-FRONT's corner seen from the crossing (ENU m)
WALK_END_BACK = 6.0          # the walk stops this far from B's eye (toward Q-FRONT), the pan covers the rest
PUSH_M = 6.0


def ease(t):
    return 0.5 - 0.5 * math.cos(math.pi * min(1.0, max(0.0, t)))


def bearing_to(p, q):
    return math.degrees(math.atan2(q[0] - p[0], q[1] - p[1])) % 360


def lerp_angle(a, b, t):
    return a + ((b - a + 180) % 360 - 180) * t


def pose(c):
    f = np.array(c["Rw"]).T[:, 2]
    return np.array(c["eye"]), math.degrees(math.atan2(f[0], f[1])) % 360, math.degrees(math.asin(f[2]))


def plan(cams_path, work):
    cams = json.load(open(cams_path))
    ka, kb = [k for k in cams if A_KEY in k][0], [k for k in cams if B_KEY in k][0]
    ea, ba, pa = pose(cams[ka])
    eb, bb, pb = pose(cams[kb])
    back = np.array([math.sin(math.radians(bb)), math.cos(math.radians(bb)), 0.0])   # B's forward
    toward_q = math.radians(bearing_to(eb, AIM))
    to_q = np.array([math.sin(toward_q), math.cos(toward_q), 0.0])
    # the walk ends WALK_END_BACK m from B's eye toward Q-FRONT; the pan slides the rest of the way
    walk_end = eb + WALK_END_BACK * to_q
    if START_BACK:
        # line mode: start START_BACK m behind B's eye on the line from Q-FRONT through it (the station
        # side), walk straight facing Q-FRONT, and turn on the spot at B's eye
        ea = eb - START_BACK * to_q
        ba, pa = bearing_to(ea, AIM), pb
        walk_end = eb.copy()
    if START is not None:
        # given start (x, y): walk straight to B's eye facing Q-FRONT, turn on the spot at B's eye
        ea = np.array([START[0], START[1], eb[2]])
        ba, pa = bearing_to(ea, AIM), pb
        walk_end = eb.copy()
    A, B = [], []
    n = int(WALK * FPS)
    for i in range(n):
        t = ease(i / (n - 1))
        p = ea + t * (walk_end - ea)
        aim_b = bearing_to(p, AIM)
        b = lerp_angle(ba, aim_b, ease(i / (0.3 * n)))      # settle onto Q-FRONT in the first ~2 s
        A.append(dict(x=p[0], y=p[1], z=ea[2] + t * (eb[2] - ea[2]), bearing=b % 360,
                      pitch=pa + (pb - pa) * t, out=str(work / "a" / f"{i:05d}.png")))
    b_end_walk = A[-1]["bearing"]
    m = int(PAN * FPS) * SUB
    for j in range(m):
        t = ease(j / (m - 1))
        p = walk_end + t * (eb - walk_end)
        fr = dict(x=p[0], y=p[1], z=eb[2], bearing=lerp_angle(b_end_walk, bb, t) % 360, pitch=pb,
                  idx=j)
        if j / (m - 1) <= 0.6:
            A.append(dict(fr, out=str(work / "pa" / f"{j:05d}.png")))
        if j / (m - 1) >= 0.4:
            B.append(dict(fr, out=str(work / "pb" / f"{j:05d}.png")))
    k = int(PUSH * FPS)
    for i in range(k):
        t = 1 - (1 - i / (k - 1)) ** 2     # ease out
        p = eb + t * PUSH_M * back
        B.append(dict(x=p[0], y=p[1], z=eb[2], bearing=bb, pitch=pb - 2 * t, out=str(work / "b" / f"{i:05d}.png")))
    for d in ("a", "pa", "pb", "b"):
        (work / d).mkdir(parents=True, exist_ok=True)
    json.dump(A, open(work / "frames_a.json", "w"))
    json.dump(B, open(work / "frames_b.json", "w"))
    print(f"A {ka} eye {ea.round(1)} bearing {ba:.0f}; B {kb} eye {eb.round(1)} bearing {bb:.0f}; "
          f"walk end {walk_end.round(1)}; renders A {len(A)} B {len(B)}")


def splice(work, out):
    from PIL import Image
    frames = sorted((work / "a").glob("*.png"))
    seq = [np.asarray(Image.open(f).convert("RGB"), np.float32) for f in frames]
    m = int(PAN * FPS) * SUB
    for f in range(int(PAN * FPS)):
        acc = []
        for j in range(f * SUB, (f + 1) * SUB):
            u = j / (m - 1)
            fa, fb = work / "pa" / f"{j:05d}.png", work / "pb" / f"{j:05d}.png"
            w = min(1.0, max(0.0, (u - 0.4) / 0.2))          # 0 -> 1 across the overlap
            if w <= 0:
                img = np.asarray(Image.open(fa).convert("RGB"), np.float32)
            elif w >= 1:
                img = np.asarray(Image.open(fb).convert("RGB"), np.float32)
            else:
                img = (1 - w) * np.asarray(Image.open(fa).convert("RGB"), np.float32) + \
                    w * np.asarray(Image.open(fb).convert("RGB"), np.float32)
            acc.append(img)
        seq.append(np.mean(acc, 0))
    seq += [np.asarray(Image.open(f).convert("RGB"), np.float32) for f in sorted((work / "b").glob("*.png"))]
    h, w_ = seq[0].shape[:2]
    enc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                            f"{w_}x{h}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "16",
                            "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    for img in seq:
        enc.stdin.write(np.clip(img, 0, 255).astype(np.uint8).tobytes())
    enc.stdin.close()
    enc.wait()
    print("frames", len(seq), "->", out)


def plan_wipe(cams_path, work):
    """Time-based plan: every video frame is a time, pan frames carry SUB sample times, and both scenes
    render the whole pan. Position = walk + slide to B's eye during the pan + push, each eased on its own
    clock, so the parts may overlap (--overlap-in / --overlap-out) without a stop between them."""
    cams = json.load(open(cams_path))
    ka, kb = [k for k in cams if A_KEY in k][0], [k for k in cams if B_KEY in k][0]
    ea, ba, pa = pose(cams[ka])
    eb, bb, pb = pose(cams[kb])
    if LAND:
        # a view from the projector's eye is the photo whichever way the camera looks, so the landing may
        # look at any part of a wide photo (013 covers 103 deg; 109 is at its left)
        bb, pb = LAND[0], (LAND[1] if len(LAND) > 1 else pb)
    if EYE_Z is not None:
        eb = np.array([eb[0], eb[1], EYE_Z])
    back = np.array([math.sin(math.radians(bb)), math.cos(math.radians(bb)), 0.0])   # B's forward
    toward_q = math.radians(bearing_to(eb, AIM))
    to_q = np.array([math.sin(toward_q), math.cos(toward_q), 0.0])
    walk_end = eb + WALK_END_BACK * to_q
    if START_BACK:
        ea = eb - START_BACK * to_q
        ba, pa = bearing_to(ea, AIM), pb
        walk_end = eb.copy()
    if START is not None:
        ea = np.array([START[0], START[1], eb[2]])
        ba, pa = bearing_to(ea, AIM), pb
        walk_end = eb.copy()
    timing = wp.Timing(FPS, WALK, PAN, PUSH, OVERLAP_IN, OVERLAP_OUT)
    push_ease = wp.push_inout if PUSH_EASE == "inout" else wp.push_out

    def camera(t):
        w, u, x = timing.progress(t)
        p = ea + ease(w) * (walk_end - ea) + ease(u) * (eb - walk_end) + push_ease(x) * PUSH_M * back
        b = lerp_angle(ba, bearing_to(p, AIM), ease(t / (0.3 * WALK)))     # settle onto Q-FRONT early
        b = lerp_angle(b, bb, ease(u))
        return dict(x=p[0], y=p[1], z=p[2], bearing=b % 360, pitch=pa + (pb - pa) * ease(w) - 2 * push_ease(x)), u

    A, B, frames = [], [], []
    for i, fr in enumerate(wp.schedule(timing, SUB)):
        entry = {"scene": fr["scene"], "a": [], "b": [], "u": [], "pitch": []}
        for k, t in enumerate(fr["times"]):
            cam, u = camera(t)
            name = f"{i:05d}.png" if fr["scene"] != "ab" else f"{i:05d}_{k:02d}.png"
            entry["u"].append(u)
            entry["pitch"].append(cam["pitch"])
            if "a" in fr["scene"]:
                out = str(work / ("a" if fr["scene"] == "a" else "pa") / name)
                A.append(dict(cam, out=out))
                entry["a"].append(out)
            if "b" in fr["scene"]:
                out = str(work / ("b" if fr["scene"] == "b" else "pb") / name)
                B.append(dict(cam, out=out))
                entry["b"].append(out)
        frames.append(entry)
    for d in ("a", "pa", "pb", "b"):
        (work / d).mkdir(parents=True, exist_ok=True)
    kr = [k for k in cams if RENDER_KEY in k][0]
    b0 = camera(timing.pan_start)[0]["bearing"]
    json.dump(A, open(work / "frames_a.json", "w"))
    json.dump(B, open(work / "frames_b.json", "w"))
    json.dump({"swap": "wipe", "fps": FPS, "sub": SUB, "fov_v": cams[kr]["fov_v"],
               "direction": wp.turn_direction(b0, bb), "frames": frames}, open(work / "plan.json", "w"))
    print(f"A {ka} eye {ea.round(1)} bearing {ba:.0f}; B {kb} eye {eb.round(1)} bearing {bb:.0f}; "
          f"pan {b0:.1f} -> {bb:.1f} at {timing.pan_start:.2f}-{timing.pan_end:.2f} s, push from "
          f"{timing.push_start:.2f} s; {timing.frames} frames; renders A {len(A)} B {len(B)}")


def splice_wipe(work, out):
    """Pan frames: per sample, scene B wipes over scene A; the samples inside the shutter are averaged in
    linear light. Other frames pass through. Frames go straight to ffmpeg."""
    from PIL import Image
    meta = json.load(open(work / "plan.json"))
    n = wp.shutter_count(meta["sub"], SHUTTER)

    def load(path):
        return np.asarray(Image.open(path).convert("RGB"), np.float32)

    enc = None
    offsets = {}
    for fr in meta["frames"]:
        if fr["scene"] != "ab":
            img = load(fr[fr["scene"]][0])
        else:
            acc = []
            for k in range(n):
                a, b = load(fr["a"][k]), load(fr["b"][k])
                key = round(fr["pitch"][k], 2)
                if key not in offsets:
                    offsets[key] = wp.pixel_bearing_offsets(a.shape[1], a.shape[0], meta["fov_v"], key)
                weight = wp.wipe_weight(offsets[key], wp.wipe_progress(fr["u"][k], *WIPE), meta["direction"], SOFT)
                acc.append(wp.blend_linear(a, b, weight))
            img = wp.mean_linear(acc)
        if enc is None:
            h, w_ = img.shape[:2]
            enc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                    "-s", f"{w_}x{h}", "-r", str(meta["fps"]), "-i", "-", "-c:v", "libx264",
                                    "-crf", "16", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
        enc.stdin.write(np.clip(img + 0.5, 0, 255).astype(np.uint8).tobytes())
    enc.stdin.close()
    enc.wait()
    print("frames", len(meta["frames"]), "shutter samples", n, "->", out)


START_BACK = 0.0
START = None
A_KEY, B_KEY = "018", "005"
SWAP, RENDER_KEY, PUSH_EASE = "dissolve", None, "out"
OVERLAP_IN = OVERLAP_OUT = 0.0
SHUTTER, SOFT, WIPE = 0.5, 10.0, (0.15, 0.85)
LAND, EYE_Z = None, None

if __name__ == "__main__":
    opts = dict(a[2:].split("=", 1) for a in sys.argv if a.startswith("--") and "=" in a)
    A_KEY, B_KEY = opts.get("a", A_KEY), opts.get("b", B_KEY)
    if "start" in opts:
        START = tuple(float(v) for v in opts["start"].split(","))
    START_BACK = float(opts.get("start-back", 0))      # e.g. 30: line mode from the station side
    WALK = float(opts.get("walk", WALK))
    PUSH = float(opts.get("push", PUSH))
    SWAP = opts.get("swap", SWAP)
    if SWAP == "wipe":
        PAN, SUB = float(opts.get("pan", PAN)), int(opts.get("sub", 16))
        RENDER_KEY, PUSH_EASE = opts.get("render", A_KEY), opts.get("push-ease", PUSH_EASE)
        OVERLAP_IN, OVERLAP_OUT = float(opts.get("overlap-in", 0)), float(opts.get("overlap-out", 0))
        SHUTTER, SOFT = float(opts.get("shutter", SHUTTER)), float(opts.get("soft", SOFT))
        WIPE = tuple(float(v) for v in opts.get("wipe", "0.15,0.85").split(","))
        LAND = [float(v) for v in opts["land"].split(",")] if "land" in opts else None
        EYE_Z = float(opts["eye-z"]) if "eye-z" in opts else None
    work = Path(sys.argv[2])
    if sys.argv[1] == "plan":
        (plan_wipe if SWAP == "wipe" else plan)(sys.argv[2], Path(sys.argv[3]))
    elif (work / "plan.json").exists():
        splice_wipe(work, Path(sys.argv[3]))
    else:
        splice(work, Path(sys.argv[3]))
