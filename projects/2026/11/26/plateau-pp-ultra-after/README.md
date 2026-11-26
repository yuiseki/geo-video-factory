# PLATEAU++ ultra: after

世界モデル (`packages/pipeline/world_model/`) の改善を、`projects/2026/11/26/plateau-pp-ultra-before/` と同じ 8 か所、同じ視点で描いて比べるプロジェクトです。
場所、場面の作り方、視点は before のもの (`before.py` の `render_area`、`render_views.py`) をそのまま使い、違いは改善の引数だけにしています。

## 作り方

```sh
python projects/2026/11/26/plateau-pp-ultra-after/atlas_after.py              # 6 か所のアトラス (写真の置き直しなし)
projects/2026/11/26/plateau-pp-ultra-after/shibuya_atlases.sh                 # 渋谷の CC0 アトラスを quality.png 付きで作り直す
OVERPASS_URL=<自前の Overpass> python projects/2026/11/26/plateau-pp-ultra-after/after.py [名前 ...]
python projects/2026/11/26/plateau-pp-ultra-after/compare.py                  # out/compare_<day|night>.jpg
```

リポジトリのルートから、`packages/pipeline` の Python で流します (ホストの資源制限に従う。アトラスは 1 つ最大 20 GB)。`blender` が要ります。`out/` と `work/` は使い捨てで、git の対象外です。

## 入れた改善 (レビューの伸び代との対応)

どれも共通の道具に、既定を変えない引数として入れました。before は既定のまま描くので、同じコードから before も描き直せます。

| 伸び代 | 入れたもの | 引数 |
|---|---|---|
| 1. 焼き込みを生かす | `pp_scene.py` が、glTF の読み込みが組んだ配線 (窓の模様 x 壁の頂点色、屋根の写真) を、照明のかからない色として描く。夜は窓の発光を足す | `--baked-look`、`--windows=1` |
| 2. 観測の質で混ぜる | `build_atlas.py` が `quality.png` (いちばん良く見た写真で、アトラス 1 画素の辺に何画素かかるか) を書き、`pp_scene.py` がそれで不透明度を滑らかに決める | `--atlas-fade` |
| 4. 置けない写真を置かない | `photo_place.py` と `skyline_match.match_cost` が、空との境界線の列が足りない写真を拒む。after のアトラスは、before の基準写真のうちコスト 0 (境界線なし) のものを外して作る | `--min-sky`、`atlas_before.py --min-cost=0.05` |
| 5. 路面と街路 | `pp_scene.py` が、古びたアスファルト (夜は濡れる) と、OSM の塗装のある横断歩道の縞を置く。横断歩道は `world_model/osm_crosswalks.py` が自前の Overpass から取り、共有キャッシュに置く | `--streets=<crosswalks.json>` |

3 (写らなかった面を同じ建物の繰り返しで埋める) は、まだ入れていません。`--atlas-fade` で、写らなかった面は焼き込んだ PLATEAU++ (窓の模様) が透けて見えるようになったので、平均の 1 色で塗られることはなくなりました。

## 結果 (`out/compare_<day|night>.jpg`)

- 1 の効果がいちばん大きい。before で黒い壁に窓だけが光っていた補完の建物 (羽村の全域、各地の PLATEAU に無い建物) が、昼は壁の色と窓の模様、夜は灯る窓として出る。テクスチャの無い PLATEAU の面の灰色も、焼き込んだ壁の色になった。
- 5 で、目の高さの画に路面の質感と横断歩道が入った (渋谷で 1,371 本の縞)。夜の路面は濡れて暗い。
- 2 と 4 は、写真で埋まった面がもともと 0〜6% しかないので、画ではほとんど見分けられない。
- 渋谷は、PLATEAU の元のテクスチャと CC0 写真の地面が全面を覆っているので、before とほぼ同じ (画素差の平均 0.04〜6.3)。改善が効くのは、テクスチャや写真の無い所。

## 未解決

- 写真が少ない場所では、写真を足すことより、写真を正しく置けることのほうが先の課題。境界線の無い写真を外すと、1 か所に 1〜2 枚しか残らない。レビューの 4 にある、建物の垂直の角と消失点で置く方法が次の候補。
- 街灯 (`buildings/street_lights.py`) は、PLATEAU の道路 LOD3 の歩道がある所でしか置けないので、まだつないでいない。
- PLATEAU の写真のテクスチャは、近くで見るとぼやける。
