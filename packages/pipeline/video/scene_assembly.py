"""Puts rendered scenes together into one video: a title card, every scene with its place name (fades in and
out) and a small credit line (stays), crossfades between them, an end card with every credit, and ambient music
(ambient_bgm.py, turning to the night chords where the first scene marked "night" begins), mastered to
-14 LUFS / -1.5 dBTP in two passes (ffmpeg_ops.normalize_loudness).

    python scene_assembly.py <plan.json> <scenes root> <work dir> <out.mp4> [--crf=18]

The plan is a JSON object:
    size [w, h], fps, crossfade (seconds)
    title    {ja, en, seconds}
    scenes   [{name, ja, en, credit, night?, frames_dir?}]
    credits  {seconds, heading, lines}     see title_cards.end_card for the lines
A scene is the frames <scenes root>/<name>/<frames dir>/%04d.png (frames dir defaults to f_mac). The cards are
drawn by title_cards.py in Noto CJK (FONT_SERIF, FONT_SANS override the paths). Nothing is overwritten: the work
dir and the output must be new. Run it under the host's resource limits; ffmpeg inherits them.

The timeline arithmetic and the ffmpeg command lines are functions that return values, so that they can be
checked without encoding anything; assemble() is the only function that runs them.
"""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
if str(_Path(__file__).resolve().parents[1]) not in _sys.path:
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import argparse
import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from PIL import Image

from narration import ambient_bgm
from video import ffmpeg_ops
from video import title_cards

FFMPEG = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin"]
# The clips are intermediates that get encoded once more when they are joined: near-lossless, so that the
# final --crf is the only visible compression.
CLIP_CODEC = ["-c:v", "libx264", "-crf", "12", "-preset", "medium"]
DEFAULT_FRAMES_DIR = "f_mac"
TITLE_FADE_IN = 1.2
CREDITS_FADE_OUT = 2.0
# The overlays wait until the crossfade into the scene is over, then take a second to appear.
OVERLAY_IN_AT, OVERLAY_IN = 1.2, 1.0
# The place name leaves after 7 s, or 3 s before the end of a shorter scene; the credit line stays.
LABEL_OUT_AT, LABEL_OUT_BEFORE_END, LABEL_OUT = 7.0, 3, 1.2


def clip_starts(durations: Sequence[float], crossfade: float) -> list[float]:
    """When each clip begins in the finished video: every clip overlaps the one before by one crossfade."""
    return [sum(durations[:k]) - k * crossfade for k in range(len(durations))]


def total_length(durations: Sequence[float], crossfade: float) -> float:
    return sum(durations) - (len(durations) - 1) * crossfade


def xfade_offsets(durations: Sequence[float], crossfade: float) -> list[float]:
    """The offset of each xfade: where clip k (k >= 1) begins, measured on the output of the joins before it."""
    offsets, offset = [], 0.0
    for k in range(1, len(durations)):
        offset += durations[k - 1] - crossfade
        offsets.append(offset)
    return offsets


def night_start(scenes: Sequence[Mapping[str, Any]], scene_starts: Sequence[float]) -> float | None:
    """The start of the first scene marked "night", or None when the whole video is day."""
    if len(scenes) != len(scene_starts):
        raise ValueError(f"{len(scenes)} scenes but {len(scene_starts)} start times")
    return next((start for scene, start in zip(scenes, scene_starts) if scene.get("night")), None)


def still_command(png: Path, seconds: float, out: Path, *, fps: float,
                  fade_in: float = 0.0, fade_out: float = 0.0) -> list[str]:
    """One image held for its seconds, optionally fading in from black and out to black."""
    if fade_in > seconds or fade_out > seconds:
        raise ValueError(f"a fade of {max(fade_in, fade_out)} s does not fit a clip of {seconds} s")
    vf = [f"fps={fps}", "format=yuv420p"]
    if fade_in:
        vf.append(f"fade=t=in:st=0:d={fade_in}")
    if fade_out:
        vf.append(f"fade=t=out:st={seconds - fade_out}:d={fade_out}")
    return [*FFMPEG, "-loop", "1", "-t", str(seconds), "-i", str(png), "-vf", ",".join(vf), *CLIP_CODEC, str(out)]


def scene_filter_graph(seconds: float) -> str:
    """Inputs: 0 the frames, 1 the place label, 2 the credit line (both transparent, full frame)."""
    if seconds < LABEL_OUT_BEFORE_END:
        raise ValueError(f"a scene must last at least {LABEL_OUT_BEFORE_END} s for its label to fade out: "
                         f"got {seconds:g} s")
    fade_in = f"fade=t=in:st={OVERLAY_IN_AT}:d={OVERLAY_IN}:alpha=1"
    label_out = f"fade=t=out:st={min(LABEL_OUT_AT, seconds - LABEL_OUT_BEFORE_END)}:d={LABEL_OUT}:alpha=1"
    return (f"[1]format=rgba,{fade_in},{label_out}[l];"
            f"[2]format=rgba,{fade_in}[c];[0][l]overlay[a];[a][c]overlay,format=yuv420p")


def scene_command(frames_dir: Path, frame_count: int, label_png: Path, credit_png: Path, out: Path,
                  *, fps: float) -> list[str]:
    """The frames %04d.png of one scene under its two overlays."""
    seconds = frame_count / fps
    # A looped image has no end of its own; -t bounds the overlays and -frames:v the clip.
    return [*FFMPEG, "-framerate", str(fps), "-start_number", "0", "-i", str(frames_dir / "%04d.png"),
            "-loop", "1", "-t", str(seconds), "-i", str(label_png),
            "-loop", "1", "-t", str(seconds), "-i", str(credit_png),
            "-filter_complex", scene_filter_graph(seconds), "-frames:v", str(frame_count), *CLIP_CODEC, str(out)]


def xfade_filter_graph(durations: Sequence[float], crossfade: float) -> tuple[str, str]:
    """(filter graph, label of its output) that crossfades inputs 0..n-1 in order."""
    if len(durations) < 2:
        raise ValueError("a crossfade needs at least two clips")
    parts, last = [], "0:v"
    for k, offset in enumerate(xfade_offsets(durations, crossfade), 1):
        parts.append(f"[{last}][{k}:v]xfade=transition=fade:duration={crossfade}:offset={offset:.4f}[v{k}]")
        last = f"v{k}"
    return ";".join(parts), last


def join_command(clips: Sequence[Path], durations: Sequence[float], crossfade: float, out: Path,
                 *, fps: float, crf: str) -> list[str]:
    if len(clips) != len(durations):
        raise ValueError(f"{len(clips)} clips but {len(durations)} durations")
    graph, last = xfade_filter_graph(durations, crossfade)
    inputs = [arg for clip in clips for arg in ("-i", str(clip))]
    return [*FFMPEG, *inputs, "-filter_complex", graph, "-map", f"[{last}]", "-c:v", "libx264", "-crf", str(crf),
            "-preset", "slow", "-pix_fmt", "yuv420p", "-r", str(fps), str(out)]


def mux_command(video: Path, bgm: Path, out: Path) -> list[str]:
    """Video and music in one file, the music still PCM: the mastering pass is its only lossy encode."""
    return [*FFMPEG, "-i", str(video), "-i", str(bgm), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
            "-c:a", "pcm_s16le", "-shortest", str(out)]


def scene_frames(scenes_root: Path, scene: Mapping[str, Any], size: tuple[int, int]) -> list[Path]:
    """The frames of a scene, checked: there are some, and the first has the plan's size."""
    directory = Path(scenes_root) / scene["name"] / scene.get("frames_dir", DEFAULT_FRAMES_DIR)
    frames = sorted(directory.glob("[0-9]*.png"))
    if not frames:
        raise FileNotFoundError(f"no frames for {scene['name']} in {directory}")
    with Image.open(frames[0]) as first:
        if first.size != tuple(size):
            raise ValueError(f"{scene['name']} is not {size[0]} x {size[1]}: {frames[0]} is "
                             f"{first.size[0]} x {first.size[1]}")
    return frames


def _run(args: list[str]) -> None:
    subprocess.run(args, check=True)


def assemble(plan: Mapping[str, Any], scenes_root: Path, work_dir: Path, out_path: Path, crf: str = "18",
             *, fonts: title_cards.FontLoader | None = None, log: Callable[[str], None] | None = None,
             ) -> dict[str, Any]:
    """Encodes every clip into work_dir and writes the mastered video to out_path.

    Everything that can be checked without encoding is checked first, before the work dir exists: a run that
    fails on a missing scene or an overflowing end card leaves nothing behind, and the same command can be run
    again. fonts defaults to the files named by the environment (title_cards.font_paths).
    """
    scenes_root, work, out = Path(scenes_root), Path(work_dir), Path(out_path)
    if out.exists():
        raise FileExistsError(f"{out} exists: give a new version")
    if work.exists():
        raise FileExistsError(f"{work} exists: give a new work dir")
    fonts = fonts or title_cards.truetype_fonts(title_cards.font_paths())
    log = log or (lambda line: print(line, flush=True))
    size = (int(plan["size"][0]), int(plan["size"][1]))
    fps, crossfade = plan["fps"], plan["crossfade"]
    title, credits, scenes = plan["title"], plan["credits"], plan["scenes"]
    frames = [scene_frames(scenes_root, scene, size) for scene in scenes]
    title_png = title_cards.title_card(title["ja"], title["en"], size, fonts)
    credits_png = title_cards.end_card(credits["heading"], credits["lines"], size, fonts)

    work.mkdir(parents=True, exist_ok=False)
    title_png.save(work / "title.png")
    credits_png.save(work / "credits.png")
    clips, durations = [work / "00_title.mp4"], [title["seconds"]]
    _run(still_command(work / "title.png", title["seconds"], clips[0], fps=fps, fade_in=TITLE_FADE_IN))
    for i, (scene, scene_pngs) in enumerate(zip(scenes, frames), 1):
        label, credit = work / f"{i:02d}_label.png", work / f"{i:02d}_credit.png"
        title_cards.place_label(scene["ja"], scene["en"], size, fonts).save(label)
        title_cards.credit_line(scene["credit"], size, fonts).save(credit)
        clip = work / f"{i:02d}_{scene['name']}.mp4"
        _run(scene_command(scene_pngs[0].parent, len(scene_pngs), label, credit, clip, fps=fps))
        clips.append(clip)
        durations.append(len(scene_pngs) / fps)
        start = clip_starts(durations, crossfade)[-1]
        log(f"{scene['name']}: {len(scene_pngs)} frames, starts at {start:.1f} s")
    clips.append(work / "99_credits.mp4")
    durations.append(credits["seconds"])
    _run(still_command(work / "credits.png", credits["seconds"], clips[-1], fps=fps, fade_out=CREDITS_FADE_OUT))

    total = total_length(durations, crossfade)
    night_from = night_start(scenes, clip_starts(durations, crossfade)[1:-1])
    # The music gets its arguments as the text a command line would carry (three and two decimals): a work dir's
    # bgm.wav can then be regenerated exactly by ambient_bgm's own CLI.
    bgm_args = [str(work / "bgm.wav"), f"{total:.3f}"]
    if night_from is not None:
        bgm_args.append(f"--night-from={night_from:.2f}")
    ambient_bgm.main(bgm_args)

    _run(join_command(clips, durations, crossfade, work / "video.mp4", fps=fps, crf=crf))
    _run(mux_command(work / "video.mp4", work / "bgm.wav", work / "mixed.mov"))
    mastered = ffmpeg_ops.normalize_loudness(work / "mixed.mov", out)
    log(f"{out}: {total:.1f} s, night from {night_from}, loudness before mastering {mastered['measured']}")
    return {"output": str(out), "seconds": total, "night_from": night_from,
            "scene_starts": clip_starts(durations, crossfade)[1:-1], "measured": mastered["measured"]}


def main(argv: list[str] | None = None) -> int:
    # Abbreviations are off so that a mistyped option stops the run instead of quietly becoming another one.
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], allow_abbrev=False)
    parser.add_argument("plan", type=Path, help="plan JSON")
    parser.add_argument("scenes_root", type=Path, help="directory with one directory of frames per scene")
    parser.add_argument("work_dir", type=Path, help="a new directory for the cards and the intermediate clips")
    parser.add_argument("out", type=Path, help="the video to write; must not exist")
    parser.add_argument("--crf", default="18", help="x264 quality of the final encode (default 18)")
    args = parser.parse_args(argv)
    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)
    try:
        assemble(plan, args.scenes_root, args.work_dir, args.out, crf=args.crf)
    except FileExistsError as error:
        raise SystemExit(str(error)) from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
