# macOS での開発環境セットアップ

macOS（Apple Silicon / Intel）における依存ソフトウェアのインストールと初期確認の手順です。全体の流れや共通の設定は [SETUP.md](../../../SETUP.md) を参照してください。

## 1. Homebrew で基本パッケージを導入

[Homebrew](https://brew.sh/) を使って必要なコマンドと日本語フォントを入れます。

```bash
brew install git node ffmpeg uv gitleaks
brew install --cask font-noto-sans-cjk-jp
```

ゆっくり風音声（Open JTalk）を使う場合は、あわせて `open-jtalk` も導入します。

```bash
brew install open-jtalk
```

インストール後、各コマンドが実行できることを確認します。

```bash
git --version
node --version
npm --version
ffmpeg -version | head -n 1
ffprobe -version | head -n 1
uv --version
gitleaks version
```

## 2. レンダラーと Playwright Chromium

`packages/renderer` で依存パッケージと Chromium を導入し、ビルドします。macOS では標準で ANGLE Metal による GPU 描画が利用されます。

```bash
cd packages/renderer
npm install
npx playwright install chromium-headless-shell
npm run build
cd ../..
```

## 3. Python 仮想環境 (`.venv`)

macOS 標準の `/usr/bin/python3`（3.9 系）ではなく、Python 3.10 以降（例: 3.12）で `.venv` を作成し、パイプライン・テスト用の依存パッケージを入れます。

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r packages/pipeline/requirements-dev.txt
```

立ち絵の PSD 分解は `uv run --with psd-tools ...` で実行するため、通常は追加インストール不要です。`pyopenjtalk` を Python から直接使う場合は `.venv` へ追加してください。

## 4. 音声エンジンの準備（用途に応じて選択）

### VOICEVOX（ずんだもん・四国めたん等）

公式サイトから VOICEVOX デスクトップ版をインストールして起動すると、`http://127.0.0.1:50021` で API が待ち受けます。

```bash
curl http://127.0.0.1:50021/version
```

### AquesTalkPlayer Mac 版（ゆっくりボイス `f1` 霊夢・`f2` 魔理沙）

株式会社アクエストの [AquesTalkPlayer Mac 版](https://www.a-quest.com/products/aquestalkplayer.html) を `/Applications/AquesTalkPlayer.app` にインストールすると、`tts.engine: "aquestalk"` 指定時に `packages/pipeline/aquestalk_tts.py` 経由で `f1` / `f2` 音声を合成できます。評価版の機能制限や公開時のライセンス条件は配布元の規約を確認してください。

### Open JTalk

Homebrew で `open-jtalk` を導入済みの場合、`/opt/homebrew/opt/open-jtalk/dic` および同梱音声モデルが自動で検出され、`tts.engine: "openjtalk"` で合成できます。

## 5. 動作確認とテスト

全パッケージの型検査・単体テスト・スキル検証は、`.venv/bin` を `PATH` に通して実行します。

```bash
CI=1 PATH="$(pwd)/.venv/bin:$PATH" bash packages/test.sh
```

実立ち絵モデルを使ってキャラクター／ナレーション E2E を確認する場合は、`MODEL_*_PATH` 環境変数を指定して実行できます（`tmp/` 配下のモデルはコミット対象外）。

```bash
cd packages/renderer
PATH="$(cd ../.. && pwd)/.venv/bin:$PATH" \
  MODEL_REIMU_PATH="$(cd ../.. && pwd)/tmp/__models/たぬき式ゆっくり/たぬき霊夢" \
  MODEL_MARISA_PATH="$(cd ../.. && pwd)/tmp/__models/たぬき式ゆっくり/たぬき魔理沙" \
  VIDEO_TARGET=narration-yukkuri npm run test:video
```
