"""Build PLATEAU++ for every trial area of areas.json into out/<name>-<version>/.

    OVERPASS_URL=<your Overpass> python projects/2026/11/26/plateau-pp/build_trial.py [--version=v1] [name ...]

Run it under the host's resource limits. An existing output is left as it is; pass a new --version instead.
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIPELINE = HERE.parents[4] / "packages" / "pipeline"

opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--"))
names = [a for a in sys.argv[1:] if not a.startswith("--")]
version = opts.get("version", "v1")
failed = []
for area in json.loads((HERE / "areas.json").read_text(encoding="utf-8"))["areas"]:
    if names and area["name"] not in names:
        continue
    out = HERE / "out" / f"{area['name']}-{version}"
    if (out / "manifest.json").exists():
        print(f"{out.name}: exists, left as it is", flush=True)
        continue
    print(f"== {out.name} {area['label']}", flush=True)
    bbox = ",".join(str(v) for v in area["bbox"])
    code = subprocess.call([sys.executable, "-u", "-m", "buildings.plateau_pp", str(out), f"--bbox={bbox}"], cwd=PIPELINE)
    if code:
        failed.append(area["name"])
print("failed:", " ".join(failed) if failed else "none")
sys.exit(1 if failed else 0)
