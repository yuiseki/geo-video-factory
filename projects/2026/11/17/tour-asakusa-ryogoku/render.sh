#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")" && pwd -P)"
repo_dir="$(cd "$project_dir/../../../../.." && pwd -P)"
renderer_dir="$repo_dir/packages/renderer"
python_cmd="${GVF_PYTHON:-python3}"
version="${1:-v0.1.1}"
output="$project_dir/out/$version"
mkdir -p "$output"
"$python_cmd" "$project_dir/prepare.py"
(cd "$renderer_dir" && npm run build)
node "$renderer_dir/dist/src/render.js" "$project_dir/shots/tour.json" --project "$project_dir" --out "$output/map" --no-voice --layer map
node "$renderer_dir/dist/src/render.js" "$project_dir/shots/tour.json" --project "$project_dir" --out "$output/overlay" --no-voice --layer overlay
ffmpeg -y -i "$output/map/map.mp4" -i "$output/overlay/overlay.mov" -filter_complex '[0:v][1:v]overlay=format=auto:shortest=1,format=yuv420p[v]' -map '[v]' -c:v libx264 -pix_fmt yuv420p -crf 18 -preset medium -movflags +faststart "$output/tour-asakusa-ryogoku.$version.mp4"
