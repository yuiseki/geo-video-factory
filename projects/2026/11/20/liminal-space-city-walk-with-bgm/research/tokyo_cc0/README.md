# 東京主要エリア 街並み写真カタログ

ライセンス方針: **CC0 or public domain (no attribution required)**。目視検品済みのカタログです。
実画像ファイルは各 `local_path`（`.gitignore` 対象）に保存しています。

- **総枚数**: 1380 枚（9 エリア）
- **SfM / 3DGS 投入可能バケット（同一スポット×同一時間帯 >= 10枚）**: 30 件
- **ライセンス内訳**: {"CC0": 1327, "CC0 1.0": 9, "Public domain": 44}
- **種別内訳**: {"landmarks": 965, "streets": 415}
- **時間帯内訳**: {"day": 813, "dusk": 222, "morning": 65, "night": 280}
- **季節内訳**: {"autumn": 272, "spring": 423, "summer": 341, "unknown": 15, "winter": 329}

## エリア別サマリー

| エリア | 合計 | ランドマーク | 通り | 朝 | 昼 | 夕 | 夜 | 春 | 夏 | 秋 | 冬 | マニフェスト |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `akihabara` | 156 | 55 | 101 | 6 | 90 | 29 | 31 | 34 | 27 | 47 | 48 | [akihabara_manifest.json](akihabara_manifest.json) |
| `asakusa` | 260 | 209 | 51 | 39 | 174 | 23 | 24 | 147 | 37 | 34 | 33 | [asakusa_manifest.json](asakusa_manifest.json) |
| `ginza` | 72 | 61 | 11 | 2 | 53 | 4 | 13 | 15 | 5 | 7 | 43 | [ginza_manifest.json](ginza_manifest.json) |
| `omotesando_harajuku` | 55 | 24 | 31 | 0 | 32 | 13 | 10 | 15 | 9 | 17 | 13 | [omotesando_harajuku_manifest.json](omotesando_harajuku_manifest.json) |
| `roppongi` | 60 | 29 | 31 | 1 | 35 | 7 | 17 | 17 | 14 | 9 | 20 | [roppongi_manifest.json](roppongi_manifest.json) |
| `shibuya` | 233 | 170 | 63 | 4 | 153 | 49 | 27 | 53 | 55 | 67 | 57 | [shibuya_manifest.json](shibuya_manifest.json) |
| `shinjuku` | 76 | 43 | 33 | 2 | 35 | 17 | 22 | 19 | 12 | 23 | 21 | [shinjuku_manifest.json](shinjuku_manifest.json) |
| `tokyo_marunouchi` | 247 | 195 | 52 | 4 | 123 | 53 | 67 | 72 | 94 | 37 | 43 | [tokyo_marunouchi_manifest.json](tokyo_marunouchi_manifest.json) |
| `ueno` | 221 | 179 | 42 | 7 | 118 | 27 | 69 | 51 | 88 | 31 | 51 | [ueno_manifest.json](ueno_manifest.json) |

## フォトグラメトリ / 3DGS 密度マトリクス（スポット × 時間帯）

同一スポット・同一時間帯の枚数目安: `★` = 10枚以上、`★★` = 25枚以上。

| エリア | スポット | 種別 | 合計 | 朝 | 昼 | 夕 | 夜 |
|---|---|---|---:|---:|---:|---:|---:|
| `tokyo_marunouchi` | `imperial_palace_outer` (皇居外苑・二重橋・お堀・和田倉噴水公園) | landmarks | 142 | 4 | **72★★** | **35★★** | **31★★** |
| `shibuya` | `scramble_hachiko` (渋谷スクランブル交差点・ハチ公前広場) | landmarks | 139 | 1 | **100★★** | **30★★** | 8 |
| `ueno` | `shinobazu_bentendo` (不忍池・不忍池辯天堂・清水観音堂) | landmarks | 99 | 1 | **64★★** | 3 | **31★★** |
| `asakusa` | `sensoji_temple` (浅草寺本堂・五重塔・宝蔵門・二天門) | landmarks | 90 | **17★** | **71★★** | 1 | 1 |
| `ueno` | `ueno_park_center` (上野公園・西郷像・東照宮・五重塔・博物館外観) | landmarks | 80 | 5 | **47★★** | **11★** | **17★** |
| `asakusa` | `kaminarimon` (雷門) | landmarks | 62 | **15★** | **37★★** | 3 | 7 |
| `tokyo_marunouchi` | `tokyo_station_marunouchi` (東京駅丸の内駅舎・駅前広場) | landmarks | 53 | 0 | **26★★** | 6 | **21★** |
| `ginza` | `ginza_4chome_wako` (銀座四丁目交差点・和光時計塔・銀座三越) | landmarks | 52 | 0 | **46★★** | 2 | 4 |
| `tokyo_marunouchi` | `gyoko_dori_marunouchi` (行幸通り・丸の内仲通り・皇居側丸の内街並み) | streets | 52 | 0 | **25★★** | **12★** | **15★** |
| `akihabara` | `chuo_dori` (秋葉原中央通り・電気街メインストリート・歩行者天国) | streets | 49 | 0 | **27★★** | 8 | **14★** |
| `ueno` | `ameyoko` (アメ横・アメヤ横丁・高架下) | streets | 42 | 1 | 7 | **13★** | **21★** |
| `akihabara` | `kandamyojin_showa_dori` (神田明神通り・昭和通り) | streets | 20 | 6 | **11★** | 1 | 2 |
| `asakusa` | `azumabashi_sumida` (吾妻橋・隅田川・スカイツリー遠景・浅草文化観光センター・隅田公園の桜) | landmarks | 20 | 2 | 9 | 3 | 6 |
| `asakusa` | `sumida_park_kototoi` (隅田公園・言問橋・駒形橋・蔵前側リバーサイド) | landmarks | 20 | 0 | **12★** | 3 | 5 |
| `akihabara` | `akiba_station_radiokaikan` (秋葉原駅電気街口・ラジオ会館・アトレ秋葉原) | landmarks | 17 | 0 | 9 | 3 | 5 |
| `akihabara` | `udx_manseibashi` (秋葉原UDX・ヨドバシAkiba・万世橋・マーチエキュート) | landmarks | 17 | 0 | 6 | 7 | 4 |
| `asakusa` | `hanayashiki_rokku` (浅草花やしき・浅草演芸ホール周辺) | landmarks | 17 | 2 | **10★** | 4 | 1 |
| `akihabara` | `kandasakumacho_kandariver` (神田佐久間町・神田川・昌平橋・和泉橋) | streets | 16 | 0 | **14★** | 1 | 1 |
| `asakusa` | `kaminarimon_kokusai_dori` (雷門通り・国際通り・江戸通り) | streets | 15 | 1 | **10★** | 2 | 2 |
| `shibuya` | `miyamasuzaka_meiji` (宮益坂・明治通り渋谷) | streets | 14 | 1 | 6 | 4 | 3 |
| `shibuya` | `station_stream_hikarie` (渋谷駅・渋谷ストリーム・スクランブルスクエア・ヒカリエ) | landmarks | 14 | 2 | 6 | 3 | 3 |
| `shibuya` | `dogenzaka` (道玄坂) | streets | 13 | 0 | 5 | 3 | 5 |
| `shibuya` | `bunkamura_dori` (文化村通り) | streets | 12 | 0 | 8 | 4 | 0 |
| `shibuya` | `center_gai` (渋谷センター街・バスケットボールストリート) | streets | 12 | 0 | 8 | 1 | 3 |
| `shibuya` | `koen_inokashira_spain` (公園通り・井の頭通り・スペイン坂) | streets | 12 | 0 | 9 | 2 | 1 |
| `shinjuku` | `kabukicho_landmarks` (歌舞伎町一番街アーチ・新宿東宝ビル/ゴジラ・東急歌舞伎町タワー) | landmarks | 12 | 0 | 5 | 3 | 4 |
| `akihabara` | `bellesalle_crossing` (ベルサール秋葉原前交差点・中央通り電気街中心部) | landmarks | 11 | 0 | 6 | 3 | 2 |
| `asakusa` | `shinnakamise_denboin` (新仲見世通り・伝法院通り) | streets | 11 | 1 | 7 | 2 | 1 |
| `omotesando_harajuku` | `harajuku_meiji_jingu` (原宿駅・明治神宮大鳥居・神宮橋) | landmarks | 11 | 0 | 6 | 1 | 4 |
| `roppongi` | `gaienhigashi_dori` (外苑東通り・芋洗坂・星条旗通り) | streets | 11 | 1 | 5 | 1 | 4 |
| `roppongi` | `roppongi_crossing_tower` (六本木交差点・六本木から望む東京タワー周辺) | landmarks | 11 | 0 | 4 | 2 | 5 |
| `roppongi` | `roppongi_dori` (六本木通り) | streets | 11 | 0 | **10★** | 1 | 0 |
| `shinjuku` | `tocho_nishishinjuku` (東京都庁・西新宿高層ビル群・新宿中央公園) | landmarks | 11 | 0 | 4 | 3 | 4 |
| `akihabara` | `junk_dori_backstreets` (ジャンク通り・秋葉原電気街裏通り) | streets | 10 | 0 | 7 | 3 | 0 |
| `akihabara` | `kanda_myojin` (神田明神) | landmarks | 10 | 0 | 8 | 0 | 2 |
| `omotesando_harajuku` | `aoyama_dori` (青山通り・南青山) | streets | 10 | 0 | 9 | 1 | 0 |
| `shibuya` | `miyashita_parco` (MIYASHITA PARK・渋谷パルコ・代々木公園南側) | landmarks | 10 | 0 | 7 | 1 | 2 |
| `shinjuku` | `gyoen_hanazono` (新宿御苑・花園神社) | landmarks | 10 | 0 | 6 | 4 | 0 |
| `shinjuku` | `shinjuku_station` (新宿駅（東口・西口・南口・バスタ新宿）) | landmarks | 10 | 0 | 7 | 2 | 1 |
| `shinjuku` | `yasukuni_dori` (靖国通り) | streets | 10 | 1 | 4 | 0 | 5 |
| `asakusa` | `nakamise_dori` (仲見世通り) | streets | 9 | 1 | 4 | 3 | 1 |
| `asakusa` | `rokku_hoppy_dori` (浅草六区ブロードウェイ・ホッピー通り) | streets | 9 | 0 | 8 | 1 | 0 |
| `roppongi` | `keyakizaka_dori` (けやき坂通り・冬イルミネーション・桜) | streets | 9 | 0 | 6 | 1 | 2 |
| `roppongi` | `roppongi_hills` (六本木ヒルズ・森タワー・毛利庭園) | landmarks | 9 | 0 | 3 | 2 | 4 |
| `roppongi` | `tokyo_midtown` (東京ミッドタウン・檜町公園・国立新美術館) | landmarks | 9 | 0 | 7 | 0 | 2 |
| `omotesando_harajuku` | `omotesando_ave` (表参道ケヤキ並木・新緑/紅葉/冬イルミネーション) | streets | 8 | 0 | 5 | 2 | 1 |
| `shinjuku` | `kabukicho_omoide_golden` (歌舞伎町セントラルロード・思い出横丁・新宿ゴールデン街) | streets | 8 | 0 | 2 | 2 | 4 |
| `shinjuku` | `meiji_koshu_dori` (明治通り・甲州街道・西新宿大通り) | streets | 8 | 1 | 3 | 2 | 2 |
| `asakusa` | `kappabashi_dori` (かっぱ橋道具街通り) | streets | 7 | 0 | 6 | 1 | 0 |
| `ginza` | `ginza_chuo_dori` (銀座中央通り・歩行者天国) | streets | 7 | 1 | 3 | 1 | 2 |
| `omotesando_harajuku` | `cat_street_meiji_dori` (キャットストリート・明治通り原宿) | streets | 7 | 0 | 1 | 6 | 0 |
| `omotesando_harajuku` | `yoyogi_park` (代々木公園・国立代々木競技場) | landmarks | 7 | 0 | 5 | 0 | 2 |
| `shibuya` | `shibuya109_qfront` (SHIBUYA109・QFRONT・MAGNET) | landmarks | 7 | 0 | 4 | 1 | 2 |
| `shinjuku` | `shinjuku_dori` (新宿通り) | streets | 7 | 0 | 4 | 1 | 2 |
| `akihabara` | `sotokanda_suehirocho` (外神田・パーツ街・末広町・蔵前橋通り) | streets | 6 | 0 | 2 | 3 | 1 |
| `ginza` | `kabukiza_ginzasix_sukiyabashi` (歌舞伎座・GINZA SIX・数寄屋橋交差点・東急プラザ銀座) | landmarks | 6 | 1 | 3 | 0 | 2 |
| `omotesando_harajuku` | `omotesando_hills_tokyu` (表参道ヒルズ・東急プラザ表参道（オモカド/ハラカド）・表参道交差点) | landmarks | 6 | 0 | 2 | 3 | 1 |
| `omotesando_harajuku` | `takeshita_dori` (竹下通り) | streets | 6 | 0 | 4 | 0 | 2 |
| `ginza` | `yurakucho_forum` (有楽町駅・東京国際フォーラム周辺) | landmarks | 3 | 0 | 1 | 1 | 1 |
| `ginza` | `harumi_dori` (晴海通り) | streets | 2 | 0 | 0 | 0 | 2 |
| `ginza` | `namiki_miyuki_sotobori` (並木通り・みゆき通り・外堀通り・銀座コリドー街) | streets | 2 | 0 | 0 | 0 | 2 |

## 出典・ライセンス規約

- 本カタログのライセンス方針は **CC0 or public domain (no attribution required)** です。
- 動画公開時には [index.json](index.json) に記録した作者名 (`creator`)・ライセンス (`license`)・取得元 URL (`landing_url`) を参考にクレジットを記録してください（CC BY 写真は帰属表記必須）。
