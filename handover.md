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

## Additional handoff: trial data and exact visual parameters

The values below were recovered from the trial scripts, generated manifests, and render logs in the current workspace. The `projects/trials/plateau/**` source assets are ignored and may be absent in another checkout. Treat this section as recorded provenance for those runs, not as a guarantee that the live endpoints still serve identical content.

### PLATEAU source URLs, regions, and height correction

Both videos use the 2025 Tokyo textured LOD2 catalogue index:

`https://api.plateauview.mlit.go.jp/datacatalog/3dtiles/13-bldg-lod2-texture-2025/tileset.json`

The catalogue's relevant partition roots found in the saved manifests are:

- Chuo-ku (13102): `https://assets.cms.plateau.reearth.io/assets/09/83a3f6-6605-477c-84dc-a973008b5a27/13102_chuo-ku_pref_2025_citygml_1_op_bldg_3dtiles_13102_chuo-ku_lod2/tileset.json`
- Sumida-ku (13107): `https://assets.cms.plateau.reearth.io/assets/9d/d19b09-1e4d-4315-804b-d62c0124f1e3/13107_sumida-ku_pref_2025_citygml_1_op_bldg_3dtiles_13107_sumida-ku_lod2/tileset.json`
- Taito-ku (13106) was served in the recorded Ryogoku manifest as individual GLBs, not a `tileset.json`. Example source URL: `https://assets.cms.plateau.reearth.io/assets/75/76c6bc-df54-4bf4-a869-b513526b5bd2/13106_taito-ku_city_2025_citygml_1_op_bldg_3dtiles_lod2/18/232853/39523_bldg_Building.glb`. The trial catalogue walker selected these by ward code alongside the Chuo/Sumida tilesets.

| Render | Source center | Half extents (lon, lat) | Bbox [west, south, east, north] | Runtime loaded tiles | PLATEAU IDs / fallback counts |
|---|---:|---:|---:|---:|---|
| `plateau-ryogoku-social.v0.0.6.mp4` | `[139.7882, 35.6948]` | `[0.008, 0.007]` | `[139.7802, 35.6878, 139.7962, 35.7018]` | 153 | 7,881 matched detail IDs; 1,340 PLATEAU footprint fallbacks; 742 OSM supplements |
| `asakusa-to-ryogoku-aerial-walk.v0.0.7.mp4` | `[139.7918, 35.7028]` | `[0.016, 0.020]` | `[139.7758, 35.6828, 139.8078, 35.7228]` | 422 | manifest reports 45,469 IDs across coverage; rendered detail log still reports 7,881 matched and 1,340 PLATEAU fallbacks; 742 OSM supplements |

The v0.0.6 region/counts are from `ryogoku-download-v002.log` and the v0.0.6 README/render log. The v0.0.7 region is from the later `prepare_tiles.py` configuration and its manifest. Do not interpret its 45,469 broad-area unique IDs as the number of feature IDs actually matched by that shot's older Ryogoku fallback data. The same local fallback GeoJSON was reused; it was prepared around Ryogoku, not regenerated to cover every block on the Asakusa route.

Both runs used `heightOffset: -39.0` metres in `page/plateau-direct.js`. This is a scene-wide empirical correction from ellipsoid height to the flat MapLibre raster plane, not a local terrain/geoid solution.

### GSI orthophoto and OSM acquisition

- Background raster style key: `seamlessphoto` (GSI seamless aerial imagery); map `dem: "gsi"`, with `hillshade: false`, `world: false`, and OSM labels enabled. The style fetches tiles for the camera viewport; it is not a single prebuilt mosaic file.
- For building footprint color estimates the trial used GSI XYZ `https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{z}/{x}/{y}.jpg` at **z=18**, cached individual 256 px tiles. Tiles were selected dynamically per footprint; there was no fixed rectangular mosaic boundary. PLATEAU roof color sampling was centered at `[139.7882, 35.6948]` and limited to a 1 km radius for the fallback-footprint dataset.
- Pixel selection used a polygon mask in tile pixel coordinates; valid pixels only had `max(R,G,B) > 20`. The representative roof color was the independent median of each RGB channel. There was no explicit shadow detector, road classifier, or pixel subsampling. Thus “orthophoto color” is a roof/footprint sample, not measured facade truth.
- OSM used `POST https://overpass.yuiseki.net/api/interpreter` with `[out:json][timeout:90]`, selecting `way[building]` and `relation[building]` in a bbox centered at `[139.7882, 35.6948]`, ±0.013° longitude and ±0.010° latitude, and `out geom`.
- The Ryogoku raw response had 17,341 elements: 17,334 ways and 7 relations. Common way tags included `building` (17,334), `building:levels` (1,528), and `height` (count not retained in the summary; examples include `height=8` for 両国国技館). Example retained source tags: `way/76187058 {building: stadium, height: 8, name: 両国国技館}`; `way/23995360 {building: yes, building:levels: 8, name: Shimojima 5}`. For proxy GLB, the feature ID is prefixed `osm-way-`.
- The hybrid preprocessing accepted numeric heights from 1–350 m; `height` (optional `m`/`米`) took precedence, otherwise `building:levels × 3 m`. It omitted polygons overlapping a PLATEAU footprint by more than 10% of the OSM footprint area, invalid ways, relations, and buildings without an accepted height. Ryogoku yielded 742 OSM proxies; 15,797 raw elements had no acceptable height, 795 were overlap-filtered, and 7 relations were skipped. Shimbashi yielded 286; 5,123 had no acceptable height, 489 overlap-filtered, and 24 relations skipped. These are preprocessing log counts, not counts from a live Overpass response today.
- The direct renderer's fallback GeoJSON contained 1,340 unrepresented Ryogoku PLATEAU footprints plus those 742 OSM proxies. Its shot spec sets `buildingOpacity: 0.74`.

### Shader-based procedural facade and texture treatment

The v0.0.5/v0.0.6 appearance pattern is generated at render time by `page/plateau-direct.js` using Three.js `material.onBeforeCompile`; it is not baked into GLB or written as a procedural image texture. It is coordinate-fixed in world space, so camera movement does not animate the pattern.

- Per-building base randoms use `_BATCHID` plus a material UUID seed. Material seed: start at 17, then for each UUID character `n = (n * 33 + charCode) % 100003`. GLSL hash is `fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453)`. The two building values are `hash(vec2(featureId + 0.37, seed))` and `hash(vec2(featureId * 1.71 + 5.3, seed * 0.61))`.
- Warm/cool tint colors are `(1.08, 0.96, 0.86)` and `(0.86, 0.96, 1.08)`. Brightness factor is `0.84 + random2 * 0.30`. Chroma is `max(rgb)-min(rgb)`; grayscale blend is `1-smoothstep(0.07, 0.19, chroma)`, then tint is blended at `graySurface * 0.78`. These thresholds are the trial's actual blend limits.
- Walls are selected from world-space normals with `smoothstep(0.58, 0.90, 1-abs(normal.z))`. The dominant horizontal world axis selects facade coordinates. Floor height is `2.9 + random * 0.65 m`; bay width is approximately `3.5 + random2 * 1.8 m` (window phase uses `3.4 + random2 * 1.7 m`). Window horizontal bounds are smooth transitions at 0.12–0.20 and 0.72–0.88; vertical bounds at 0.18–0.29 and 0.66–0.80. A floor band uses 0.06–0.13 of floor phase. Window glass ranges from `(0.045,0.065,0.075)` to `(0.14,0.17,0.18)` and is applied with a 0.52–0.76 random mix factor. Floor band darkening is 0.11.
- Roofs use near-horizontal normals (`smoothstep(0.72, 0.92, abs(normal.z))`), a world-space grid `6.5 + random * 2.5 m`, seam width thresholds 0.025–0.065, seam darkening 0.10, and randomized roof units darkened toward `(0.17,0.19,0.20)` at factor 0.32.
- Texture atlas analysis draws the image into 32×32 pixels, computes Rec.709 luma `(0.2126R + 0.7152G + 0.0722B)/255`, ignores alpha below 16, and measures mean, standard deviation, and share above luma 0.78. Brightness multiplier: 0.64 when bright share >0.42 or mean >0.74; else 0.78 when share >0.24 or mean >0.64; else 1.0. “Bland” material is flagged when standard deviation <0.105 and mean >0.28. Untextured base material colors whose max channel exceeds 0.45 are scaled so max equals 0.45. These values are the implementation's literal constants (there was no separate `materials.md` in the trial tree).

The broader v0.0.5/v0.0.6 method describes this as preserving colored photo areas and applying more procedural contrast to near-achromatic material. In the code path, `addProceduralFacade()` is installed for textured materials too; tint/glass/window modifications are attenuated by measured chroma. Do not describe it as “texture untouched” without qualifying that its original map is retained but may be darkened and shader-tinted.

### Orthophoto-to-facade fallback tone

`plateau-direct-experiment/harmonize_fallback.py` does use the same formula described in the earlier notes:

1. Convert sampled RGB to HSV.
2. `s = min(0.42, max(s * 1.12, 0.055))`.
3. `v = min(0.14 + 0.50 * (v ** 0.88), 0.52)`.
4. Convert back to RGB; retain the source color as `orthoColor`, and record `colorMethod` as GSI median with highlight compression.

The source roof RGB itself was sampled from PLATEAU/OSM footprint polygons as described above. It does not sample GLB vertices, remove shadows explicitly, or use height to alter color. The fallback is applied to PLATEAU buildings absent from the detailed tile IDs and OSM supplement buildings.

### Adaptive GLB texture optimization and encountered formats

`optimize_glb_adaptive.py` considers a tile near when its tile region intersects center ±0.003° longitude and ±0.0025° latitude. Near tile max dimension is 2048 px; all other selected tiles use 1024 px. Resizing uses Lanczos and WebP quality 88, method 3. It appends replacement compressed image bytes to the GLB and reuses geometry/UV buffers; Draco geometry is not decoded/re-encoded. The adaptive runs' saved Ryogoku v0.0.7 manifest had 2 tiles at 2048 and 420 at 1024; Shimbashi had 17 at 2048 and 171 at 1024. Per-render peak memory was not recorded in logs.

The saved Ryogoku v0.0.7 manifest has 422 tiles; aggregate extension counts (a tile may have multiple extensions) were: `KHR_draco_mesh_compression` 422, `EXT_texture_webp` 394, `EXT_mesh_features` 346, `EXT_structural_metadata` 346, and `CESIUM_RTC` 76. Inspection of one saved tile from each partition confirmed:

- Chuo and Sumida leaf payloads were `b3dm` containing GLB; observed GLB attributes include `_BATCHID`, `POSITION`, `NORMAL`, `TEXCOORD_0`, and sometimes `COLOR_0`. The b3dm batch table contains `gml_id`; `RTC_CENTER` is commonly present.
- Taito payloads were direct `.glb`; observed attributes include `_FEATURE_ID_0`, `POSITION`, `NORMAL`, and `TEXCOORD_0`; extensions include `EXT_mesh_features` and `EXT_structural_metadata`.
- The sampled GLBs had one mesh with multiple primitives and two materials, one with a base-color texture; the pipeline must not assume one primitive/material or only `_BATCHID`.
- The direct renderer supports Draco via `DRACOLoader`; sampled 2025 payloads required `KHR_draco_mesh_compression`. `EXT_texture_webp` appeared in the source. The existing package parser has separate support concerns for extension feature IDs and structural metadata; verify the supported ID-reading cases with real fixture-derived tests before claiming complete compatibility.

### Shot settings and measured render logs

Both specs use `1280×720`, 24 fps, `base: seamlessphoto`, `dem: gsi`, `world: false`, `hillshade: false`, `osmLabels: true`, `buildings: assets/ryogoku/fallback-harmonized.geojson`, `buildingOpacity: 0.74`, and `directModels: ryogoku`. Both specify smooth interpolation and PLATEAU/OSM credits.

v0.0.6 `shots/ryogoku-social-v005.json` has three shots (4.8 s, 4.6 s, 5.6 s; total 15.0 s):

1. `[139.79255,35.69625]`, zoom 16.05, pitch 62, bearing -28 → `[139.79305,35.69648]`, zoom 16.62, pitch 66, bearing -18.
2. `[139.79305,35.69648]`, zoom 16.62, pitch 66, bearing -18 → `[139.79352,35.69646]`, zoom 16.58, pitch 64, bearing -7.
3. `[139.79335,35.69655]`, zoom 16.25, pitch 62, bearing -7 → `[139.7918,35.6962]`, zoom 15.75, pitch 56, bearing 3.

v0.0.7 `shots/asakusa-to-ryogoku-v007.json` has four smooth tracking segments, total 20.6 s: 5.2 s from `[139.7977,35.7110]` (16.10/63/168) to `[139.7957,35.7085]` (16.18/65/170); 5.0 s to `[139.7920,35.7041]` (16.12/65/173); 5.0 s to `[139.7917,35.6994]` (16.10/64/174); 5.4 s to `[139.7930,35.6968]` (16.58/66/152). Tuple values are `[center lon/lat]`, then `zoom/pitch/bearing`. Labels mark Asakusa, Sumida River, Kuramae, and Ryogoku; the last shot shows “浅草から約2km”.

Recorded horizontal render benchmarks from the logs:

| Render | Frames | Wall time | Models | GL calls | Triangles | Cesium requests |
|---|---:|---:|---:|---:|---:|---:|
| v0.0.6 Ryogoku social | 360 | 48 s | 153 | 318 | 1,017,708 | 0 |
| v0.0.7 Asakusa–Ryogoku | 495 | 148 s | 422 | 1,091 | 2,657,560 | 0 |

The corresponding vertical logs record 48 s for v0.0.6 and 141 s for v0.0.7. These are render-loop elapsed times from logs, not controlled benchmarks. Peak memory was not captured, so do not invent a memory figure.
