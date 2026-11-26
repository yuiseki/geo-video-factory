"""Whether the level lines of Shibuya's street photos tell the camera's turn, against PLATEAU's walls (geo/vanishing.py).

    python projects/2026/11/26/plateau-pp-ultra-after/vanishing_eval.py [--above=<elevation deg>]

The same 31 SfM-aligned street photos as placement_eval.py, at their true pose (the best case: pitch, roll and place
known). --above keeps only the pixels looking higher than that (the facades, not the people). For each, the turn of the photo's level-line azimuths that best fits the walls within 120 m of the true eye;
0 is right. A street grid is square, so the error is folded to -45..45 degrees. Prints one row per photo and writes
work/vanishing_eval.json. Run from the repository root with packages/pipeline's Python, under resource limits.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[4] / "packages" / "pipeline"))
import placement_eval as pe  # noqa: E402
from geo import skyline_match as sm  # noqa: E402
from geo import vanishing as vp  # noqa: E402
from photos import photo_store  # noqa: E402

WIDTH = 800
ABOVE = float(next((a.split("=")[1] for a in sys.argv[1:] if a.startswith("--above=")), "-90"))


def main() -> None:
    tris = np.load(pe.TRIS)["tris"]
    rows = []
    for n, (key, cam) in enumerate(pe.street_cams()):
        with Image.open(photo_store.camera_photo(cam)) as im:
            s = WIDTH / im.width
            gray = np.asarray(im.convert("L").resize((WIDTH, round(im.height * s))), float)
        f, _, cx, cy = cam["params"]
        k = (cam.get("distortion") or [0.0])[0]
        a, e = sm.pixel_rays(gray.shape[1], gray.shape[0], f * s, cx * s, cy * s, k, cam["Rw"], step=1)
        mask = HERE / "work" / "placement_eval" / "skyline" / key / "mask.jpg"
        sky = None
        if mask.exists():
            with Image.open(mask) as m:
                sky = np.asarray(m.convert("L").resize(gray.shape[::-1]), float) > 127
        low = e < ABOVE                               # people, cars and signs stand low; facades rise
        photo = vp.blur(vp.photo_azimuths(a, e, gray, low if sky is None else sky | low), 1)
        model = vp.blur(vp.model_azimuths(tris, cam["eye"]), 1)
        cost = vp.turn_cost(photo, model)
        best = int(np.argmin(cost))
        err = (best + 45) % 90 - 45
        folded = np.minimum(cost[:90], cost[90:])        # a square grid: a turn and the turn 90 degrees on
        rank = int(np.sum(folded < folded[0]))
        rows.append({"n": n, "key": key, "turn_error_deg": err, "cost_true": round(float(cost[0]), 3),
                     "cost_best": round(float(cost[best]), 3), "truth_rank_of_90": rank})
        print(n, key[:40], f"error {err:+d} deg  cost at truth {cost[0]:.3f}  best {cost[best]:.3f}  "
              f"truth rank {rank}/90", flush=True)
    (HERE / "work" / f"vanishing_eval_above{ABOVE:g}.json").write_text(json.dumps(rows, indent=1) + "\n")
    errs = [abs(r["turn_error_deg"]) for r in rows]
    print(f"within 3 deg: {sum(x <= 3 for x in errs)}/{len(errs)}; median |error| {sorted(errs)[len(errs) // 2]} deg; "
          f"median rank of the truth {sorted(r['truth_rank_of_90'] for r in rows)[len(rows) // 2]}/90 "
          f"(by chance: 2.3 within 3 deg, median |error| 22.5 deg, median rank 45)")


if __name__ == "__main__":
    main()
