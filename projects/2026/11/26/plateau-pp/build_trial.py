"""Build PLATEAU++ (baked, as plateau_pp makes it) for every trial area of areas.json into out/<name>/.

    OVERPASS_URL=<your Overpass> python projects/2026/11/26/plateau-pp/build_trial.py [--no-bake] [name ...]

--no-bake builds the pre-v0.1.0 PLATEAU++ (look left to the renderer's shaders) into out/before/<name>/, to compare.

Run it under the host's resource limits. out/<name>/ is rebuilt from scratch every time: versions are commits.
Downloads come from the shared cache (packages/pipeline/shared_cache.py); each area's OSM extract is kept there
too, under osm/<name>.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIPELINE = HERE.parents[4] / "packages" / "pipeline"
sys.path.insert(0, str(PIPELINE))
from shared_cache import cache_root  # noqa: E402

names = [a for a in sys.argv[1:] if not a.startswith("--")]
no_bake = "--no-bake" in sys.argv[1:]
root = HERE / "out" / ("before" if no_bake else "")
failed = []
for area in json.loads((HERE / "areas.json").read_text(encoding="utf-8"))["areas"]:
    if names and area["name"] not in names:
        continue
    out = root / area["name"]
    if out.exists():
        shutil.rmtree(out)
    print(f"== {area['name']} {area['label']}", flush=True)
    bbox = ",".join(str(v) for v in area["bbox"])
    code = subprocess.call([sys.executable, "-u", "-m", "buildings.plateau_pp", str(out), f"--bbox={bbox}",
                            f"--cache={cache_root() / 'osm' / area['name']}"] + (["--no-bake"] if no_bake else []), cwd=PIPELINE)
    if code:
        failed.append(area["name"])
print("failed:", " ".join(failed) if failed else "none")
sys.exit(1 if failed else 0)
