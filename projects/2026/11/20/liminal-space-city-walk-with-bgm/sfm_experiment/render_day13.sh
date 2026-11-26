#!/bin/bash
# 昼の渋谷、全部が真昼の写真の版: A = 049 を 013 の上に、B = 013 を 049 の上に (009 は夕方なので使わない)。
# usage: render_day13.sh <work_dir> [stills|test]
#   stills: 確認用の静止画だけ / test: <work_dir>/test_a.json, test_b.json のカメラだけ / 省略: frames_{a,b}.json
#   環境変数 DAY_A, DAY_B で場面ごとの見た目の引数を渡す (例: DAY_A="--day --sun=200,55")
set -euo pipefail
G=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
P=$G/projects/2026/11/20/liminal-space-city-walk-with-bgm
E=$P/sfm_experiment
Z=$P/work/trials          # the photos with people removed and the projection set-ups (git-ignored, see work/)
N=$Z/day/nopeople
W=$1
MODE=${2:-all}
CAP=(systemd-run --user --scope -q -p MemoryMax=12G -p MemorySwapMax=0 -p CPUQuota=800% --)
K49=shibuya_crossing__049; K13=shibuya_crossing__013
P49=--photo-$K49=$N/049_2016_27737461806_nopeople.png
P13=--photo-$K13=$N/013_Shibuya_Crossing_2018_Shibuya_Crossing_Cropped_nopeople.png
FA=(); FB=()
if [ "$MODE" = all ]; then FA=(--frames=$W/frames_a.json); FB=(--frames=$W/frames_b.json); fi
if [ "$MODE" = test ]; then FA=(--frames=$W/test_a.json); FB=(--frames=$W/test_b.json); fi
mkdir -p $W
cd $G
date +%T; echo "== A"
"${CAP[@]}" blender -b --factory-startup -P $E/blender_projection.py -- $G $Z/proj_day $W/stillsA $K49 $K49 $K13 "$P49" "$P13" --stretch=0 --crosswalks=$E/crosswalks.json "${FA[@]}" --aged ${DAY_A:---day} > $W/blender_a.log 2>&1
date +%T; echo "== B"
"${CAP[@]}" blender -b --factory-startup -P $E/blender_projection.py -- $G $Z/proj_day $W/stillsB $K49 $K13 $K49 "$P49" "$P13" --stretch=0 --crosswalks=$E/crosswalks.json "${FB[@]}" --aged ${DAY_B:---day} > $W/blender_b.log 2>&1
date +%T; echo "== rendered"
