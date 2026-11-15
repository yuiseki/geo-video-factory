"""Turn a YouTube WebVTT caption file into one timed line per spoken line, and measure speaking speed.

YouTube's automatic captions roll: each cue repeats the previous line and adds the next one, and
carries per-word timing tags. Creator-uploaded captions do not. Both are handled.

usage: python3 transcript.py <captions.vtt> [--duration SECONDS] [--out transcript.txt]
prints the number of lines, characters, and characters per second over the given duration
(the whole video, silences included, so it is comparable between videos).
"""
from __future__ import annotations

import argparse
import re
import sys

CUE_TIME = re.compile(r'^(\d+):(\d{2}):(\d{2})\.(\d{3}) -->')
TAG = re.compile(r'<[^>]+>')


def seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse(text: str) -> list[tuple[float, str]]:
    """[(start seconds, line)] with rolling repeats removed."""
    out: list[tuple[float, str]] = []
    recent: list[str] = []
    start = None
    for raw in text.splitlines():
        m = CUE_TIME.match(raw)
        if m:
            start = seconds(*m.groups())
            continue
        if start is None:
            continue  # header
        line = TAG.sub('', raw).strip()
        if not line:
            continue
        if line in recent:
            continue
        out.append((start, line))
        recent = (recent + [line])[-2:]
    return out


def chars_per_second(lines: list[tuple[float, str]], duration: float) -> float:
    n = sum(len(re.sub(r'\s', '', t)) for _, t in lines)
    return n / duration if duration else 0.0


def mmss(t: float) -> str:
    t = int(t)
    return f'{t // 60:02d}:{t % 60:02d}'


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('vtt')
    ap.add_argument('--duration', type=float, help='video length in seconds (from info.json)')
    ap.add_argument('--out')
    a = ap.parse_args()
    with open(a.vtt, encoding='utf-8') as f:
        lines = parse(f.read())
    if a.out:
        with open(a.out, 'w', encoding='utf-8') as f:
            f.writelines(f'{mmss(t)} {s}\n' for t, s in lines)
    chars = sum(len(re.sub(r'\s', '', s)) for _, s in lines)
    msg = f'lines {len(lines)} chars {chars}'
    if a.duration:
        msg += f' chars/s {chars_per_second(lines, a.duration):.1f} (over {a.duration:.0f} s)'
    print(msg)
    if not lines:
        sys.exit('no caption lines found')


if __name__ == '__main__':
    main()
