# world_model (渋谷): 無人の渋谷の世界モデルのショットと編集

世界モデルの道具 (写真から建物の見た目を逆算する、Blender で描く、フレームをつなぐ) は
`packages/pipeline/world_model/` にある。手法と分かったことはそちらの README.md。ここには渋谷のものだけを置く。

```
magic_shots.py              渋谷のカメラワーク (見上げて回る、ドリーズーム、ビルに飛び込んで出る、周回 ...)
edit_globe_to_crossing_*.json   地球から交差点までの編集表 (edit_frames の形式。ディレクトリは $WORLD などの変数)
photo_sources.tsv      v0.2 の映像の壁と地面に入りうる写真の出典
```

描き方 (packages/pipeline から):

```
blender -b --factory-startup -P world_model/pp_scene.py -- <out.blend> <PLATEAU++ manifest.json> --atlas=... --ground=...
bash world_model/render_shot_wd.sh <scene.blend> <out dir> <この magic_shots.py> <shot> <first> <last>
python -m world_model.world_camera <この magic_shots.py> <scene tris.npz>      # 壁に近づきすぎるショットを探す
WORLD=... FLYOUT=... MACOUT=... bash world_model/render_edit.sh <edit.json> <out dir>
```

座標は (139.7005, 35.6595) を原点とする東、北、上のメートル、高さは PLATEAU の楕円体高 (交差点の地面 52.8)。

- 地図 (MapLibre) の最後のカメラを Blender に換算して継ぐ (maplibre_eye) と、縮尺が合わなかった。
  描き比べて地図側のズームを合わせた (18.7 で計算したものに 19.3)。理由は確かめていない。
- 渋谷スクランブルスクエアの屋上は高さ約 230 m、上端の中心は局所座標の (175, -123)。渋谷ストリームの塔は
  OSM の外形の中心ではなく東の端 (270, -272) に立つ。真上から突っ込むときは塔の位置に合わせる。
- 真っ直ぐ QFRONT へ向かう線は渋谷スクランブルスクエアを通る。避けて南を回るか、そこから出る。

## 写真の来歴

- photo_sources.tsv は、v0.2 の映像の壁と地面に入りうる写真 126 枚の出典 (ライセンス、作者、題名、URL)。
  出典の一覧 (research/*manifest.json) とファイルの SHA-1 で照合し、一覧にない写真は Wikimedia Commons を
  SHA-1 で引いた。Commons の題名でしか照合できなかった写真は found_by にそう書いてある。
- 取得元は Wikimedia Commons と Openverse (その先の Flickr、rawpixel)。出典の一覧は research/ の
  photos_manifest.json、photos_buildings_night_manifest.json、photos_qfront_manifest.json、
  photos_crossing_night_cc0_manifest.json、tokyo_cc0/、tokyo_ccby/。assets/photos の 2,324 枚はすべてこのどれかと
  パスか SHA-1 で照合でき、食い違いは無かった (2026-11-25)。
- v0.2 の 126 枚のうち CC BY-SA は 52 枚。これらは packages/pipeline/photos/photo_blocklist.tsv に載っていて、
  次に作るテクスチャには入らない。
