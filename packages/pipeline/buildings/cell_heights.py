"""Heights of filled-in buildings, calibrated per JIS third-level mesh cell (about 1 km, buildings.jis_mesh).

A building PLATEAU lacks, with neither OSM building:levels nor height, gets the median PLATEAU height of its class
and footprint size (building_heights.calibrate_height_model). The median is taken over the PLATEAU buildings of the
cell the building's footprint lies in, never over the box being built, so the same building gets the same height in
every box that holds it: plateau_pp reads PLATEAU and GSI for the whole cells around the box.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from buildings.building_heights import calibrate_height_model, footprint_area_m2
from buildings.jis_mesh import mesh3, mesh3_bounds


def _centroid(feature: dict[str, Any]) -> tuple[float, float]:
    ring = feature["geometry"]["coordinates"][0]
    xs, ys = [p[0] for p in ring[:-1]] or [ring[0][0]], [p[1] for p in ring[:-1]] or [ring[0][1]]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def cells_of(features: list[dict[str, Any]]) -> list[str]:
    """The cells the footprints' centres lie in, sorted."""
    return sorted({mesh3(*_centroid(f)) for f in features})


def cells_box(cells: list[str]) -> list[float]:
    """[west, south, east, north] around the cells."""
    bounds = [mesh3_bounds(c) for c in cells]
    return [min(b[0] for b in bounds), min(b[1] for b in bounds), max(b[2] for b in bounds), max(b[3] for b in bounds)]


def cell_height_models(cells: list[str], heights: dict[str, dict[str, Any]],
                       footprints: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{cell: height model} from the PLATEAU buildings (heights: id -> {lonlat, height}) whose centre lies in the
    cell, each matched with the GSI footprint it stands in (for the class and the area)."""
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree

    tree = STRtree([shape(f["geometry"]) for f in footprints]) if footprints else None
    samples: dict[str, list[tuple[Any, float, float]]] = {c: [] for c in cells}
    for key in sorted(heights):
        item = heights[key]
        cell = mesh3(*item["lonlat"])
        if cell not in samples or tree is None:
            continue
        hits = tree.query(Point(*item["lonlat"]), predicate="within")
        if len(hits):
            f = footprints[int(min(hits))]
            samples[cell].append((f["properties"]["vt_code"], footprint_area_m2(f["geometry"]["coordinates"][0]),
                                  item["height"]))
    return {c: calibrate_height_model(samples[c]) for c in cells}


def model_for(models: dict[str, dict[str, Any]]) -> Callable[[float, float], dict[str, Any]]:
    """(lon, lat) -> the model of the cell there (the prior where no cell was calibrated)."""
    prior = calibrate_height_model([])

    def at(lon: float, lat: float) -> dict[str, Any]:
        return models.get(mesh3(lon, lat), prior)
    at.models = models                   # what city_proxy records beside the buildings
    return at


def feature_heights(tileset_url: str, bbox_degrees: list[float], *, fetcher: Callable[[str], bytes] | None = None,
                    raw_cache: Path | None = None) -> dict[str, dict[str, Any]]:
    """{gml id: {lonlat, height}} of every PLATEAU building in the leaves intersecting the box, read from the served
    tiles (the shared plateau-raw cache) without writing anything: what cell_heights calibrates on."""
    from buildings.glb_spatial import extract_glb_feature_heights
    from buildings.plateau_3d import _cached_fetcher, _leaf_items, _parse_tile
    fetch = _cached_fetcher(fetcher, raw_cache)
    out: dict[str, dict[str, Any]] = {}
    for item in _leaf_items(tileset_url, bbox_degrees, fetch):
        glb, ids, rtc, _ = _parse_tile(fetch(item['uri']), item['uri'])
        if ids:
            out.update(extract_glb_feature_heights(glb, [float(v) for v in rtc], ids))
    return out
