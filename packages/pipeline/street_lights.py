"""Place street light sources from open data: snap OSM traffic signals onto PLATEAU sidewalks.

OSM `highway=traffic_signals` nodes sit on the carriageway (stop lines), while the poles stand
on the sidewalk corner. Each node is moved to the nearest PLATEAU road LOD3 sidewalk vertex.
"""
from __future__ import annotations

import argparse
import json
import math
import urllib.request
from pathlib import Path
from typing import Sequence

KY = 110_950


def _kx(origin: Sequence[float]) -> float:
    return 111_320 * math.cos(math.radians(origin[1]))


def to_local(lnglat: Sequence[float], origin: Sequence[float]) -> tuple[float, float]:
    return ((lnglat[0] - origin[0]) * _kx(origin), (lnglat[1] - origin[1]) * KY)


def to_lnglat(xy: Sequence[float], origin: Sequence[float]) -> tuple[float, float]:
    return (origin[0] + xy[0] / _kx(origin), origin[1] + xy[1] / KY)


def snap_points(points, candidates, max_distance: float):
    """Nearest candidate for each point, or None when none is within `max_distance` meters."""
    out = []
    for p in points:
        best = min(candidates, key=lambda c: (c[0] - p[0]) ** 2 + (c[1] - p[1]) ** 2, default=None)
        if best is None or math.dist(best, p) > max_distance:
            out.append(None)
        else:
            out.append(tuple(best))
    return out


def sidewalk_vertices(manifest_path: Path, origin: Sequence[float]) -> list[tuple[float, float]]:  # pragma: no cover - I/O
    """Local-meter vertices of PLATEAU road LOD3 features whose function is 歩道部."""
    import glb_spatial
    import plateau_3d

    manifest = json.loads(manifest_path.read_text())
    vertices = []
    for tile in manifest["tiles"]:
        request = urllib.request.Request(tile["source"], headers={"User-Agent": plateau_3d.USER_AGENT})
        attrs = (plateau_3d.parse_b3dm(urllib.request.urlopen(request, timeout=120).read()).get("batch_table") or {}).get("attributes", [])
        sidewalks = {i for i, a in enumerate(attrs) if a.get("tran:function") == "歩道部"}
        payload = (manifest_path.parent / tile["glb"]).read_bytes()
        for index, points in glb_spatial._feature_ecef_points(payload, tile["rtc"], tile["ids"]).items():
            if index in sidewalks:
                for ecef in points:
                    lng, lat = glb_spatial._geodetic(ecef)
                    vertices.append(to_local((lng, lat), origin))
    return vertices


def main() -> None:  # pragma: no cover - thin CLI
    parser = argparse.ArgumentParser()
    parser.add_argument("signals", type=Path, help="JSON with signals[].lngLat (OSM traffic_signals)")
    parser.add_argument("roads_manifest", type=Path, help="frozen PLATEAU road LOD3 manifest")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-distance", type=float, default=15.0)
    args = parser.parse_args()
    signals = json.loads(args.signals.read_text())["signals"]
    origin = json.loads(args.roads_manifest.read_text())["center"]
    candidates = sidewalk_vertices(args.roads_manifest, origin)
    snapped = snap_points([to_local(s["lngLat"], origin) for s in signals], candidates, args.max_distance)
    poles = []
    for signal, xy in zip(signals, snapped):
        if xy is not None:
            poles.append({"osmId": signal["id"], "lngLat": list(to_lnglat(xy, origin)),
                          "movedM": round(math.dist(xy, to_local(signal["lngLat"], origin)), 1)})
    args.out.write_text(json.dumps({"source": "OSM highway=traffic_signals snapped to PLATEAU road LOD3 sidewalks",
                                    "poles": poles}, ensure_ascii=False, indent=1))
    print(f"{len(poles)}/{len(signals)} signals snapped; moved {[p['movedM'] for p in poles]} m")


if __name__ == "__main__":  # pragma: no cover
    main()
