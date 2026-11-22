"""Photo walk draft: the people-removed real photos in walking order, slow push-ins, crossfades, BGM.

A stand-in for the 3D walk until the photos are projected in Blender: it checks the order, the pace
and whether the cleaned photos hold up at normal speed with the music.

usage: python3 photo_walk.py <flyover_dir> <version>   (needs ffmpeg and Pillow)
  -> <flyover_dir>/out/photo-walk-v<version>/photo-walk-v<version>.mp4  (1280x720, 24 fps, -14 LUFS)
Never overwrites: refuses if the output exists.
"""
import subprocess
import sys
from pathlib import Path

W, H, FPS = 1280, 720, 24
HOLD, FADE = 5.5, 1.5  # seconds on screen per photo, crossfade length
ZOOM = 0.08  # push-in over HOLD: a slow step forward
# (id or folder/id, vertical focus 0-1 for the 16:9 window, note). Walking order: the crossing at street
# level, looking up in the middle, into Center-gai, out by Dogenzaka, fade out under the trees.
# v0.2.0: Center-gai added; 288 dropped (its car light trails contradict the empty city).
# v0.2.1: the karaoke shop without the people inside (centergai_v2/139).
# v0.3.0: opens standing at the corner (220); the Tokyu Toyoko view (147) in the crossing.
# v0.3.1: push-ins drawn with Pillow at sub-pixel positions (zoompan juddered).
# v0.4.0: an establishing shot from above (258) before the first-person walk. An alternative to v0.3.1,
#         not a replacement: whether to break the first person once is an editing choice.
# v0.4.1: 258 without the parked cars left in its upper left (crossing_night_v8).
SHOTS = [
    ("crossing_night_v8/258", 0.5, "the empty crossing from above, before stepping in"),
    ("buildings_night_v2/220", 0.5, "standing at the corner of the crossing"),
    ("262", 0.5, "crossing, street level"),
    ("138", 0.5, "crossing, the crosswalk ahead"),
    ("305", 0.5, "crossing toward TSUTAYA"),
    ("buildings_night_v1/147", 0.55, "crossing toward the Tokyu Toyoko store"),
    ("212", 0.5, "crossing, wide"),
    ("199", 0.62, "middle of the crossing, looking up"),
    ("278", 0.5, "screens around the crossing"),
    ("068", 0.5, "screens, low angle"),
    ("308", 0.5, "looking straight up"),
    ("centergai_v2/132", 0.55, "into Center-gai: shutters and rubbish"),
    ("centergai_v1/129", 0.5, "deep in Center-gai"),
    ("centergai_v2/139", 0.45, "karaoke shop from above"),
    ("118", 0.55, "back out by H&M"),
    ("117", 0.55, "corner on Dogenzaka"),
    ("267", 0.6, "karaoke street"),
    ("190", 0.5, "Reikyo on Dogenzaka"),
    ("044", 0.5, "tree-lined slope, fade out"),
]
# current version of each photo (later folders first); see HANDOVER-2026-11-22.md
DIRS = ["crossing_night_v7b", "crossing_night_v7", "night_v2", "crossing_night_v6", "night_v1"]
GRADE = ("rgbashift=rh=-1:bh=1,colorbalance=rs=0.04:bs=0.08:rm=0.02:bm=0.05,"
         "vignette=PI/5,noise=alls=4:allf=t")
BGM = "assets/bgm/vaporwave_mallsoft.wav"


def find(fly: Path, i: str) -> Path:
    """`id` searches DIRS in order; `folder/id` looks only in that folder (ids repeat across photo sets)."""
    if "/" in i:
        d, i = i.split("/", 1)
        hits = sorted((fly / "out/people_removal_cc0" / d).glob(f"{i}*_nopeople.png"))
        if hits:
            return hits[0]
        raise SystemExit(f"no people-removed photo for {d}/{i}")
    for d in DIRS:
        hits = sorted((fly / "out/people_removal_cc0" / d).glob(f"{i}*_nopeople.png"))
        if hits:
            return hits[0]
    raise SystemExit(f"no people-removed photo for {i}")


def push_in(photo: Path, focus: float, out: Path) -> None:
    """Write one push-in clip. Frames are drawn with Pillow at sub-pixel positions: ffmpeg's zoompan crops
    at whole pixels and the slow zoom judders (11/23: mean second temporal difference 6.6 with zoompan on a
    2x canvas, 3.1 on 4x, 1.2 here). The photo is first shrunk to the window (Lanczos), so the affine
    transform only ever enlarges by up to ZOOM and does not alias."""
    from PIL import Image
    n = int(HOLD * FPS)
    src = Image.open(photo).convert("RGB")
    sw, sh = src.size
    ww, wh = (sh * W / H, sh) if sw / sh > W / H else (sw, sw * H / W)  # 16:9 window covering the photo
    k = W / ww
    src = src.resize((max(W, round(sw * k)), max(H, round(sh * k))), Image.LANCZOS)
    sw, sh, ww, wh = src.size[0], src.size[1], ww * k, wh * k
    x0, y0 = (sw - ww) / 2, min(max(0.0, sh * focus - wh / 2), sh - wh)
    enc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "12",
                            "-preset", "fast", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    for i in range(n):
        z = 1 + ZOOM * i / n
        cw, ch = ww / z, wh / z
        s = cw / W
        frame = src.transform((W, H), Image.AFFINE, (s, 0, x0 + (ww - cw) / 2, 0, s, y0 + (wh - ch) / 2),
                              Image.BICUBIC)
        enc.stdin.write(frame.tobytes())
    enc.stdin.close()
    if enc.wait() != 0:
        raise SystemExit(f"encoding {out} failed")


def main(fly: Path, version: str) -> None:
    out_dir = fly / "out" / f"photo-walk-v{version}"
    out = out_dir / f"photo-walk-v{version}.mp4"
    if out.exists():
        raise SystemExit(f"{out} exists; pick a new version")
    out_dir.mkdir(parents=True, exist_ok=True)
    clips = out_dir / "clips"
    clips.mkdir(exist_ok=True)
    args, chains = ["ffmpeg", "-loglevel", "error", "-y"], []
    for k, (i, focus, _) in enumerate(SHOTS):
        clip = clips / f"{k:02d}.mp4"
        push_in(find(fly, i), focus, clip)
        args += ["-i", str(clip)]
        chains.append(f"[{k}:v]setsar=1,format=yuv420p[c{k}]")
    step = HOLD - FADE
    total = step * (len(SHOTS) - 1) + HOLD
    prev = "c0"
    for k in range(1, len(SHOTS)):
        chains.append(f"[{prev}][c{k}]xfade=transition=fade:duration={FADE}:offset={step * k:.2f}[x{k}]")
        prev = f"x{k}"
    chains.append(f"[{prev}]{GRADE},fade=t=in:d=1.5,fade=t=out:st={total - 3:.2f}:d=3,format=yuv420p[v]")
    a = len(SHOTS)
    args += ["-stream_loop", "-1", "-i", str(fly / BGM)]
    chains.append(f"[{a}:a]atrim=0:{total:.2f},afade=t=in:d=2,afade=t=out:st={total - 3.5:.2f}:d=3.5,"
                  "loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    args += ["-filter_complex", ";".join(chains), "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}",
             "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-c:a", "aac", "-b:a", "192k",
             "-ar", "48000", str(out)]
    subprocess.run(args, check=True)
    (out_dir / "shots.txt").write_text("".join(f"{i}\t{find(fly, i).relative_to(fly)}\t{note}\n"
                                               for i, _, note in SHOTS))
    (out_dir / "credits.txt").write_text(credits_text([find(fly, i).relative_to(fly) for i, _, _ in SHOTS]))
    print(out, f"{total:.1f} s")


def credits_text(used) -> str:
    """Description-box credits for the photos used, in order, from credits_people_removed.json."""
    import json
    doc = json.loads((Path(__file__).parent / "credits_people_removed.json").read_text())
    rows = {r["output"]: r for k, v in doc.items() if isinstance(v, list) for r in v if "output" in r}
    lines = ["写真 (人と車を SAM 3.1 のマスクと LaMa の塗りで消し、色を調整):"]
    for u in used:
        r = rows.get(f"flyover/{u}")
        if r is None:
            raise SystemExit(f"no credit for {u}")
        who = r["creator"] or "作者名なし"
        lines.append(f"- {r['title'].removeprefix('File:')} / {who} / {r['license']} / {r['url']}")
    lines += ["", "BGM: ローカル合成 (flyover/scripts/generate_vaporwave_bgm.py)",
              "人の検出: SAM 3.1 / 塗り: LaMa (Apache-2.0)", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
