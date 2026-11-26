# 03. 歩く人間にとって、箱根越えは足柄峠より1.6倍速い

![第1章 扉](images/03_ch1_question.jpg)

![徒歩最小経路（箱根）と足柄峠まわりの比較](images/04_walk_hakone_vs_ashigara.jpg)

## 事実の要点
- 国土地理院の20 m格子 DEM 上で Tobler の歩行関数を使い、小田原宿〜三島宿の最小歩行時間経路を計算すると、**箱根越え（28.271 km、6.317 時間）**が選ばれる。
- 古代の官道であった北の **足柄峠まわり（関本・御殿場経由）** は **47.96 km、10.085 時間**（最高標高 749.1 m）となり、箱根最小経路の **1.5965 倍（約1.60倍）** の時間がかかる。
- 歴史的にも、古代は足柄路が主経路だったが、延暦19（800）年〜21（802）年の富士山噴火で足柄路が埋没した際、延暦21年5月に迂回路として箱根路（筥荷途）が開削された（『日本紀略』）。

## 計算条件と断り書き
- 標高は現代の国土地理院 DEM（芦ノ湖は水面マスク 17,623 セルで通行不可に設定）。
- 歩行関数（Tobler）は勾配のみを考慮し、路面状況や天候は含まない。

## 出典
- 地形データ: [国土地理院 地理院タイル一覧](https://maps.gsi.go.jp/development/ichiran.html)（標高タイル）
- 路線データ: [OpenStreetMap Relation 5185746](https://www.openstreetmap.org/relation/5185746) (ODbL)
- 史実資料: [足柄峠 - Wikipedia](https://ja.wikipedia.org/wiki/%E8%B6%B3%E6%9F%84%E5%B3%A0)、[日本紀略 - Wikipedia](https://ja.wikipedia.org/wiki/%E6%97%A5%E6%9C%AC%E7%B4%80%E7%95%A5)、[文化庁 日本遺産「箱根八里」](https://japan-heritage.bunka.go.jp/ja/stories/story058/)
