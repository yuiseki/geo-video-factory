"""Add the selected CC0 photos to the finished episode without changing audio."""
import json
import subprocess
from pathlib import Path

panels = Path('assets/gyazo/panels_v011')
items = json.loads((panels / 'manifest.json').read_text())
cmd = ['ffmpeg', '-nostdin', '-v', 'error', '-progress', 'pipe:1', '-n',
       '-i', 'out/final_v4/final_v4.mp4']
for i in range(len(items)):
    cmd += ['-i', str(panels / f'{i:02}.png')]
filters = []
for i, item in enumerate(items):
    previous = '0:v' if i == 0 else f'v{i}'
    start, end = item['start'], item['end']
    filters.append(f"[{previous}][{i + 1}:v]overlay=60:60:enable='between(t,{start},{end})'[v{i + 1}]")
cmd += ['-filter_complex', ';'.join(filters), '-map', f'[v{len(items)}]',
        '-map', '0:a:0', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
        '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-movflags', '+faststart',
        'out/v0.1.1/dotonbori.v0.1.1.mp4']
subprocess.run(cmd, check=True)
