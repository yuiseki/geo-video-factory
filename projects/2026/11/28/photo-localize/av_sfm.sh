#!/bin/bash
# av_sfm.sh <image dir> <work dir>: AliceVision's incremental SfM (the engine under Meshroom) on the same terms as
# colmap_sfm.py: SIFT up to 8,192 features, exhaustive pairs, then the model exported as COLMAP text and put on the
# photos' GPS with colmap_sfm.py --georef (world_model.sim3.from_positions; PY is a python with numpy, scipy and Pillow). AV_ROOT is the unpacked release
# (the directory with bin/, lib/, share/aliceVision/). Run it under the host's memory and CPU limits.
set -euo pipefail
img=$(realpath "$1"); w=$2; mkdir -p "$w"; w=$(realpath "$w")
here=$(dirname "$(realpath "$0")")
: "${AV_ROOT:?set AV_ROOT to the unpacked AliceVision release}"
export ALICEVISION_ROOT=$AV_ROOT LD_LIBRARY_PATH=$AV_ROOT/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
av() { local s; s=$(date +%s); "$AV_ROOT/bin/aliceVision_$1" "${@:2}" > "$w/$1.log" 2>&1; echo "$1 $(( $(date +%s) - s )) s"; }
threads=${THREADS:-8}
av cameraInit --imageFolder "$img" --sensorDatabase "$AV_ROOT/share/aliceVision/cameraSensors.db" \
  --errorOnMissingColorProfile 0 -o "$w/cameraInit.sfm"
"${PY:-python3}" "$here/av_intrinsics.py" "$w/cameraInit.sfm"
av featureExtraction -i "$w/cameraInit.sfm" -o "$w/features" --describerTypes sift --maxNbFeatures 8192 \
  --forceCpuExtraction 1 --maxThreads "$threads"
av imageMatching -i "$w/cameraInit.sfm" --featuresFolders "$w/features" --method Exhaustive -o "$w/pairs.txt"
mkdir -p "$w/matches"
av featureMatching -i "$w/cameraInit.sfm" --featuresFolders "$w/features" --imagePairsList "$w/pairs.txt" \
  --describerTypes sift -o "$w/matches" --maxCoresAvailable "$threads"
av incrementalSfM -i "$w/cameraInit.sfm" --featuresFolders "$w/features" --matchesFolders "$w/matches" \
  --describerTypes sift -o "$w/sfm.abc" --outputViewsAndPoses "$w/cameras.sfm" --maxCoresAvailable "$threads"
av exportColmap -i "$w/sfm.abc" -o "$w/colmap"
model=$(dirname "$(find "$w/colmap" -name images.txt | head -1)")
"${PY:-python3}" "$here/colmap_sfm.py" --georef "$model" "$img" "$w/geo"
echo "registered $(grep -vc '^#' "$model/images.txt" | awk '{print int($1/2)}') of $(ls "$img" | wc -l)"
