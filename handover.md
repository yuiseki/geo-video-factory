# Handover: PLATEAU appearance and OSM building proxies

## Goal

Continue the work on `feat/plateau-appearance-osm-proxies`. The target behavior is the part that made these Ryogoku trial videos look convincing:

1. PLATEAU buildings that have usable facade textures should render those original textures.
2. Untextured PLATEAU buildings should receive stable facade colors inferred from the GSI orthophoto, with deterministic variation so adjacent buildings do not become an identical row.
3. Buildings missing from PLATEAU should be filled from OpenStreetMap footprints and height tags, converted into the same local GLB tile / manifest shape that the renderer already loads.

The request is to implement the reusable pipeline and renderer in `packages/`, not to turn the trial project into the product implementation. Use TDD: write/fix a focused failing test before changing behavior.

## Reference work and design decisions

The motivating outputs are `plateau-ryogoku-social.v0.0.6.mp4` and `asakusa-to-ryogoku-aerial-walk.v0.0.7.mp4`, produced from trial code in `projects/trials/plateau/plateau-direct-experiment/`. Their source videos and much of the trial tree are ignored by Git (`projects/**/*.mp4` and `projects/trials/**/*`); they may exist only in the current workspace and are not guaranteed to be available to a fresh checkout. The trial README records the visual rationale and parameters. Read it before changing the design:

- `projects/trials/plateau/plateau-direct-experiment/README.md`
- `projects/trials/plateau/plateau-direct-experiment/page/plateau-direct.js`
- `projects/trials/plateau/plateau-direct-experiment/harmonize_fallback.py`
- `projects/trials/plateau/plateau-direct-experiment/optimize_glb_adaptive.py`
- Shot definitions: `shots/ryogoku-social-v005.json`, `shots/asakusa-to-ryogoku-v007.json`
- Trial logs for v0.0.6 and v0.0.7, if present locally.

Important visual details from the trial implementation:

- v0.0.6 uses glTF `_BATCHID` to vary appearance by building, not only by material. A deterministic seed incorporates the material identity so different tiles do not repeat the same pattern. Existing textured color variation is retained; low-information/near-gray facade areas receive stronger procedural treatment.
- Procedural facade detail was coordinate-fixed: approximate floor bands, windows, and rooftop seams. It must not shimmer from frame to frame. These details are a visual estimate, not recovered building truth.
- The v0.0.7 camera tracks from Asakusa along the Sumida river via Kuramae to Ryogoku while staying within building coverage. This is useful visual context, but this handover task is specifically about the reusable building pipeline.
- The trial used fixed local models and no Cesium ion runtime. Preserve that property.

## Current branch state

- Branch: `feat/plateau-appearance-osm-proxies`
- Test-first specification commit: `2d8b206 test: specify PLATEAU building appearance and OSM proxies`
- Current implementation commit: `805d8d9 feat: add PLATEAU appearance and OSM proxy pipeline`
- `.vscode/settings.json` is intentionally part of the implementation commit per the owner's standing instruction.
- The implementation commit was pushed, but the full Python suite has not been verified after the latest edits. Do not infer green CI from the renderer build/unit pass.

## Current package implementation

### Data preparation

`packages/pipeline/plateau_3d.py`:

- Selects intersecting leaf 3D Tiles content for a WGS84 bbox.
- Parses b3dm/GLB content, extracts GML IDs and RTC centers, preserves source texture data, and writes a local `geo-video-factory.plateau-3d/1` manifest with GLB tiles.
- Resizes embedded GLB textures; rejects unsupported transforms and external image paths rather than silently producing broken assets.
- CLI accepts `--orthophoto`, `--osm-geojson`, and `--seed` in addition to tile URL/bbox/output options.

`packages/pipeline/building_appearance.py`:

- `sample_polygon_color()` samples a polygon region from the orthophoto.
- `assign_facade_colors()` produces stable, varied colors and preserves entries marked textured.
- `infer_glb_facade_colors()` maps GLB feature/batch IDs to inferred orthophoto color and skips detected textured IDs.
- `apply_orthophoto_palette()` writes per-tile `facade_colors` in manifest ID order.
- `build_osm_proxy_tiles()` extrudes OSM polygons to GLB with height from `height` or `building:levels` (3 m/floor), and appends a renderer-compatible proxy tile to the existing manifest.
- `extract_glb_feature_centroids()` and `_point_in_ring()` exist, but centroid metadata is not yet wired into the PLATEAU manifest or proxy overlap filtering.

### Renderer

`packages/renderer/src/page/plateau-buildings.ts` loads the local manifest and GLBs with Three.js/DRACO in a MapLibre custom 3D layer, transforms ECEF/RTC positions into the map frame, and calls `applyBuildingAppearance()`.

`packages/renderer/src/page/plateau-materials.ts` retains materials with texture maps. For untextured material meshes with a batch/feature attribute, it applies the manifest palette through a shader lookup. Meshes without feature IDs get a stable seeded tint fallback. The renderer uses standard Three.js materials in MapLibre's shared WebGL context; there is no Cesium ion path.

## Known gaps (do these first)

1. **Known test/implementation mismatch:** `test_osm_proxy_skips_buildings_whose_footprint_contains_a_plateau_building_centroid` expects OSM/PLATEAU overlap suppression. The helper for centroid extraction and point-in-ring is present, but `build_osm_proxy_tiles()` does not yet load/use those centroids. This test is expected to fail until it is wired. Implement that test first and then make it pass.
2. The `plateau_3d.py --osm-geojson` CLI currently invokes `build_osm_proxy_tiles()` without `plateau_ids`, even though the function can exclude explicit IDs. Wire overlap and ID metadata end-to-end.
3. `infer_glb_facade_colors()` currently considers a feature textured if it appears in a textured primitive; a mixed textured/untextured feature can therefore miss facade color assignment. Improve this carefully without recoloring original texture maps.
4. The OSM generator currently handles a Polygon outer ring or only the first ring of each MultiPolygon polygon. It does not model holes and its centroid-based bbox filter can drop intersecting edge buildings.
5. Current PLATEAU color sampling from GLB vertices uses a feature centroid (not a full footprint mask). This can sample a road, shadow, or roof equipment; compare against the trial's polygon-based sampling and improve if feasible.
6. The proxy's palette/material path and the PLATEAU palette path need a shared appearance contract; verify OSM proxy colors actually reach the renderer and are not overwritten by the generic fallback shader.
7. The production README describes the base 3D building pipeline but is not yet sufficient documentation for the new appearance and OSM pipeline.

## Tests and resource safety

Relevant suites:

- `packages/pipeline/tests/test_building_appearance.py`
- `packages/pipeline/tests/test_plateau_3d.py`
- `packages/renderer/test/plateau-materials.test.ts`
- `packages/renderer/test/plateau-coordinates.test.ts`

Test fixtures use synthetic images and GLBs; begin with these focused tests. The last renderer build and non-E2E unit run passed (40 tests), but that does not verify Python integration or visual appearance. Follow repository rules for data-consuming runs: execute under `systemd-run --user --scope -q -p MemoryMax=8G -p MemorySwapMax=0 -p CPUQuota=400% -- ...`. Keep downloads to three workers. Use a single targeted video E2E when visual integration is ready; inspect its frames for duplicate buildings, blank/white facades, same-color neighbors, missing textures, and alignment with the orthophoto.

Potential verification commands (apply the resource scope to test/build/render commands as required by the workspace rules):

```sh
python3 -m unittest discover -s packages/pipeline/tests -p 'test_building_appearance.py' -v
python3 -m unittest discover -s packages/pipeline/tests -p 'test_plateau_3d.py' -v
cd packages/renderer && npm run build
cd packages/renderer && node --test --test-skip-pattern='E2E' dist/test/plateau-materials.test.js dist/test/plateau-coordinates.test.js
```

Do not assume the video references or trial inputs are in a fresh clone: check their availability first. The trials are intentionally ignored to avoid adding large derived assets and videos to the package branch.
