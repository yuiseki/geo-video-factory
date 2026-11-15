"""How often the overall look of the screen changes: a rough measure of visual rhythm.

One sample per second (mean brightness and mean saturation from ffmpeg signalstats). A "look
change" is a jump of more than 12 levels in either within 2 seconds. Also reports the longest
stretch without such a change.

This counts changes of brightness and colour only. A video can change its look often and still
feel repetitive if every scene is built the same way; read it next to the contact sheets.

usage: python3 look_changes.py <video.mp4>
"""
from __future__ import annotations

import re
import statistics as st
import subprocess
import sys

JUMP = 12


def samples(src: str) -> tuple[list[float], list[float]]:
    out = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', src, '-an', '-vf',
                          'fps=1,scale=320:-1,signalstats,metadata=print:file=-', '-f', 'null', '-'],
                         capture_output=True, text=True, check=True).stdout
    y = [float(x) for x in re.findall(r'lavfi\.signalstats\.YAVG=([\d.]+)', out)]
    s = [float(x) for x in re.findall(r'lavfi\.signalstats\.SATAVG=([\d.]+)', out)]
    return y, s


def changes(y: list[float], s: list[float]) -> list[int]:
    return [i for i in range(2, len(y)) if abs(y[i] - y[i - 2]) > JUMP or abs(s[i] - s[i - 2]) > JUMP]


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    y, s = samples(sys.argv[1])
    if len(y) < 3:
        sys.exit('video too short')
    idx = changes(y, s)
    gaps = [b - a for a, b in zip([0] + idx, idx + [len(y)])]
    print(f'look changes {len(idx) / (len(y) / 60):.1f}/min | longest same look {max(gaps)} s | '
          f'brightness mean {st.mean(y):.1f} sd {st.pstdev(y):.1f} | saturation mean {st.mean(s):.1f} sd {st.pstdev(s):.1f}')


if __name__ == '__main__':
    main()
