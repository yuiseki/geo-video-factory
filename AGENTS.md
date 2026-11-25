# geo-video-factory: エージェントへの案内

`geo-video-factory` は、地理・歴史・土木の解説動画を、エージェントが再現可能な手順で作るためのスキル集です。地理院タイルの空中写真と標高で地形を 3D にし、カメラを動かしながら線・範囲・地名・数字・写真を重ね、VOICEVOX の掛け合いの声と字幕、立ち絵を付けた mp4 を、ショットの JSON から何度でも同じに書き出します。

各スキルの手順は `.agents/skills/<スキル>/SKILL.md` にある (`.claude/skills` は同じ場所への symlink)。使うと決めたスキルは、答える前に `SKILL.md` を開いて読む。スキルの名前と説明だけから答えない。

## どのスキルを使うか

| スキル | 責務 | 使う場面 |
|---|---|---|
| `geo-video-production` | 企画、章立て、素材と出典の管理、章ごとの並列レンダリング、結合、検品、版番号付きの公開 | 複数章・複数素材の動画全体を作るとき。入口はここ |
| `geo-video-renderer` | MapLibre + 地理院タイル + Playwright + ffmpeg のレンダラー本体、ショット JSON の書式、タイル選択、描画エラーの調査 | レンダラーの導入、ショットの記述、書き出しの不具合 |
| `geo-video-3d-terrain` | 標高タイル (`gsidem` / `mapterhorn`) の選択と変換、高さ強調、陰影起伏、地形上の描画制約 | 標高ソースの選定、3D地形の立体感、地形描画の不具合 |
| `geo-video-satellite-imagery` | Sentinel-2 L2A 等の衛星データ検索、SCL 雲判定、COG 読み込み、NDVI・Lab 季節色度転写、出典表記 | 季節変化・経年変化の衛星色度テクスチャを作るとき |
| `geo-video-3d-buildings` | PLATEAU 3D Tiles の取得と固定化、OSM による欠損建物補完、建物ごとの色・推定テクスチャ、データ被覆との整合 | 都市の 3D 建物映像を作る・建物の欠落や質感を直すとき |
| `geo-video-camera` | カメラ技法 (ドリー、トラッキング、オービット、リビール、俯瞰) の選択、速度、データ範囲、ラベルの検品 | カメラの動きを決める・直すとき |
| `geo-video-narration` | VOICEVOX、複数話者の掛け合い、字幕のタイミング、読み、立ち絵のリアクション、BGM と効果音 | 台本を音声付きの動画へ組み込むとき |
| `geo-video-bgm` | BGM の選定・ローカル合成、FFmpeg `sidechaincompress` 自動ダッキング、`-14 LUFS` 音量マスタリングと出典 | BGM が声を邪魔する、章結合後に BGM を重ねるとき |
| `geo-video-thumbnail` | 代表フレーム抽出と HTML/Playwright による 1280×720（2MB 未満）YouTube サムネイル設計・自動生成 | 公開用のサムネイルを設計・書き出すとき |
| `geo-video-visuals` | 写真、地名、線、範囲、数字、図解、タイトルカード、画面効果、編集表現 | 画が単調、素材が反復、情報が読みにくいとき |
| `geo-video-motion-diagram` | 静止画ではなく時間軸に沿った動きで因果・移動・循環・構造を伝える「動く図」の設計・決定論的実装・検品 | プレート衝突・熱水循環・分解図などを動く模式図として見せたいとき |
| `geo-video-art-direction` | 構図、文字造形と尺度差、3層情報密度、静止と変化、縮小・色以外のビジュアル検品 | 画面が資料一覧に見える、文字が弱い、版を重ねて改善するとき |
| `geo-video-console-layout` | 防災・インフラ・観測向けの管制コンソール・診断・警戒区画風レイアウトと状態遷移 | 区画マップ、多系統比較、時系列波形、計器・警戒表示を設計するとき |
| `geo-video-visualize` | 2D / 3D コロプレス図（`choropleth` / `fill-extrusion`）、配色・階級・NoData・時系列共通尺度の設計 | 統計・空間データを色と高さの地図で可視化するとき |
| `geo-video-materials` | いらすとや・Wikimedia Commons 等の素材収集、ライセンス確認、重複監査、EXIF 抽出、Gyazo 画像 ID 管理 | 外部素材や個人写真を集める・出典や権利を確かめるとき |
| `geo-video-reference-analysis` | 利用者が良いと感じた動画の取得、測定、構成と編集の分析、再生数などの数字の読み方、持ち帰りの提案 | 「この動画いいな」「なぜ伸びたのか」と言われたとき |
| `geo-video-growth-dopa` | 長尺の導入（冒頭30秒）とショート動画における期待と報酬の時間軸設計、過度な複雑化の回避、WCAG 2.2 配慮、効果検証 | 冒頭の離脱を減らしたい、ショート動画向けに構成したい、視聴維持率を改善・検証したいとき |
| `geo-video-growth-predictive-coding` | 視聴者の予測 (事前分布) を呼び出し、裏切る予測誤差を立て、映像の中で解消する構成の設計。予測符号化・分散ベイズ推論・自由エネルギー原理を物差しにする。dopa とは別の枠組みで混ぜない | 「地味」「何がすごいのか伝わらない」と言われたとき、冒頭に置く目印や対比、驚きと種明かしの位置、出典や断り書きの見せ方を決めるとき |

単一ショットの JSON やカメラの調整だけなら、`geo-video-production` を経ずに専用のスキルを直接使う。

## リポジトリの構成

```
.agents/skills/
  geo-video-*/SKILL.md          スキルの入口 (短く保ち、詳細は references/ へ)
  geo-video-*/references/       詳細な手順と知見
  geo-video-*/agents/openai.yaml  Codex 向けの表示名
  geo-video-renderer/assets/template/  レンダラーの実装の正本
.claude/skills -> ../.agents/skills
projects/YYYY/MM/DD/<slug>/     個々の動画の作業場所
```

### 動画ごとの作業場所

1 本の動画 (特集 1 本、シリーズの 1 回) の作業は、必ず `projects/YYYY/MM/DD/<slug>/` で行う。

- `YYYY/MM/DD` は作業を始めた日 (企画や調査を始めた日)。版を重ねても変えない。
- `<slug>` は題材を表す短い英小文字の名前 (`moyashi`、`dotonbori`)。単語の区切りはハイフン。
- 台本、調査メモ、ショット JSON、素材の出典の記録 (`credits.json` など)、概要欄、制作の判断のメモをここに置く。レンダラーはテンプレートを `flyover/` などの下にコピーして使う。
- 画像、動画、音声は `.gitignore` で除外している。写真、地図、立ち絵は他者の著作物か個人の写真で、書き出した動画は大きいため。代わりに、取得元、作者、ライセンス、撮影地点を文字のファイルに残し、取り直せるようにする。
- 書き出し (`out/`)、`node_modules/`、大きな元データ (PLATEAU の CityGML など) は置いても commit しない。
- ほかのプロジェクトを参照するときは、リポジトリのルートからのパス (`projects/2026/11/11/moyashi/flyover/`) で書く。
- 機械固有のパス、配布先、資格情報を書かない。資源制限のコマンドは「ホストの規則に従う」と書く。

例:

| ディレクトリ | 中身 |
|---|---|
| `projects/2026/11/11/moyashi/` | 特集「ヤサイマシマシらーめんの危機！？」。もやしの値段の裏側を、ホルムズ海峡から日本への 4 本の線 (袋、重油、電気、円安) でたどる。調査 (`research/`)、台本の下書き、ショット、v0.2 の見直し案 (`v0.2_plan.md`) |
| `projects/2026/11/13/dotonbori/` | 特集「道頓堀からコスモスクエアへ」。江戸から続く娯楽の街と昭和に描かれた未来都市を、年代別の空中写真、写真、浮世絵でたどる。原稿、章ごとのショット (v0.1.2〜v0.1.7)、章の並列書き出し、撮影地点つきの写真マーカー |

### 共通パッケージと Python / TypeScript の役割分担

プロジェクトごとに JS/Python ファイルをコピーせず、リポジトリ共通のパッケージを直接使う。

| パッケージ / ディレクトリ | 言語 | 役割 |
|---|---|---|
| `packages/renderer/` | **TypeScript** (`strict: true`, TDD) | ショット JSON の型・純粋計算 (`src/lib.ts`)、VOICEVOX 連携 (`src/voice.ts`)、Playwright + ffmpeg 描画 CLI (`src/render.ts`)。ブラウザ側はフレーム制御 (`src/page/flyover.ts`)、地図スタイル (`map-style.ts`)、タイルプロトコル (`map-protocols.ts`)、DOM オーバーレイ (`overlays.ts`) に分割 |
| `packages/pipeline/` | **Python** | 章ごとの並列書き出しと結合 (`chapter_pipeline.py`)、EXIF GPS 抽出 (`photo_geo.py`)、共通カメラキー生成 (`shot_effects.py`)、PSD スプライト書き出し (`psd_sprites.py`) |
| `.agents/skills/geo-video-renderer/assets/template/` | データ雛形のみ | 新規プロジェクト用の初期データ (`shots/`, `characters/`, `assets/.gitkeep`, `.gitignore`)。コードはここに置かない |

- TypeScript レンダラーのビルドとテスト:
  ```bash
  cd packages/renderer
  npm test
  ```
- 全 packages の型検査・単体テスト・カバレッジ検査: `packages/test.sh`
- レンダラーのテストは Playwright と ffmpeg を通す E2E 動画も生成する。成果物は `packages/renderer/dist/test/video/` の `base.mp4`、`earth-tokyo-station.mp4`、`terrain-mt-fuji.mp4`。各動画の確認用フレームは同ディレクトリの `.work/<動画名>/frames/` に出る
- 動画 E2E は `packages/renderer/test/video.e2e.test.ts` の共通 `cases` 登録と描画処理を使う。ケース定義とフィクスチャ検査は `test/e2e/<testname>.test.ts` に置き、共通 runner に登録する。個別ファイルに別の動画描画・出力処理を実装しない。
- 中間成果物と実行時に取得・生成する実データのキャッシュは必ず `packages/renderer/dist/test/video/.work/<testname>/` に作る。通常の最終出力は `packages/renderer/dist/test/video/<testname>.mp4`。ケースが `outputPath` を宣言した場合はその1か所だけを正本とし、古い別名コピーを残さない。PLATEAU Asakusa の正本は `packages/renderer/dist/test/video/buildings-asakusa.mp4`。
- E2E 実行時に公開データから取得・生成できる GLB、manifest、GeoJSON、アーカイブを `packages/renderer/test/fixtures/` に置かない。fixture には動画仕様だけを置き、実データは欠落時に `.work/<testname>/` へ取得・生成して再利用する。
- `VIDEO_TARGET=<testname>` は共通 `cases` に登録した名前で対象を絞る。PLATEAU E2E も例外にせず、この共通 runner から単独実行できるようにする。
- PLATEAU データを使う E2E のケース名・出力動画名には、必ず `buildings-` prefix を付ける（例: `buildings-asakusa`）。
- `packages/renderer/dist/test/video/` に置く再現用素材・動画は、追跡されたパッケージ実装とフィクスチャから他端末でも生成できるものに限る。`tmp/` 以下にある実装・入力・生成物を同ディレクトリへコピー、移動、リンクしてはならない。
- `tmp/` は使い捨ての作業物専用とする。再現に必要なコード、データ、設定、手順の正本を `tmp/` に置かない。再現用素材は、出典・ライセンスを記録したうえで適切な追跡対象ディレクトリに置く。
- Python パイプラインだけのテスト: `python3 -m unittest discover -s packages/pipeline/tests -v`
- 参考動画の分析スクリプトのテスト: `python3 .agents/skills/geo-video-reference-analysis/scripts/tests/test_scripts.py`

必要なもの: Node.js 22+、Playwright の Chromium、ffmpeg と ffprobe、Python 3 と Pillow、Noto Sans CJK、VOICEVOX エンジン (既定は `http://127.0.0.1:50021`)。

## 「PLATEAU」は PLATEAU++ を指す

「PLATEAU を描いて」「PLATEAU の建物で」のように言われたら、常に PLATEAU++ を用意する。「PLATEAU だけで」のような例外の注文があるときだけ従う。

PLATEAU++ は次の優先順位で、カメラに収まる範囲の全建物をテクスチャ付きでそろえたもの。

1. PLATEAU の元の建物モデルと、元のテクスチャ (テクスチャ付き LOD2 の tileset)。元のテクスチャの上に合成外壁 (`facadeTextures` など) を重ねて消さない。
2. PLATEAU にテクスチャが無い建物だけ、地理院オルソなどから外壁の色と屋根を合成する。
3. PLATEAU に建物モデルが無い所だけ、OpenStreetMap などから建物を合成する。

- 範囲はカメラの全行程で画面に入る地面から決める。用意した範囲の外が映るところまでカメラを引かない。
- 手順と実装は `geo-video-3d-buildings` スキル。PLATEAU と補完を 1 つの manifest にする例は `packages/renderer/test/e2e/prepare-buildings-tokyo-sota.py`。
- 補完の形状は今の実装では地理院の建物外形を使い、高さに OSM の `building:levels` を優先し、無ければ `height` を使う。

## 進め方の原則

- 静止画の一覧で完了としない。通常速度の音声付き動画で、カメラの加速、章の境界、ラベルの重なり、写真マーカーの追従、読み、字幕の同期を確かめる。
- 音声の実尺がショットの長さを決める。文字数からの推定だけで本番のタイミングを確定しない。
- 書き出しは新しい出力先へ。既存の成果物を上書きせず、`v0.1.7` のような版番号を付けて残す。
- 実データを読む書き出しは、ホストの資源制限ルールに従ってメモリと CPU に上限を掛けて流す。並列の章は同じ上限を共有し、最大 3 並列を目安にする。
- 素材ごとに作者、取得先、ライセンス、加工、使った箇所を記録し、出典を画面と概要欄に出す。地理院タイル、NASA GIBS、OpenStreetMap、VOICEVOX、立ち絵の作者を落とさない。
- 歴史的な空中写真に現代の地名を重ねるときは、そのことを画面で明示する。概略の位置や模式図は概略と書く。

## スキルを書く、直すとき

- 動画を作って見つかった型の不具合は、その作品の中だけで直さず、スキルと共通パッケージ (`packages/renderer/`, `packages/pipeline/`) へ戻してから次へ進む。
- `SKILL.md` は短く保ち、詳細は `references/` に分ける。スキル間の責務は上の表に合わせ、レンダラーへ個別作品の演出ルールを持ち込まない。
- 共通パッケージの挙動を変えるときは、先に `test/` にテストを足す (TDD)。ドキュメントは現に動いている実装に合わせて直す。
- 実装できない技法を名前だけで書かない。`geo-video-visuals/references/README.md` の対応表 (○ △ ×) を実装に合わせて更新する。

## リポジトリに入れないもの

このリポジトリは公開を前提にしている。

- 特定の機械のパス、ローカルのホスト名、配布先、資格情報、`.env`。必要なら環境変数や引数で渡す。公開している `*.yuiseki.net` の OSM サービス (`osm-services.md`) は書いてよい。
- 立ち絵の PSD、参考動画とその字幕・サムネイル・分析ファイル、再配布の許可が確かめられていない写真や素材。スキルや文書に個々の参考動画やチャンネルの名前を書かず、型の言葉で書く。
- 書き出したフレームと動画 (`out/`)、`node_modules/`。
- 公開してよいと確かめていない写真サービスの画像 ID や URL (Gyazo など)。ID が分かれば写真そのものを開けるので、写真のファイルを除外していても、ID を書けば写真を公開したことになる。push する前に ID の一覧を利用者に見せて確かめる。

### 秘密情報と写真の ID の検査 (gitleaks)

gitleaks で、資格情報と写真の ID を検査する。設定は `.gitleaks.toml`。

- gitleaks の既定の規則 (API キー、トークン、秘密鍵など) に加えて、ちょうど 32 桁の小文字の 16 進の並びをすべて Gyazo の画像 ID の候補として検出する。許可するのは、持ち主が公開してよいと確かめた ID だけ (許可リスト方式)。
- 新しい写真の ID を使うときは、`https://gyazo.com/<ID>` の一覧を利用者に見せ、公開してよいと言われた ID だけを `.gitleaks.toml` の許可リストに足す。日付とプロジェクトを注記する。確かめていない ID を許可リストに足さない。検出を避けるために ID の書き方を変えない。
- clone したら一度 `git config core.hooksPath .githooks` を実行する。コミットのたびに `.githooks/pre-commit` がステージした変更を検査する。
- GitHub では `.github/workflows/gitleaks.yml` が push と pull request のたびに全履歴を検査する。
- 手で全履歴を検査するとき: `gitleaks git --redact -c .gitleaks.toml .`
