"""Score a visual place recognition model by where its nearest photo was taken.

Every photo with a position is a query. The database is the CC0 photos; a query may
not match itself or another photo by the same creator on the same day, since those
are near copies a new photo would not have. A query is right at k when one of its k
best database photos stands within RADIUS_M of it, and it counts towards recall only
when such a photo exists at all (its oracle distance is within reach).

    python vpr_eval.py collect <cc0 research dir> <cc0 photo dir> <gyazo cache dir> <items.json>
    python vpr_eval.py score <items.json> <descriptors.npy> <rows.jsonl>
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

RADIUS_M = 25.0
KS = (1, 5, 10)


def metres(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(a))


def eligible(q, d):
    return q["id"] != d["id"] and not (q["creator"] == d["creator"] and q["date"] == d["date"])


def evaluate(items, desc, ks=KS):
    db = [i for i, it in enumerate(items) if it["role"] == "db"]
    sims = desc @ desc[db].T
    rows = []
    for qi, q in enumerate(items):
        ok = [j for j, di in enumerate(db) if eligible(q, items[di])]
        if not ok:
            continue
        dist = {j: metres(q["lon"], q["lat"], items[db[j]]["lon"], items[db[j]]["lat"]) for j in ok}
        order = sorted(ok, key=lambda j: (-float(sims[qi, j]), items[db[j]]["id"]))
        rows.append({
            "id": q["id"], "role": q["role"], "area": q.get("area"),
            "ranked": [items[db[j]]["id"] for j in order[:max(ks)]],
            "top1_m": round(dist[order[0]], 1),
            "oracle_m": round(min(dist.values()), 1),
            "hit": {k: any(dist[j] <= RADIUS_M for j in order[:k]) for k in ks},
        })
    return rows


def summary(rows, ks=KS):
    reach = [r for r in rows if r["oracle_m"] <= RADIUS_M]
    top1 = sorted(r["top1_m"] for r in rows)
    return {
        "queries": len(rows), "reachable": len(reach),
        "recall": {k: (sum(r["hit"][k] for r in reach) / len(reach) if reach else None) for k in ks},
        "median_top1_m": top1[len(top1) // 2] if top1 else None,
    }


def collect(research, photos, gyazo):
    items = []
    for m in sorted(Path(research).glob("*_manifest.json")):
        for p in json.loads(m.read_text(encoding="utf-8"))["photos"]:
            c, local = p.get("coordinates"), p.get("local_path")
            path = Path(photos) / local.split("tokyo_cc0/", 1)[1] if local else None
            if c and path and path.exists():
                items.append({"id": p["id"], "path": str(path), "lon": c[0], "lat": c[1], "creator": p["creator"],
                              "date": p.get("date") or "", "area": p["area"], "spot": p["spot_slug"], "role": "db"})
    for meta in sorted(Path(gyazo).glob("*/meta.json")):
        g = json.loads(meta.read_text(encoding="utf-8"))
        c = g.get("coordinates")
        if c and (meta.parent / "photo.jpg").exists():
            items.append({"id": "gyazo_" + meta.parent.name, "path": str(meta.parent / "photo.jpg"), "lon": c[0],
                          "lat": c[1], "creator": g["creator"], "date": g.get("date") or "", "area": "gyazo",
                          "role": "query"})
    return items


def main(argv):
    if argv[0] == "collect":
        items = collect(*argv[1:4])
        Path(argv[4]).write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")
        print(len(items), "photos,", sum(i["role"] == "db" for i in items), "in the database")
    elif argv[0] == "score":
        items = [json.loads(line) for line in Path(argv[1]).read_text(encoding="utf-8").splitlines()]
        rows = evaluate(items, np.load(argv[2]))
        Path(argv[3]).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        for name, sub in (("cc0 leave-one-out", [r for r in rows if r["role"] == "db"]),
                          ("gyazo against cc0", [r for r in rows if r["role"] == "query"])):
            print(name, json.dumps(summary(sub)))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
