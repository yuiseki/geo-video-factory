# 制作ロール別チェックリスト・品質ゲートと動画タイプ別パイプライン

複数章・複数素材を扱う地理動画では、全スキルを一度に読み込んで場当たり的に書き出すと、後工程での手戻り（再レンダリング・音声再生成・素材差し替え）が大きくなる。本ガイドでは、制作を **5つのロール領域（監督/脚本・撮影・美術・特効・音響）** に分け、各工程で必要なスキルだけをオンデマンドに読み込みながら、明示的な **品質ゲート（Pass / Fail 条件）** を通過してから次工程へ進む手順を定める。

## ゲート運用の基本原則

- **オンデマンド読み込み**: 各工程に入るとき、表に記載された担当スキルの `SKILL.md` と該当 `references/` を開く。関係のない工程のスキルを先に抱え込まない。
- **Fail 時は次工程へ進まない**: ゲートで 1 項目でも Fail があれば、重い書き出し（本編レンダリングや全編結合）へ進まず、その工程内で修正して再判定する。
- **試作とファストトラック**: 新しい表現の検証やショート動画など小規模案件では、Gate 1〜2（企画〜画コンテ）および Gate 3〜4（美術〜特効）をそれぞれ束ねて進めてよい。ただし、**事実・出典の確認（Gate 1）**、**権利・重複・ID 管理（Gate 3）**、**音声実尺と最終 QA（Gate 5）** は省略しない。

---

## ロール別チェックリストと品質ゲート

### Gate 1: 企画・構成（監督 / 脚本）

**役割**: 調査・事実の骨組みづくり、動画タイプ選定、章構成、冒頭フックと問いの配置、台本執筆。

**オンデマンド参照スキル**:
- `geo-video-production`（[script-from-sources.md](script-from-sources.md)）
- `geo-video-reference-analysis`（[findings.md](../../geo-video-reference-analysis/references/findings.md)）
- `geo-video-growth-predictive-coding`（事前分布・予測誤差・解消の設計）
- `geo-video-growth-dopa`（冒頭 30 秒の離脱対策・ショート動画のテンポ設計）

**チェックリスト**:
- [ ] 主題・想定視聴者・伝えたい主張・目標尺・動画タイプ（後述の 4 類型）を 1 枚に整理した。
- [ ] 一次資料・報道・自治体資料から事実の骨組みと年表を作り、出典（媒体名・原題・URL）を記録した。
- [ ] 冒頭に視聴者の関心を引く問い・対比・目印を置き、各章の終わりと次章の始まりに自然なつなぎを設計した。
- [ ] 章の境界を原稿の場面見出しで一意に定め、各章で同じ問いを繰り返していない。
- [ ] 生成テキストから Markdown 記号・絵文字・混入文字を機械的に除去し、煽り語を避けた。

**Pass / Fail 判定**:
- **Pass**: 台本内のすべての事実に出典が対応し、推測は「〜と考えられている」等で区別され、章見出し一覧と目標尺が確定している。
- **Fail**: 出典不明の断定が残っている／章の境界が曖昧／冒頭で何を見る動画かが伝わらない。

---

### Gate 2: 画コンテ・カメラ（撮影）

**役割**: 台本からショット単位の画コンテ（Scene Plan）への分解、地名座標・経路の確定、カメラ技法・速度・データ範囲の設計。

**オンデマンド参照スキル**:
- `geo-video-camera`（[camera.md](../../geo-video-camera/references/camera.md)、[camera-and-label-review.md](../../geo-video-camera/references/camera-and-label-review.md)）
- `geo-video-renderer`（[shots.md](../../geo-video-renderer/references/shots.md)、[gsi-tiles.md](../../geo-video-renderer/references/gsi-tiles.md)）
- `geo-video-production`（[osm-services.md](osm-services.md)）

**チェックリスト**:
- [ ] 台本の全場面・全セリフをショット単位へ割り当て、各ショットの役割（導入・位置確認・比較・寄り・引き・図解）を決めた。
- [ ] 地名座標・川や路線の形状・経路を OSM サービス等で取得し、地理院空中写真の上に重ねて位置の正しさを目視確認した。
- [ ] カメラ技法（ドリー・トラッキング・オービット・リビール・俯瞰）を単調にならないよう使い分け、急激な加減速を避けた。
- [ ] 対象地だけでなく、位置関係が伝わる隣の駅・川・橋などのランドマークを配置計画に入れた。
- [ ] 縦長（1080×1920）出力がある場合、横長構図の流用ではなく縦長用に画角と重ね物位置を組み直した。

**Pass / Fail 判定**:
- **Pass**: 全ショットの座標・カメラ移動・使用タイル種別が確定し、タイル欠落範囲や画面外ラベル流出の見込みがない。
- **Fail**: 同名別地点の座標が混入／全編ほぼ同一画角の静止画または一定速度移動のみ／鉄道移動に徒歩経路を流用している。

---

### Gate 3: 視覚ルック・素材（美術）

**役割**: 画面全体の構図・配色・タイポグラフィ尺度差の設計、写真・イラスト・過去地図の収集と権利・重複監査、サムネイル設計。

**オンデマンド参照スキル**:
- `geo-video-art-direction`（[composition-and-type.md](../../geo-video-art-direction/references/composition-and-type.md)、[visual-review.md](../../geo-video-art-direction/references/visual-review.md)）
- `geo-video-visuals`（[look.md](../../geo-video-visuals/references/look.md)、[graphics.md](../../geo-video-visuals/references/graphics.md)）
- `geo-video-materials`（[sourcing.md](../../geo-video-materials/references/sourcing.md)、[rights-and-audit.md](../../geo-video-materials/references/rights-and-audit.md)）
- `geo-video-thumbnail`（[thumbnail-design.md](../../geo-video-thumbnail/references/thumbnail-design.md)）

**チェックリスト**:
- [ ] 画面の 3 層情報密度（主題・補助・背景）と文字の尺度差・実ウェイト・コントラストを決め、縮小表示でも読める設計にした。
- [ ] 使用する全素材（写真・イラスト・過去地図・立ち絵）について、作者・取得先・ライセンス・加工内容・使用箇所を `credits.json` 等へ記録した。
- [ ] 同一素材の無意味な反復や重複を監査し、個人写真・外部画像 ID（Gyazo 等）は公開可否と許可リストを確認した。
- [ ] 写真と地図を対応づける場合、EXIF GPS の誤差を確認し、撮影地点（`at`）と写っている対象（`cameraAt`）を混同していない。
- [ ] 過去空中写真に現代地名を重ねる場合、画面上および概要欄に明示する注記を配置した。
- [ ] サムネイル候補となる代表フレームの構図を、本編ショット計画の段階で確保した。

**Pass / Fail 判定**:
- **Pass**: 権利・出典・重複監査が完了し、色だけに頼らない判別性と文字可読性が確保され、未確認の画像 ID がリポジトリに混入していない。
- **Fail**: ライセンス不明またはクレジット欠落の素材がある／写真と撮影地点の線が矛盾／文字が背景に埋もれる。

---

### Gate 4: 動く図・3D演出（特効）

**役割**: 3D 地形・3D 建物・衛星季節テクスチャ・動く模式図・統計コロプレス・管制コンソール表示など、空間演出とデータの決定論的実装。

**オンデマンド参照スキル**:
- `geo-video-3d-terrain`（[dem-sources.md](../../geo-video-3d-terrain/references/dem-sources.md)、[terrain-rendering.md](../../geo-video-3d-terrain/references/terrain-rendering.md)）
- `geo-video-3d-buildings`（[architecture.md](../../geo-video-3d-buildings/references/architecture.md)、[validation.md](../../geo-video-3d-buildings/references/validation.md)）
- `geo-video-satellite-imagery`（[sentinel2-seasonal-ortho.md](../../geo-video-satellite-imagery/references/sentinel2-seasonal-ortho.md)）
- `geo-video-motion-diagram`（[motion-grammar.md](../../geo-video-motion-diagram/references/motion-grammar.md)、[deterministic-engine.md](../../geo-video-motion-diagram/references/deterministic-engine.md)）
- `geo-video-visualize`（[choropleth-and-scale.md](../../geo-video-visualize/references/choropleth-and-scale.md)）
- `geo-video-console-layout`（[console-patterns.md](../../geo-video-console-layout/references/console-patterns.md)、[state-and-motion.md](../../geo-video-console-layout/references/state-and-motion.md)）

**チェックリスト**:
- [ ] 3D 地形の標高ソース・高さ強調（exaggeration）・陰影起伏が主題と合致し、地形上のラベルや線が破綻していない。
- [ ] 3D 建物（PLATEAU / OSM 補完）の被覆範囲がカメラ移動範囲を満たし、画面端に不自然な欠落が露出していない。
- [ ] 動く図（因果フロー・循環・分解図）やコンソール状態遷移が時間軸に対して決定論的に描画され、字幕・立ち絵と干渉しない。
- [ ] 統計コロプレス図の配色・階級区切り・NoData 分離・時系列比較の共通尺度が誤解を生まない設計になっている。
- [ ] 模式図・概略位置・衛星データの取得日・出典表記が画面内に正しく表示される。

**Pass / Fail 判定**:
- **Pass**: 該当する 3D・衛星・図解・可視化レイヤーが代表フレームおよび短尺テスト動画で破綻なく再現でき、データ出典・時点・概略注記が揃っている。
- **Fail**: カメラ内に建物・タイルの空白が露出／統計の尺度や NoData が誤読を招く／図解が静止画の貼り付けだけで動きの意図が伝わらない。

---

### Gate 5: 声・BGM・同期（音響）＆最終書き出し

**役割**: VOICEVOX 音声生成と実尺確定、字幕・立ち絵同期、章並列レンダリングと結合、BGM ダッキング・音量マスタリング、自動 QA と目視検品。

**オンデマンド参照スキル**:
- `geo-video-narration`（[narration.md](../../geo-video-narration/references/narration.md)、[reaction.md](../../geo-video-narration/references/reaction.md)、[sound.md](../../geo-video-narration/references/sound.md)）
- `geo-video-bgm`（[ducking-and-loudness.md](../../geo-video-bgm/references/ducking-and-loudness.md)）
- `geo-video-production`（[production-workflow.md](production-workflow.md)、[publishing.md](publishing.md)）

**チェックリスト**:
- [ ] すべてのショット長を文字数推定ではなく VOICEVOX の実音声長から確定し、読み間違い・不自然な間を修正した。
- [ ] 字幕・立ち絵リアクション・写真マーカーの追従が音声タイミングと同期し、画面上で相互に重なっていない。
- [ ] 複数章を資源上限内で並列書き出し（最大 3 並列目安）し、既存版を上書きせず版番号付き出力先へ結合した。
- [ ] BGM を重ねる場合、結合後に `sidechaincompress` ダッキングと `-14 LUFS` 前後の音量マスタリングを行い、声の明瞭度を保った。
- [ ] `packages/pipeline/video_qa.py --platform youtube --content --contact ...` を実行し、規格値・黒画面・フリーズ・無音・4×3 コンタクトシートを目視確認した。
- [ ] 音声付きの通し動画で章境界・カメラ速度・ラベル・出典を確認し、概要欄（実尺ベースのチャプター・出典・クレジット）とサムネイルを揃えた。

**Pass / Fail 判定**:
- **Pass**: 自動 QA と音声付き通し検品に異常がなく、版番号付き MP4・概要欄・チャプター・出典・サムネイルが一致して公開準備が整っている。
- **Fail**: 誤読・字幕ズレ・無音または黒画面エラー・音量過大/過小・ラベル衝突・出典漏れが 1 件でも残っている。

---

## 動画タイプ別の推奨パイプライン

企画段階（Gate 1）で題材に最も合うパイプラインを選び、重点スキルと確認ポイントを先に決める。

| 動画タイプ | 主な題材例 | 重点スキル（オンデマンド） | 標準フェーズと設計の要点 |
|---|---|---|---|
| **1. 紀行・街歩き解説** | 商店街・駅周辺・路線・史跡の巡訪、現地写真と地図の連動 | `geo-video-camera`, `geo-video-materials`, `geo-video-3d-buildings`, `geo-video-narration`, `geo-video-bgm` | **標準 5 ゲート**。OSM で駅・川・橋・徒歩経路を確定し、EXIF 付き写真を `photo_marker` で地図へ結ぶ。新表現は代表写真 1 枚で試作してから本編へ展開する。 |
| **2. 歴史・地形変遷** | 治水・埋立・都市開発・災害前後の比較、時代をまたぐ空中写真 | `geo-video-3d-terrain`, `geo-video-satellite-imagery`, `geo-video-renderer`, `geo-video-motion-diagram`, `geo-video-growth-predictive-coding` | **標準 5 ゲート**。年代別の地理院空中写真や衛星テクスチャを同一画角で比較し、地形の起伏と原因を動く図で補う。背景が過去・地名が現代である注記を必ず入れる。 |
| **3. データ可視化・防災コンソール** | 統計比較・人口動態・地震・河川監視・インフラ解説 | `geo-video-visualize`, `geo-video-console-layout`, `geo-video-art-direction`, `geo-video-motion-diagram`, `geo-video-production`（`script-from-sources.md`） | **標準 5 ゲート（Gate 1・4 重点）**。一次資料の数値をそのまま保持し、階級区切り・NoData・時系列共通尺度を固定する。3 層情報密度と色以外の判別性を縮小グレースケールで検品する。 |
| **4. ショート動画（縦長 9:16）** | 本編の切り出し再構成、1 トピック完結の 30〜60 秒解説 | `geo-video-growth-dopa`, `geo-video-visuals`, `geo-video-camera`, `geo-video-narration`, `geo-video-production`（`publishing.md`） | **ファストトラック**（Gate 1〜2、Gate 3〜4 をそれぞれ統合可）。冒頭数秒で問いと視覚的変化を提示し、1080×1920 で下部・右端の再生 UI を避けて構図と文字を組み直す。 |

### パイプラインの切り替え判断

- 1 本の長尺動画の中に「歴史変遷の章」と「データ可視化の章」が混在する場合は、**動画全体は標準 5 ゲートで管理し、章単位で該当タイプの重点スキルと Gate 4 の判定項目を追加する**。
- 調査（Gate 1）の段階で一次資料や必要な写真・タイルが揃わないと判明した場合は、ショット設計へ進まず企画スコープを見直す。
