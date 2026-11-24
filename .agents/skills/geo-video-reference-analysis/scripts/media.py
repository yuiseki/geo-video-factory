"""Measure a reference video with ffmpeg: cuts, loudness, silences, contact sheets, chapter openings.

usage: python3 media.py <video.mp4> <outdir> [--info a.info.json] [--sheet-step 20] [--cut-threshold 0.25]

writes into <outdir>:
  cuts.txt          one time (s) per hard cut (scene score > threshold)
  loudness.txt      integrated loudness, loudness range, count of silences (< -50 dB for 0.5 s)
  sheets/sheet_NN.jpg   frames every --sheet-step seconds, 4x4 per sheet, time in the corner
  chapters/all.jpg  frames 0.5, 1.5 and 3 s after each chapter start (needs --info with chapters)
Run it inside a memory/CPU limit; decoding a 1080p video uses one or more cores for minutes.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess


def run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f'failed: {" ".join(cmd[:6])} ...\n{r.stderr[-1500:]}')
    return r.stderr + r.stdout


def cuts(src: str, threshold: float) -> list[float]:
    log = run(['ffmpeg', '-nostdin', '-i', src, '-an', '-vf',
               f"scale=480:-1,select='gt(scene,{threshold})',showinfo", '-f', 'null', '-'])
    return [float(x) for x in re.findall(r'pts_time:([\d.]+)', log)]


def loudness(src: str) -> dict:
    log = run(['ffmpeg', '-nostdin', '-i', src, '-vn', '-af',
               'ebur128=peak=true,silencedetect=n=-50dB:d=0.5', '-f', 'null', '-'])
    summary = log[log.rfind('Summary:'):]
    i = re.search(r'I:\s+(-?[\d.]+) LUFS', summary)
    lra = re.search(r'LRA:\s+([\d.]+) LU', summary)
    return {'integrated_lufs': float(i.group(1)) if i else None,
            'lra_lu': float(lra.group(1)) if lra else None,
            'silences': len(re.findall(r'silence_start', log))}


def sheets(src: str, out: pathlib.Path, step: float) -> None:
    out.mkdir(parents=True, exist_ok=True)
    stamp = "pad=iw:ih+32:0:32:black,drawtext=text='%{pts\\:hms}':x=8:y=4:fontsize=24:fontcolor=white"
    run(['ffmpeg', '-nostdin', '-y', '-i', src, '-an', '-vf',
         f'fps=1/{step},scale=480:-1,{stamp},tile=4x4', '-q:v', '4', str(out / 'sheet_%02d.jpg')])


def adaptive_sheets(src: str, out: pathlib.Path, budget: int) -> dict:
    import sys
    pipeline_dir = pathlib.Path(__file__).resolve().parents[4] / 'packages' / 'pipeline'
    if str(pipeline_dir) not in sys.path:
        sys.path.insert(0, str(pipeline_dir))
    from video import video_inspect
    out.mkdir(parents=True, exist_ok=True)
    return video_inspect.build_adaptive_storyboard(
        pathlib.Path(src), out / 'storyboard.jpg',
        budget=budget, timeline_path=out / 'timeline.txt', overwrite=True,
    )


def chapter_heads(src: str, chapters: list[dict], out: pathlib.Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for n, c in enumerate(chapters):
        for d in (0.5, 1.5, 3.0):
            f = out / f'c{n:02d}_{d}.jpg'
            run(['ffmpeg', '-nostdin', '-y', '-ss', str(c['start_time'] + d), '-i', src,
                 '-frames:v', '1', '-vf', 'scale=480:-1', '-q:v', '4', str(f)])
            files.append(f)
    # one row per chapter (0.5 s, 1.5 s, 3 s after its start)
    inputs = sum((['-i', str(f)] for f in files), [])
    rows = [f'[{3 * r}:v][{3 * r + 1}:v][{3 * r + 2}:v]hstack=3[r{r}]' for r in range(len(chapters))]
    graph = ';'.join(rows)
    if len(chapters) > 1:
        graph += ';' + ''.join(f'[r{r}]' for r in range(len(chapters))) + f'vstack={len(chapters)}[all]'
        last = '[all]'
    else:
        last = '[r0]'
    run(['ffmpeg', '-nostdin', '-y', *inputs, '-filter_complex', graph, '-map', last,
         '-frames:v', '1', str(out / 'all.jpg')])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('video')
    ap.add_argument('outdir')
    ap.add_argument('--info')
    ap.add_argument('--sheet-step', type=float, default=20)
    ap.add_argument('--cut-threshold', type=float, default=0.25)
    ap.add_argument('--adaptive', action='store_true', help='Also generate adaptive keyframe storyboard and timeline')
    ap.add_argument('--budget', type=int, default=32, help='Keyframe budget for --adaptive (default: 32)')
    a = ap.parse_args()
    out = pathlib.Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)

    c = cuts(a.video, a.cut_threshold)
    (out / 'cuts.txt').write_text(''.join(f'{t:.2f}\n' for t in c))
    ld = loudness(a.video)
    (out / 'loudness.txt').write_text(json.dumps(ld) + '\n')
    sheets(a.video, out / 'sheets', a.sheet_step)
    msg = f'cuts {len(c)} | {ld["integrated_lufs"]} LUFS, LRA {ld["lra_lu"]} LU, silences {ld["silences"]}'
    if a.adaptive:
        ad = adaptive_sheets(a.video, out / 'adaptive', a.budget)
        msg += f' | adaptive {ad["keyframes"]} frames'
    if a.info:
        chapters = json.loads(pathlib.Path(a.info).read_text(encoding='utf-8')).get('chapters') or []
        if chapters:
            chapter_heads(a.video, chapters, out / 'chapters')
            msg += f' | chapters {len(chapters)}'
    print(msg)


if __name__ == '__main__':
    main()
