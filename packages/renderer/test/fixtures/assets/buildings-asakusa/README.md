# Asakusa PLATEAU E2E fixture

This fixture contains the 16 PLATEAU LOD2 textured building tiles selected for
`139.795 35.712 139.799 35.716` from the 2025 Taito City dataset. The tiles and
their source URLs, SHA-256 hashes, building IDs, and RTC values are recorded in
`plateau/manifest.json`. Texture images are optimized to a maximum edge of 512 px.

- Dataset: [Project PLATEAU, Taito City 2025](https://www.geospatial.jp/ckan/dataset/plateau-13106-taito-ku-2025)
- Tileset: <https://api.plateauview.mlit.go.jp/datacatalog/3dtiles/13106-bldg-lod2-texture-2025/tileset.json>
- Data use: [Project PLATEAU data terms](https://www.mlit.go.jp/plateau/site-policy/)
- Regenerate from the repository root:

  ```sh
  python3 packages/pipeline/plateau_3d.py \
    'https://api.plateauview.mlit.go.jp/datacatalog/3dtiles/13106-bldg-lod2-texture-2025/tileset.json' \
    --bbox 139.795 35.712 139.799 35.716 \
    --out packages/renderer/test/fixtures/assets/buildings-asakusa/plateau \
    --max-texture-dimension 512 --workers 1 --seed buildings-asakusa-e2e-v1
  ```

The generated video is rendered by the E2E test from these committed fixtures;
no video or source asset is read from `tmp/`.
