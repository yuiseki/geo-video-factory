# PLATEAU++ ultra: before

世界モデル (`packages/pipeline/world_model/`) の今の出力を、渋谷以外も含めた 8 か所で記録するプロジェクトです。
改善の試行錯誤は `projects/2026/11/26/plateau-pp-ultra-after/` で行い、ここの出力と並べて比べます。
ここでは何も改善しません。

## 場所

`areas.json` に置いています。範囲は中心から 350 m 四方です。

| 名前 | 場所 | 写真 |
|---|---|---|
| shibuya | 渋谷スクランブル交差点 | CC0 の写真のアトラスと地面がある (liminal プロジェクトの `work/shibuya_world_v1`) |
| shinjuku | 新宿駅東口 | CC0 写真の集まりはあるが、世界モデルは無い |
| ginza | 銀座四丁目交差点 | 同上 |
| marunouchi | 東京駅丸の内口 | 同上 |
| akihabara | 秋葉原 中央通り | 同上 |
| asakusa | 浅草 雷門 | 同上 |
| ueno | 上野駅前 | 同上 |
| hamura | 羽村駅 | 写真なし、PLATEAU のタイルも無い |

## 作り方

```sh
OVERPASS_URL=<自前の Overpass> python projects/2026/11/26/plateau-pp-ultra-before/before.py [名前 ...]
python projects/2026/11/26/plateau-pp-ultra-before/sheet.py
```

リポジトリのルートから、`packages/pipeline` の Python で流します (ホストの資源制限に従う)。`blender` が要ります。

1. PLATEAU++ v0.1.0 を、版付きの共有キャッシュから使う (`plateau_pp.cached`)。
2. 地面の高さは、地理院の DEM に楕円体高との差 36.7 m を足したもの。
3. `world_model/pp_scene.py` で昼と夜の場面を作る。渋谷だけは、CC0 のアトラス 5 つと地面を重ねる。
4. `render_views.py` で 3 つの視点から描く。上空から斜め (300 m 離れて 250 m 上)、屋上の高さ (90 m 離れて 45 m 上)、歩く人の目の高さ (1.6 m) です。目の高さの地点は、中心から 80 m 以内で、指定の方向にいちばん遠くまで見通せる所を当たり判定で選ぶ。
5. `sheet.py` が `out/sheet_day.jpg` と `out/sheet_night.jpg` にまとめる。

`out/` は使い捨てで、流すたびに作り直します。

## 見るところ (レビューの 5 つの伸び代)

1. `pp_scene.py` が PLATEAU++ v0.1.0 の焼き込みを生かしていない。壁の頂点色 (`COLOR_0`) と夜の窓 (`emissiveTexture`) を捨て、最初に見つかった画像だけを発光させる。昼なのに黒い壁に窓が光る建物や、テクスチャの無い面の灰色 (0.5, 0.5, 0.52) として出る。
2. 写真のアトラスが、見た写真の枚数 (`seen.png`) を 0.05 で二値に切って重なる。浅い角度で 1 枚だけかすめた壁が、引き伸ばされた縞模様になる (渋谷)。
3. 写真に写らなかった面は、`--fill=mean` で平均の 1 色に塗られる。
4. 位置合わせ (`photo_place.py`) が空と建物の境界線しか見ないので、空の見えない路地や夜の写真が落ちる。
5. 地面は地理院の写真か一様な灰色の板で、横断歩道、路面の質感、街灯などが無い。
