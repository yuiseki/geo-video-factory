#!/bin/bash
# omvg_sfm.sh <image dir> <work dir>: openMVG's incremental SfM on the same terms as the other tools: SIFT (HIGH
# preset), exhaustive pairs, fundamental-matrix filtering, one intrinsic per photo from its EXIF 35 mm equivalent,
# the photos' GPS as position priors in Earth-centred coordinates, then the model moved into metres east, north,
# up (omvg_tools.py). The engine is the classic INCREMENTAL one: on 130 and 200 street photos INCREMENTALV2 never
# grows past its seed (STELLAR fails to initialise, MAX_PAIR leaves two poses with a NaN error), while it passed
# on 12. Start each run in an empty work dir: openMVG takes an empty matches file left by a failed run as
# finished work and matches nothing. OMVG_IMAGE is a docker image with openMVG's binaries on PATH (built from the repository's
# Dockerfile); PY is a python with numpy and Pillow. Run it under the host's memory and CPU limits.
set -euo pipefail
img=$(realpath "$1"); w=$2; mkdir -p "$w"; w=$(realpath "$w")
here=$(dirname "$(realpath "$0")")
: "${OMVG_IMAGE:?set OMVG_IMAGE to an openMVG docker image}"
mv() { local s; s=$(date +%s)
  docker run --rm -u "$(id -u):$(id -g)" --memory="${MEM:-8g}" --memory-swap="${MEM:-8g}" --cpus="${CPUS:-8}" \
    -v "$img:/img:ro" -v "$w:/w" "$OMVG_IMAGE" "openMVG_main_$1" "${@:2}" > "$w/$1.log" 2>&1
  echo "$1 $(( $(date +%s) - s )) s"; }
mv SfMInit_ImageListing -i /img -o /w -f 1111 -g 0 -c 3 -P -m 0
"${PY:-python3}" "$here/omvg_tools.py" focals "$w/sfm_data.json" "$img"
mv ComputeFeatures -i /w/sfm_data.json -o /w -m SIFT -p HIGH -n "${CPUS:-8}"
mv PairGenerator -i /w/sfm_data.json -o /w/pairs.bin -m EXHAUSTIVE
mv ComputeMatches -i /w/sfm_data.json -p /w/pairs.bin -o /w/matches.putative.bin
mv GeometricFilter -i /w/sfm_data.json -m /w/matches.putative.bin -g f -o /w/matches.f.bin
mv SfM -s INCREMENTAL -i /w/sfm_data.json -m /w -M /w/matches.f.bin -o /w/recon -P
mv openMVG2Colmap -i /w/recon/sfm_data.bin -o /w/colmap_ecef
"${PY:-python3}" "$here/omvg_tools.py" enu "$w/colmap_ecef" "$w/geo"
echo "registered $(grep -vc '^#' "$w/colmap_ecef/images.txt" | awk '{print int($1/2)}') of $(ls "$img" | wc -l)"
