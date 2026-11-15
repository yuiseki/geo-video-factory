# 地名、位置、経路を調べる (yuiseki.net の OSM サービス)

台本の地名を座標にする、川や路線の形を線で引く、2 地点の経路を描く、現代の地名を地図に重ねる。そのために、OpenStreetMap のデータで動く次の 4 つのサービスを使える。どれも OSM の公開サーバーではなく、作者が自分で立てているもの。

| サービス | URL | 使いどころ |
|---|---|---|
| Nominatim | `https://nominatim.yuiseki.net` | 地名から座標と範囲 (`/search`)、座標から地名 (`/reverse`) |
| Overpass API | `https://overpass.yuiseki.net/api/interpreter` | 川、路線、境界などの地物と形状 |
| Valhalla | `https://valhalla.yuiseki.net` | 徒歩、自転車、車の経路 (`/route`) |
| ベクトルタイル | `https://tile.yuiseki.net/data/v3.json` | OpenMapTiles 形式。ショットの `osmLabels: true` が現代の地名に使う |

Nominatim と Overpass のデータは 2025-09-14 時点で止まっている (2026-11-15 に確かめた。Nominatim は `/status?format=json` の `data_updated`、Overpass は `/api/timestamp`)。それより後の開業、改名、廃止は入っていない。Valhalla の経路データは `/status` の `tileset_last_modified` が 2025-10-05 で、元の OSM の時点は応答から分からない。ベクトルタイルの時点も応答には出ないので、新しい施設や改名が絡むときは地図で目で確かめる。画面や概要欄に「現代の地名」と出すときは、いつ時点のものかが分かるようにする。

出典は「© OpenStreetMap contributors」(データは ODbL)。タイルを使うときは「OpenMapTiles」も。`osmLabels` は自動で出す。

## Nominatim

```bash
curl -s 'https://nominatim.yuiseki.net/search?q=上野&format=jsonv2&limit=5&countrycodes=jp'
curl -s 'https://nominatim.yuiseki.net/reverse?lat=35.3615&lon=138.7274&format=jsonv2&zoom=10'
```

- OSM の駅の名前には「駅」が付かない (`name=上野` + `railway=station`)。「上野駅」で探すと、駅の敷地 (`landuse=railway`) や、名前に「駅」の付いた通路が先に返る。駅の点が欲しいなら、駅名から「駅」を外して探し、`category` と `type` で駅を選ぶか、Overpass で `railway=station` を引く。
- `importance` は同名の候補から選ぶ手がかりにだけ使う。主題や隣の駅を、重要度が低いという理由で落とさない。
- 範囲 (`boundingbox`) はカメラの寄りと引きの目安になる。

## Overpass API

```bash
curl -s https://overpass.yuiseki.net/api/interpreter \
  --data-urlencode 'data=[out:json][timeout:60];way["waterway"="river"]["name"="隅田川"];out geom;'
```

- `out geom` で各 way の座標列が返る。ショットの `line` にするときは way をつないで向きをそろえ、上流から下流へ描く。描く前に点を間引く。
- `[timeout:N]` は小さめ (数十〜数百秒) にする。サーバー側の上限と同じ値を要求すると、軽いクエリでも「The server is probably too busy」で断られる。この表示はレート制限や混雑の印ではない。
- 鉄道は `railway=rail` の線、駅は `railway=station`、行政界は `boundary=administrative` と `admin_level` で引く。

## Valhalla

```bash
curl -s --get https://valhalla.yuiseki.net/route --data-urlencode \
  'json={"locations":[{"lat":35.7138,"lon":139.7774},{"lat":35.7148,"lon":139.7967}],"costing":"pedestrian","units":"kilometers"}'
```

- 経路の形は `trip.legs[].shape` に、精度 6 の encoded polyline で入る。デコードして `line` にする。
- `costing` は `pedestrian`、`bicycle`、`auto` など。鉄道の線形は返らない。電車の移動を見せるなら Overpass の線路を使い、徒歩の経路を鉄道の線のように描かない。
- `/height` (標高) は使わない。標高データが入っておらず、`null` が返った。標高や断面には DEM タイルを使う ([dem-sources.md](../../geo-video-3d-terrain/references/dem-sources.md))。

## 使うときの決まり

- 1 本ずつ順に投げ、まとめて大量に投げない。結果は作業ディレクトリに保存し、同じ問い合わせを繰り返さない。どのサービスに、いつ、何を問い合わせたかを素材の記録に残す。
- 取れた座標と形は、地理院の写真の上に重ねて目で確かめる。名前が同じ別の場所、古いデータ、つなぎ損ねた線は、引いてから気づくことが多い。
- サービスが応答しないときは、OSM の公開サーバー (nominatim.openstreetmap.org、overpass-api.de など) へ黙って切り替えない。利用規約と負荷の配慮が要るので、利用者に相談する。
