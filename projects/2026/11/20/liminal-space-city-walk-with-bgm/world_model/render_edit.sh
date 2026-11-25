#!/usr/bin/env bash
# render_edit.sh <edit.json> <out_dir> [bgm.wav]
# Frames of the edit list -> one mp4; with a BGM, looped under it, faded out with the picture and mastered to
# -14 LUFS. Without one, a silent mp4. Set WORLD and FLYOUT (where the clips live) in the environment; run under the host's resource limits.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
edit=$1; out=$2; bgm=${3:-}
mkdir -p "$out"
python "$here/edit_frames.py" "$edit" "$out/frames"
n=$(ls "$out/frames" | wc -l)
fps=$(python -c "import json,sys; print(json.load(open(sys.argv[1])).get('fps', 30))" "$edit")
dur=$(python -c "print($n / $fps)")
fade=$(python -c "print(max($n / $fps - 2.5, 0))")
if [ -z "$bgm" ]; then
  ffmpeg -y -loglevel error -framerate "$fps" -i "$out/frames/f%05d.jpg" -c:v libx264 -pix_fmt yuv420p -crf 18 \
    "$out/$(basename "$out").mp4"
else
ffmpeg -y -loglevel error -framerate "$fps" -i "$out/frames/f%05d.jpg" -stream_loop -1 -i "$bgm" \
  -filter_complex "[1:a]atrim=0:$dur,afade=t=in:d=1.5,afade=t=out:st=$fade:d=2.5,loudnorm=I=-14:TP=-1.5:LRA=11[a]" \
  -map 0:v -map "[a]" -c:v libx264 -pix_fmt yuv420p -crf 18 -c:a aac -b:a 192k -shortest "$out/$(basename "$out").mp4"
fi
echo "wrote $out/$(basename "$out").mp4 ($n frames, $dur s)"
