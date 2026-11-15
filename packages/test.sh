#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)

cd "$root/packages/renderer"
npm ci
npm run typecheck
npm test
npm run test:coverage

cd "$root"
python3 -m coverage erase
python3 -m coverage run --rcfile=packages/pipeline/.coveragerc \
  -m unittest discover -s packages/pipeline/tests -v
python3 -m coverage report --rcfile=packages/pipeline/.coveragerc
