"""Photo walk draft: the people-removed real photos in walking order, slow push-ins, crossfades, BGM.

A stand-in for the 3D walk until the photos are projected in Blender: it checks the order, the pace
and whether the cleaned photos hold up at normal speed with the music.

usage: python3 photo_walk.py <flyover_dir> <version>   (needs ffmpeg; Pillow not required)
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
SHOTS = [
    ("262", 0.5, "crossing, street level"),
    ("138", 0.5, "crossing, the crosswalk ahead"),
    ("305", 0.5, "crossing toward TSUTAYA"),
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


def clip_filter(focus: float) -> str:
    """Cover a 2x canvas, place the 16:9 window at `focus`, then push in slowly toward its centre."""
    n = int(HOLD * FPS)
    cw, ch = 2 * W, 2 * H
    return (f"scale={cw}:{ch}:force_original_aspect_ratio=increase,"
            f"crop={cw}:{ch}:(iw-{cw})/2:min(max(0\\,ih*{focus}-{ch}/2)\\,ih-{ch}),"
            f"zoompan=z='1+{ZOOM}*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:s={W}x{H}:fps={FPS},"
            "setsar=1,format=yuv420p")


def main(fly: Path, version: str) -> None:
    out_dir = fly / "out" / f"photo-walk-v{version}"
    out = out_dir / f"photo-walk-v{version}.mp4"
    if out.exists():
        raise SystemExit(f"{out} exists; pick a new version")
    out_dir.mkdir(parents=True, exist_ok=True)
    args, chains = ["ffmpeg", "-loglevel", "error", "-y"], []
    for k, (i, focus, _) in enumerate(SHOTS):
        args += ["-loop", "1", "-t", str(HOLD), "-i", str(find(fly, i))]
        chains.append(f"[{k}:v]{clip_filter(focus)}[c{k}]")
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
    print(out, f"{total:.1f} s")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
