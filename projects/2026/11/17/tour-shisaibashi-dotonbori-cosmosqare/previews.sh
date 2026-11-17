#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")" && pwd -P)"
repo_dir="$(cd "$project_dir/../../../../.." && pwd -P)"
renderer="$repo_dir/packages/renderer"
python_cmd="${GVF_PYTHON:-python3}"
"$python_cmd" "$project_dir/prepare.py" "$@"
(cd "$renderer" && npm run build)
for pair in minami/shinsaibashi minami/dotonbori cosmosquare/cosmosquare; do
  area="${pair%/*}"
  name="${pair#*/}"
  if [ "$#" -gt 0 ]; then
    selected=false
    for arg in "$@"; do [ "$arg" = "$area" ] && selected=true; done
    [ "$selected" = true ] || continue
  fi
  node "$renderer/dist/src/render.js" "$project_dir/areas/$area/shots/$name.json" --project "$project_dir/areas/$area" --out "$project_dir/out/$name.v0.1.3" --no-voice --stills 1 --from 0.5 --to 1
 done
