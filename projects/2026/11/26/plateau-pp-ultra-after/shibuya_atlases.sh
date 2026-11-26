#!/bin/bash
# Rebuild Shibuya's CC0 atlases with today's build_atlas (which also writes quality.png) into work/shibuya/,
# from the CC0 world model of the liminal project, with the options its run_cc0_v1.sh/run_cc0_v1b.sh used.
# Run from anywhere in the repository; packages/pipeline's Python; under the host's resource limits (around: 16 GB).
set -euo pipefail
REPO=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
HERE=$REPO/projects/2026/11/26/plateau-pp-ultra-after
W=$REPO/projects/2026/11/20/liminal-space-city-walk-with-bgm/work
S=$W/shibuya_world_v1; T=$W/shibuya_crossing/plateau/tris.npz; C=$S/sfm_world_cc0_v1/layers
P=${PYTHON:-$REPO/packages/pipeline/.venv/bin/python}
O=$HERE/work/shibuya; mkdir -p $O
cd $REPO/packages/pipeline
for L in day night; do
  for B in qfront ekimae s109; do
    # 278 (the crossing at night, toward Center-gai) does not show 109, but the model lets it see 109's wall low in
    # the frame, where the photo has the crowd: it alone painted the crowd as a smear over that wall
    SKIP=; [ "$B$L" = s109night ] && SKIP=--skip=278_The_front_of_Shibuya_Station_Crossing_20211126_01
    $P -u -m world_model.build_atlas $S $B $T $O/${B}_${L}_cc0_v1 --keep=10 --patch=3 --agree=25 --smooth=2 --fill=mean --eras=2 $SKIP $C/cams_$L.json > $O/${B}_${L}.log 2>&1
    echo "$B $L exit $?"
  done
  $P -u -m world_model.build_atlas $S/magnet_v1 magnet $T $O/magnet_${L}_cc0_v1 --keep=10 --patch=3 --agree=25 --smooth=2 --fill=mean --eras=2 $C/cams_$L.json > $O/magnet_${L}.log 2>&1
  echo "magnet $L exit $?"
  $P -u -m world_model.build_atlas $S/around_v2 around $T $O/around_${L}_cc0_v1b --texel=0.1 --width=8192 --keep=6 --patch=3 --agree=25 --smooth=2 --fill=mean --split=25 --changing=45 $C/cams_$L.json > $O/around_${L}.log 2>&1
  echo "around $L exit $?"
done
