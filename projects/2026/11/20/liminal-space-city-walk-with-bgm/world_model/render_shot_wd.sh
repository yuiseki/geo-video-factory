#!/usr/bin/env bash
# render_shot_wd.sh <scene.blend> <out dir> <shot> <first> <last>
# Frames first..last-1 of one magic_shots move, drawn by path_render.py from a saved scene. Blender is stopped
# after 25 s without a new frame and started again on the frames still missing (EEVEE sometimes sleeps on a
# frame). Set BLENDER to the binary when it is not on PATH. Run under the host's resource limits.
set -u
here=$(cd "$(dirname "$0")" && pwd)
blend=$1; out=$2; shot=$3; first=$4; last=$5
blender=${BLENDER:-blender}
mkdir -p "$out"
count() { local n=0; for i in $(seq "$first" $((last - 1))); do
  f=$(printf "%s/f%04d" "$out" "$i"); { [ -f "$f.jpg" ] || [ -f "$f.stuck" ]; } && n=$((n + 1)); done; echo $n; }
want=$((last - first))
for try in $(seq 1 40); do
  [ "$(count)" -ge "$want" ] && break
  "$blender" -b "$blend" -P "$here/path_render.py" -- "$out" magic_shots "$shot" --only="$first,$last" >> "$out/blender.log" 2>&1 &
  pid=$!; seen=$(count); last_t=$(date +%s)
  sleep 20
  while kill -0 $pid 2>/dev/null; do
    sleep 3; now=$(count)
    if [ "$now" -gt "$seen" ]; then seen=$now; last_t=$(date +%s); fi
    if [ $(( $(date +%s) - last_t )) -gt 25 ]; then kill $pid; echo "try $try: stopped after 25 s without a frame ($now of $want)"; break; fi
  done
  wait $pid 2>/dev/null
done
echo "$shot: $(count) of $want in $out"
