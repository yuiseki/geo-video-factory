# 開発環境のセットアップ

この文書では、`geo-video-factory` の全スキルを利用するための共通環境を準備します。個々の動画素材や地図データの取得方法は、各スキルの `SKILL.md` と `references/` を参照してください。

## 想定する環境

このリポジトリは Linux を基準にしています。動画のレンダリングでは、多数の画像、ブラウザー、音声合成、FFmpeg を同時に使うため、十分な空き容量とメモリーが必要です。GPU があると書き出しが速くなりますが、必須ではありません。

次のソフトウェアをインストールしてください。

| ソフトウェア | 用途 | 必須範囲 |
|---|---|---|
| Git | リポジトリの取得と変更管理 | 全機能 |
| Node.js と npm | MapLibre、Playwright、レンダラー、参考動画の取得 | 全機能 |
| Python 3 | 章の結合、写真の EXIF、カメラ補助、素材分析 | 全機能 |
| uv | PSD変換や動画分析用のPythonパッケージを一時実行 | 立ち絵と参考動画分析 |
| FFmpeg と ffprobe | フレームから MP4 を生成、音声結合、音量測定、動画分析 | 全機能 |
| Playwright の Chromium | MapLibre の画面をフレーム単位で描画 | 動画レンダリング |
| Noto Sans CJK JP | 日本語の字幕、地名、タイトルカード | 動画レンダリング |
| VOICEVOX エンジン | 複数話者の音声合成 | 音声付き動画 |
| ずんだもん・四国めたんの PSD | 表情、まばたき、口パクを含む立ち絵 | キャラクター付き動画 |
| Docker | Linux で VOICEVOX エンジンを動かす方法の1つ | Docker 版 VOICEVOX を使う場合 |
| gitleaks | 資格情報と公開未確認の画像 ID をコミット前に検出 | コミットと公開 |

Node.js は保守中の LTS 版を使ってください。Python は Python 3.10 以降を想定しています。古い Linux ディストリビューションの標準パッケージでは、Node.js が古すぎる場合があります。その場合は、Node.js の公式配布物または Node.js のバージョン管理ツールを使ってください。

## OS の基本パッケージ

Ubuntu 系 Linux では、次のパッケージが土台になります。

```bash
sudo apt update
sudo apt install git curl ffmpeg python3 python3-venv python3-pip \
  fontconfig fonts-noto-cjk
```

Node.js、Docker、gitleaks は、それぞれの公式手順でインストールしてください。インストール後に、コマンドが `PATH` から実行できることを確認します。

```bash
git --version
node --version
npm --version
python3 --version
ffmpeg -version
ffprobe -version
fc-list :lang=ja | head
```

## リポジトリと秘密情報検査の準備

リポジトリを clone し、同梱の pre-commit hook を有効にします。

```bash
git clone https://github.com/yuiseki/geo-video-factory.git
cd geo-video-factory
git config core.hooksPath .githooks
```

hook は `gitleaks` を使います。`gitleaks version` が失敗する場合は、コミットする前に gitleaks をインストールしてください。

## レンダラーの準備

レンダラーの正本は `packages/renderer/` にあります。依存パッケージと Chromium をインストールし、TypeScript をビルドします。

```bash
cd packages/renderer
npm install
npx playwright install chromium-headless-shell
npm run build
cd ../..
```

Linux で Chromium の共有ライブラリーが不足する場合は、Playwright の表示に従って OS パッケージを追加してください。Playwright のブラウザーは、OS に入っている Chromium とは別に管理されます。

JavaScript の単体テストで、Node.js と依存パッケージを確認できます。

```bash
npm test
```

## Python の準備

章の結合と写真の EXIF 読み取りには Pillow が必要です。仮想環境を作り、Pillow をインストールします。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install Pillow
```

次の機能では追加パッケージを使います。

- 立ち絵の PSD 分解: `psd-tools`
- 参考動画の動きの測定: `opencv-python-headless` と `numpy`
- 参考動画の取得: `yt-dlp`

これらは全動画で必要になる依存関係ではありません。該当するスキルの手順に従い、Python 仮想環境または `uv` で追加してください。

立ち絵または参考動画分析を使う場合は、Astral が配布する `uv` を公式手順でインストールし、`uv --version` が成功することを確認してください。

## ずんだもん・四国めたんの立ち絵

キャラクター付き動画では、音声とは別に立ち絵の PSD ファイルが必要です。このリポジトリには、立ち絵の PSD と変換後の PNG を収録していません。素材の配布元から各自で入手してください。

同梱のレイヤー選択設定は、次の素材で確認しています。

- 坂本アヒル氏「ずんだもん立ち絵素材 2.3」
- 坂本アヒル氏「四国めたん立ち絵素材 2.1」

異なる版ではレイヤー名や構造が変わり、同梱設定で正しく変換できない場合があります。ZIP に含まれる readme と、[東北ずん子・ずんだもんプロジェクトのキャラクター利用ガイドライン](https://zunko.jp/guideline.html) を確認してください。配布先は変更される場合があるため、素材名と作者名から作者が案内する最新の配布元を確認します。

新しい動画のプロジェクトを作り、テンプレートのキャラクター設定をコピーします。入手した PSD は、リポジトリ内の次の固定パスへ置きます。`tmp/` は `.gitignore` の対象であり、PSD はコミットされません。

```text
tmp/zunda/ずんだもん立ち絵素材2.3.psd
tmp/metan/四国めたん立ち絵素材2.1.psd
```

```bash
mkdir -p projects/YYYY/MM/DD/<slug>/characters
mkdir -p projects/YYYY/MM/DD/<slug>/assets/chara
cp .agents/skills/geo-video-renderer/assets/template/characters/*.json \
  projects/YYYY/MM/DD/<slug>/characters/
```

`psd-tools` を使い、PSD から表情、目、口の組み合わせを PNG スプライトとして書き出します。次のコマンドはリポジトリのルートで実行します。

```bash
uv run --with psd-tools python packages/pipeline/psd_sprites.py \
  projects/YYYY/MM/DD/<slug>/characters/zundamon.json \
  "tmp/zunda/ずんだもん立ち絵素材2.3.psd" \
  projects/YYYY/MM/DD/<slug>/assets/chara/zundamon

uv run --with psd-tools python packages/pipeline/psd_sprites.py \
  projects/YYYY/MM/DD/<slug>/characters/metan.json \
  "tmp/metan/四国めたん立ち絵素材2.1.psd" \
  projects/YYYY/MM/DD/<slug>/assets/chara/metan
```

各出力先に、表情ごとの PNG と `sheet.png` が生成されます。`sheet.png` を開き、次の項目を確認してください。

- ずんだもんと四国めたんの全身が正しい範囲で切り出されている。
- 表情が切り替わっている。
- 目を閉じた画像が実際に閉じている。
- 口を開いた画像と閉じた画像が異なる。
- 腕や服のレイヤーが欠けていない。

PSD、変換後の PNG、素材の ZIP はコミットしません。プロジェクトには、再取得できる素材名、作者、版、配布元、利用条件、変換設定だけを記録します。VOICEVOX の音声規約と立ち絵素材の規約は別のものです。完成動画では、実際に使用した音声と立ち絵の条件をそれぞれ確認してください。

## VOICEVOX エンジンの準備

音声付き動画では、VOICEVOX エンジンの HTTP API を使います。既定の接続先は `http://127.0.0.1:50021` です。

Linux では、VOICEVOX エンジンの Docker 版を使えます。利用する CPU または GPU に対応した安定版イメージを選び、ポート `50021` をローカルホストだけに公開してください。イメージ名とタグは VOICEVOX エンジンの公式配布情報で確認し、プロジェクト内で固定します。

エンジンを起動した後、HTTP API を確認します。

```bash
curl http://127.0.0.1:50021/version
curl http://127.0.0.1:50021/speakers
```

JSON が返れば、レンダラーから音声を合成できます。接続先を変更する場合は、ショット JSON の `tts.url` へ URL を指定します。AivisSpeech のように VOICEVOX 互換 API を持つエンジンも利用できますが、既定値、話者 ID、クレジット表記はエンジンごとに確認してください。

VOICEVOX と各キャラクターには利用規約とクレジット条件があります。完成動画と概要欄に、実際に使用した音声のクレジットを記載してください。

## 最小動作確認

リポジトリのルートからプロジェクトデータの雛形を一時ディレクトリへコピーし、音声を使わないサンプルを書き出します。事前に `packages/renderer/` のビルドを完了してください。

```bash
mkdir -p /tmp/geo-video-smoke
cp -a .agents/skills/geo-video-renderer/assets/template/. /tmp/geo-video-smoke/
node packages/renderer/dist/src/render.js \
  /tmp/geo-video-smoke/shots/example.json \
  --project /tmp/geo-video-smoke \
  --out /tmp/geo-video-smoke/out/example \
  --stills 2 --no-voice
```

音声付きの確認では、VOICEVOX エンジンを起動してから `--no-voice` を外します。最終的には、生成した静止画だけでなく MP4 を通常速度で再生し、日本語表示、地形、音声、字幕の同期を確認してください。

## GPU を使えない環境

GPU を利用できない場合は、SwiftShader によるソフトウェア描画を指定できます。

```bash
FLYOVER_GL=swiftshader node packages/renderer/dist/src/render.js \
  /tmp/geo-video-smoke/shots/example.json \
  --project /tmp/geo-video-smoke \
  --out /tmp/geo-video-smoke/out/example --no-voice
```

ソフトウェア描画は大幅に遅くなります。地形や高解像度のシーンでは、タイムアウトや長時間の処理が起きる場合があります。

## 外部サービスへの接続

地図と素材を扱うスキルでは、国土地理院、OpenStreetMap 系サービス、PLATEAU、Wikimedia Commons などへ接続します。組織のプロキシーやファイアウォールを使っている場合は、HTTPS 接続と Playwright Chromium からの通信を許可してください。

大量のタイルやデータを取得する処理では、取得元の利用条件を守り、結果をローカルへキャッシュしてください。実データを処理するときは、ホスト環境の規則に従って CPU、メモリー、並列数へ上限を設定します。
