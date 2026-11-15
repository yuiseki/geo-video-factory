# TODO: PLATEAU building appearance and OSM proxies

This is the implementation checklist for the work on branch `feat/plateau-appearance-osm-proxies`. See [handover.md](handover.md) for the design context and known gaps. Keep changes test-first.

## Immediate correctness work

- [ ] Validate GLB spatial decoding across all real tile formats and both RTC variants. Node transforms and Draco decoding are implemented; three Ryogoku real tiles yielded feature centroids in the expected area. Add more real-data control points and verify incomplete or undecodable geometry cannot silently produce incorrect samples.
- [ ] Validate OSM deduplication with complete CityGML coverage and production OSM input. When `--citygml-geojson` is supplied, the pipeline uses the trial's >10% area overlap rule; otherwise it still falls back to the less complete centroid test.
- [ ] Make palette inference robust for partial texturing within one building. A building should keep actual source textures wherever present and receive inferred color only on genuinely untextured facade material/features. Current textured-feature detection can mark a whole feature textured from one textured primitive.
- [ ] Verify GLB batch/feature IDs against the PLATEAU versions encountered in the Ryogoku trial and retain correct ID order when writing `facade_colors`.
- [ ] Fix malformed or absent feature geometry handling and validate orthophoto bounds, image dimensions, and empty/degenerate footprints with clear errors.

## Fidelity and coverage

- [ ] Sample each actual building footprint's orthophoto pixels robustly (mask the polygon and ignore shadows/roads where possible). Current hull sampling is only trustworthy after node transforms and Draco geometry are decoded; see [handover.md](handover.md). Preserve a stable seed so repeated renders match.
- [ ] Estimate facade tone from roof/footprint color while reducing bright roof bias; keep neighboring untextured buildings visibly varied without random frame-to-frame flicker or implausible saturated colors.
- [ ] Validate proxy triangulation for complex real OSM multipolygons, holes, concave polygons, and bbox-crossing buildings; basic geometry support exists.
- [ ] Decide and test how to handle OSM ways without `height` or `building:levels`, units, malformed values, and non-building features. Current fallback is 3 m per level and otherwise raises.
- [ ] Make OSM proxy materials use sampled orthophoto appearance consistently with PLATEAU palette materials, rather than relying on a separate flat/material path.
- [ ] Add stable adjacency variation tests: neighboring untextured PLATEAU buildings and OSM proxies must not collapse to one identical color; same inputs and seed must reproduce identical outputs.

## Renderer integration

- [ ] Confirm renderer uses each building's palette index for untextured materials while leaving source GLB texture maps intact.
- [ ] Check material arrays, meshes without `_BATCHID`/feature IDs, multiple primitives, shared materials, and GLB texture color spaces.
- [ ] Add a lightweight integration fixture with one textured PLATEAU feature, two untextured PLATEAU features, and one OSM proxy in a single manifest.
- [ ] Render a Ryogoku preview and inspect it against the orthophoto. Specifically check for white/gray blank buildings, repeated adjacent colors, displaced models, missing facade texture, duplicate OSM/PLATEAU geometry, and seams at the edge of the coverage area.
- [ ] Fix the obviously saturated purple/green buildings visible in the Ryogoku real-data preview. Identify source material, palette, and texture causes separately before claiming appearance parity with the trial.
- [ ] Port the trial's adaptive atlas optimization and textured-material chroma/brightness treatment, and run the real-data render within the host resource limits. Unoptimized 422-tile rendering exhausted the browser; the trial's optimized assets rendered successfully.
- [ ] Keep rendering deterministic and avoid adding Cesium ion or runtime Cesium dependencies.

## Reproduction and verification

- [ ] Recover or recreate the ignored source assets and video references described in [handover.md](handover.md); do not assume the two MP4s are tracked in this repository.
- [ ] Reproduce both reference shots: `plateau-ryogoku-social.v0.0.6.mp4` and `asakusa-to-ryogoku-aerial-walk.v0.0.7.mp4`, then compare the appearance layers independently.
- [ ] Add transform tests for both RTC + local-delta b3dm GLBs and RTC-zero + ECEF node-transform GLBs, plus a known geographic control point. Run Python pipeline unit tests and renderer build/unit tests; run only the affected video E2E target under the repository's resource limits.
- [ ] Update `packages/README.md` and the relevant `geo-video-3d-buildings` skill with behavior verified in code and rendered previews.
