# TODO: PLATEAU building appearance and OSM proxies

This is the implementation checklist for the work on branch `feat/plateau-appearance-osm-proxies`. See [handover.md](handover.md) for the design context and known gaps. Keep changes test-first.

## Immediate correctness work

- [ ] Make `build_osm_proxy_tiles()` exclude OSM footprints that overlap existing PLATEAU buildings. Use the available per-building PLATEAU feature centroids as an initial overlap signal; wire `extract_glb_feature_centroids()` into the manifest, then use point-in-polygon against OSM footprints. Do not claim this catches every partial footprint overlap; add a more robust overlap strategy if needed.
- [ ] Pass existing PLATEAU IDs / centroid metadata from the CLI into OSM proxy generation. Right now `plateau_3d.py --osm-geojson` calls `build_osm_proxy_tiles()` without `plateau_ids`, so the CLI path does not perform the explicit ID exclusion tested by the function API.
- [ ] Make palette inference robust for partial texturing within one building. A building should keep actual source textures wherever present and receive inferred color only on genuinely untextured facade material/features. Current textured-feature detection can mark a whole feature textured from one textured primitive.
- [ ] Verify GLB batch/feature IDs against the PLATEAU versions encountered in the Ryogoku trial and retain correct ID order when writing `facade_colors`.
- [ ] Fix malformed or absent feature geometry handling and validate orthophoto bounds, image dimensions, and empty/degenerate footprints with clear errors.

## Fidelity and coverage

- [ ] Sample a footprint's orthophoto pixels robustly (mask the polygon and ignore shadows/roads where possible) instead of relying only on a centroid sample for PLATEAU GLB features. Preserve a stable seed so repeated renders match.
- [ ] Estimate facade tone from roof/footprint color while reducing bright roof bias; keep neighboring untextured buildings visibly varied without random frame-to-frame flicker or implausible saturated colors.
- [ ] Support OSM `MultiPolygon` shells and interior rings, concave polygons, and buildings crossing the requested bbox. Current proxy geometry takes only the first outer ring and centroid-filters it.
- [ ] Decide and test how to handle OSM ways without `height` or `building:levels`, units, malformed values, and non-building features. Current fallback is 3 m per level and otherwise raises.
- [ ] Make OSM proxy materials use sampled orthophoto appearance consistently with PLATEAU palette materials, rather than relying on a separate flat/material path.
- [ ] Add stable adjacency variation tests: neighboring untextured PLATEAU buildings and OSM proxies must not collapse to one identical color; same inputs and seed must reproduce identical outputs.

## Renderer integration

- [ ] Confirm renderer uses each building's palette index for untextured materials while leaving source GLB texture maps intact.
- [ ] Check material arrays, meshes without `_BATCHID`/feature IDs, multiple primitives, shared materials, and GLB texture color spaces.
- [ ] Add a lightweight integration fixture with one textured PLATEAU feature, two untextured PLATEAU features, and one OSM proxy in a single manifest.
- [ ] Render a Ryogoku preview and inspect it against the orthophoto. Specifically check for white/gray blank buildings, repeated adjacent colors, displaced models, missing facade texture, duplicate OSM/PLATEAU geometry, and seams at the edge of the coverage area.
- [ ] Keep rendering deterministic and avoid adding Cesium ion or runtime Cesium dependencies.

## Reproduction and verification

- [ ] Recover or recreate the ignored source assets and video references described in [handover.md](handover.md); do not assume the two MP4s are tracked in this repository.
- [ ] Reproduce both reference shots: `plateau-ryogoku-social.v0.0.6.mp4` and `asakusa-to-ryogoku-aerial-walk.v0.0.7.mp4`, then compare the appearance layers independently.
- [ ] Run Python pipeline unit tests and renderer build/unit tests after fixing the known centroid test gap. Run the video E2E only for the affected target, under the repository's resource limits.
- [ ] Update `packages/README.md` and the relevant `geo-video-3d-buildings` skill with behavior verified in code and rendered previews.
