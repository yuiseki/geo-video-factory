# 参考動画を取得する

## 置き場所

リポジトリの外に保管庫を作る。場所は利用者に聞くか、環境変数 `GEO_VIDEO_REFERENCES` があればそこを使う。1 本 1 フォルダで、フォルダ名は動画 ID。保管庫の直下に一覧の `README.md` (ID、チャンネル、題、長さ、公開日、取得日、利用者の一言) を置く。

## yt-dlp で取る

古い yt-dlp は途中で 403 になることがある。最新版を、JavaScript ランタイムを指定して使う (uv があれば入れずに動かせる)。

```bash
uvx --from "yt-dlp[default]" yt-dlp --js-runtimes node:$(readlink -f $(which node)) \
  -f "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]" --merge-output-format mp4 \
  --write-info-json --write-description --write-thumbnail \
  --write-subs --write-auto-subs --sub-langs "ja,ja-orig" \
  -o "%(id)s.%(ext)s" <URL>
```

できるもの:

| ファイル | 中身 |
|---|---|
| `<ID>.mp4` | 本体。1080p まで |
| `<ID>.info.json` | 再生数、高評価、コメント数、登録者数、公開時刻 (`timestamp`)、取得時刻 (`epoch`)、長さ、チャプター、タグ |
| `<ID>.description` | 概要欄。素材の出典、使った道具 (合成音声、AI 生成) が書かれていることが多い |
| `<ID>.webp` など | サムネイル |
| `<ID>.ja.vtt` | 字幕。作者が上げた字幕があればそれ、無ければ自動字幕 |
| `<ID>.ja-orig.vtt` | 自動字幕 (音声認識)。行が次の字幕に重なって繰り返される |

- 作者の字幕と自動字幕の両方があれば、作者の字幕を使う。どちらを使ったかを分析に書く。
- 高評価の数や登録者数は、非公開にされていると `null` になる。0 として扱わない。
- 取得の記録 (`dl.log`) を残す。失敗したときに、どの段で止まったかが分かる。

## 取り直すとき

数字は取得した時点の値なので、公開直後の動画は日をおいて `--skip-download --write-info-json` でメタデータだけ取り直すと、伸び方が分かる。前の `info.json` は日付を付けて残す。
