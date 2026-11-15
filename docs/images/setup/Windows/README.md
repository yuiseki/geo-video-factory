# Windows での開発環境セットアップ

Windows 10 / 11（PowerShell）における依存ソフトウェアのインストールと初期確認の手順です。全体の流れや共通の設定は [SETUP.md](../../../../SETUP.md) を参照してください。

## 1. 必要なソフトウェアのインストール

`winget` が使える環境では、PowerShell から次のツールを導入できます（`winget` が利用できない環境では、各公式サイトからインストーラーまたは ZIP 版を取得して `PATH` に通してください）。

```powershell
winget install Git.Git
winget install OpenJS.NodeJS.LTS
winget install Python.Python.3.13
winget install Gyan.FFmpeg
winget install astral-sh.uv
winget install Gitleaks.Gitleaks
```

> [!NOTE]
> `Gyan.FFmpeg` には `ffmpeg` と `ffprobe` の両方が含まれます。インストール後は新しい PowerShell ウィンドウを開き直して `PATH` を反映してください。

インストール後の確認（PowerShell）：

```powershell
git --version
node --version
npm --version
python --version
ffmpeg -version | Select-Object -First 1
ffprobe -version | Select-Object -First 1
gitleaks version
uv --version
```

## 2. 日本語フォント (Noto Sans CJK JP)

Windows の既定環境には `Noto Sans CJK JP` が入っていない場合があります。字幕や地名が豆腐（□）になるのを防ぐため、[Noto CJK](https://github.com/notofonts/noto-cjk/releases) または [Google Fonts (Noto Sans JP)](https://fonts.google.com/noto/specimen/Noto+Sans+JP) からフォントをダウンロードし、`.otf` / `.ttf` ファイルを右クリック →「インストール」で導入してください。

> [!TIP]
> `packages/pipeline/chapter_pipeline.py` のタイトルカード生成は Linux の `/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc` を既定のフォントパスにしています。Windows で章結合を実行する場合は、環境に存在する日本語フォントのパスへ合わせる必要があります。

## 3. 文字コード設定 (`PYTHONUTF8=1`)

Windows では Python の既定文字コードが UTF-8 ではないため、ログの文字化けや `UnicodeEncodeError` が起きることがあります。Python スクリプトを実行する前に PowerShell で UTF-8 モードを有効にしてください。

```powershell
$env:PYTHONUTF8 = "1"
```

## 4. レンダラーと Playwright Chromium の準備

```powershell
cd packages\renderer
npm install
npx playwright install chromium-headless-shell
npm run build
npm test
cd ..\..
```

## 5. Python 仮想環境 (venv)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install Pillow
```

PowerShell でスクリプト実行ポリシーのエラーが出る場合は、現在のユーザーのみ許可してください。

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 6. VOICEVOX エンジンの準備

Windows では次のいずれかで VOICEVOX エンジン（`http://127.0.0.1:50021`）を起動します。

- **VOICEVOX アプリ版**: Windows 版 VOICEVOX をインストールして起動しておく（起動中は `127.0.0.1:50021` で HTTP API が待ち受けます）。
- **Docker Desktop 版**: WSL 2 バックエンドの Docker Desktop で VOICEVOX エンジンコンテナを起動する。

PowerShell で疎通確認を行う際は、エイリアス（`Invoke-WebRequest`）を避けるため `curl.exe` または `Invoke-RestMethod` を使います。

```powershell
curl.exe http://127.0.0.1:50021/version
curl.exe http://127.0.0.1:50021/speakers
```

## 7. 最小動作確認（PowerShell）

プロジェクトデータの雛形を一時ディレクトリへコピーし、音声なしで静止画シートを書き出して確認します。

```powershell
$smoke = Join-Path $env:TEMP "geo-video-smoke"
New-Item -ItemType Directory -Force $smoke | Out-Null
Copy-Item -Recurse -Force .agents\skills\geo-video-renderer\assets\template\* $smoke

node packages\renderer\dist\src\render.js `
  "$smoke\shots\example.json" `
  --project $smoke `
  --out "$smoke\out\example" `
  --stills 2 --no-voice
```

GPU を利用できない環境では、PowerShell で環境変数を設定してから実行してください（ソフトウェア描画のため大幅に遅くなります）。

```powershell
$env:FLYOVER_GL = "swiftshader"
```
