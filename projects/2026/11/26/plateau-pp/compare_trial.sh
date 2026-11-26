#!/bin/bash
# Build, place and render every trial area into out/<name>/ and out/compare/ (both rewritten each run).
#   OVERPASS_URL=<your Overpass> PYTHON=<python with packages/pipeline deps> projects/2026/11/26/plateau-pp/compare_trial.sh
# Run from the repository root under the host's resource limits; needs blender and node on PATH.
set -euo pipefail
P=projects/2026/11/26/plateau-pp
PY=${PYTHON:-python3}
"$PY" $P/build_trial.py
mkdir -p $P/out/compare
for name in $("$PY" -c "import json;print(' '.join(a['name'] for a in json.load(open('$P/areas.json'))['areas']))"); do
  "$PY" $P/scene_trial.py "$name"
  blender -b --factory-startup -P "$PWD/$P/compare_blender.py" -- "$PWD/$P/out/$name" "$PWD/$P/out/compare/${name}_blender.png" > /dev/null
  node $P/compare_three.mjs "$P/out/$name" "$P/out/compare/${name}_three.png"
done
"$PY" $P/compare_sheet.py
