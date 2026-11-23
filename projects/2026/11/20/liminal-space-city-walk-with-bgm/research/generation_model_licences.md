# 画像生成モデルのライセンスと、このプロジェクトの立場

2026-11-23 の記録です。モデルを足すとき、成果物にモデルの出力を入れるときは、先にここを見て、ここを直します。

## 立場

作品 (無人の渋谷) の拘束条件は、構成するソフトウェアとコンテンツのすべてが再配布可能・商用利用可能で、改変するものは改変も許されていることです。画像生成モデルについては、制作者が 2026-11-23 に次のように決めました。

- モデルの作者が求めるクレジット表記は受け入れる。モデルの出力を成果物に使ったら、モデルの名前と作者を `credits.json` と概要欄に書く。
- モデルを販売しない。モデルの重みも、それを混ぜたり追加学習したりしたモデルも、配布しない。
- リポジトリに入れるのは、取得元、版、ハッシュ、ライセンスの記録だけ。重みは入れない。
- 作品に入るのは、生成した画像だけ。作品は CC BY-SA で出す。
- 非商用のライセンスのモデル (FLUX.1-dev など) は使わない。取得もしない。

## 台帳

「状態」の「試走」は、1024×1024 を 1 枚ずつ生成して動くことを確かめただけで、成果物には使っていないという意味です。

| モデル | ライセンス | 取得元 (Hugging Face) と版 | 状態 |
|---|---|---|---|
| Stable Diffusion XL Base 1.0 | CreativeML Open RAIL++-M | `stabilityai/stable-diffusion-xl-base-1.0` | `v1.0.0` の路面テクスチャに使用 |
| ControlNet Depth SDXL 1.0 | カードに `openrail++` | `diffusers/controlnet-depth-sdxl-1.0` @ `17bb97973f29801224cd66f192c5ffacf82648b4` | 試走 |
| ControlNet Canny SDXL 1.0 | カードに `openrail++` | `diffusers/controlnet-canny-sdxl-1.0` @ `eb115a19a10d14909256db740ed109532ab1483c` | 試走 |
| RealVisXL V5.0 (作者 SG161222) | カードに `openrail++` (CreativeML Open RAIL++-M)。作者の Civitai のページに追加の条件 (下の節) | `SG161222/RealVisXL_V5.0` @ `ac93e0dda1f6d448cae19bbfab8c5e720a5e48bc` | 試走 |
| FLUX.1-schnell (Black Forest Labs) | Apache-2.0 | `Comfy-Org/Flux-1-Schnell` @ `d31e04067066d92c55ece2b01748dcc337725d7a` (ComfyUI 用の詰め直し。元は `black-forest-labs/FLUX.1-schnell`) | 試走 |
| Z-Image-Turbo (Tongyi-MAI) | Apache-2.0 | `Comfy-Org/Z-Image-Turbo` @ `6fc90a3b1b653e935a0d175e260736de25b84df5` (ComfyUI 用の詰め直し。元は `Tongyi-MAI/Z-Image-Turbo`) | 試走 |
| ComfyUI | GPL-3.0 | [comfyanonymous/ComfyUI](https://github.com/comfyanonymous/ComfyUI) | 生成を動かす道具。HTTP の API から呼ぶだけで、配布も改変もしない |

`v1.0.0` で使ったほかのモデル (RealESRGAN_x4plus、controlnet-tile-sdxl-1.0、sdxl-vae-fp16-fix) は [credits.json](../credits.json) にあります。

### 取得したファイル

| ファイル | SHA-256 |
|---|---|
| `sd_xl_base_1.0.safetensors` | `31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b` |
| `diffusion_pytorch_model.fp16.safetensors` (Depth) | `66a6813e6bd7270ecfe68206a59ddd605a011ae85321188376605c66e0a4f303` |
| `diffusion_pytorch_model.fp16.safetensors` (Canny) | `b2e7d3921058a442cc80430d1ec8847f42599c705e2451c95e77cf4dcf8d6c25` |
| `RealVisXL_V5.0_fp16.safetensors` | `6a35a7855770ae9820a3c931d4964c3817b6d9e3c6f9c4dabb5b3a94e5643b80` |
| `flux1-schnell-fp8.safetensors` | `ead426278b49030e9da5df862994f25ce94ab2ee4df38b556ddddb3db093bf72` |
| `split_files/diffusion_models/z_image_turbo_int8_convrot.safetensors` | `be517ebd47c912a5626a588e1aeea43e6be4a43c0cdcd2b48a2a780d9f358635` |
| `split_files/text_encoders/qwen_3_4b_fp8_mixed.safetensors` | `72450b19758172c5a7273cf7de729d1c17e7f434a104a00167624cba94f68f15` |
| `split_files/vae/ae.safetensors` | `afc8e28272cd15db3919bacdb6918ce9c1ed22e96cb12c4d5ed0fba823529e38` |

## CreativeML Open RAIL++-M が求めること

本文は `stabilityai/stable-diffusion-xl-base-1.0` の `LICENSE.md` (2023-07-26 付) で読みました。

- モデルとその派生物は、改変の有無によらず複製、配布できる。配布するときは、使用制限 (Attachment A) を受け手にも守らせ、ライセンスの写しを渡す。このプロジェクトはモデルを配布しないので、この条件は掛からない。
- 使用制限 (Attachment A) は、モデルを使う私たちに掛かる。違法な利用、人を害する利用などを禁じる内容で、無人の街の外壁や路面を生成する用途は当たらない。
- 出力について、ライセンサーは権利を主張しない (The Output You Generate の項)。ただし出力の使い方がライセンスに反してはならない。

出力の画像を CC BY-SA で出すことを妨げる条項は、読んだ範囲では見つかっていません。これは本文を読んだ記録で、法的な判断ではありません。

## RealVisXL V5.0

- Hugging Face のカード (`SG161222/RealVisXL_V5.0`) のライセンス欄は `openrail++`、つまり CreativeML Open RAIL++-M。
- 作者は同じファイルを Civitai ([models/139562](https://civitai.com/models/139562)、版 789646) でも配っている。SHA-256 は Hugging Face のファイルと一致する。Civitai の設定は次のとおり。
  - クレジットなしの利用は不可 (`allowNoCredit: false`)
  - 商用利用として許されているのは、生成した画像の販売と、生成サービスでの提供 (`Image`、`Rent`、`RentCivit`)。モデルやそれを混ぜたモデルの販売 (`Sell`) は入っていない
  - 派生物は可、派生物に別のライセンスを付けることも可
- 2 つの配布元で条件が違うので、厳しいほうに合わせる。上の「立場」のとおり、クレジットを書き、モデルを売らない。
- クレジットの書き方: `RealVisXL V5.0 by SG161222 (CreativeML Open RAIL++-M)`
- 作者はこのモデルを複数のモデルの混合と説明している (Civitai の説明に DreamShaper XL、Juggernaut XL など 11 の名前)。

## FLUX.1-schnell

- Apache-2.0。本文は Black Forest Labs の GitHub の `model_licenses/LICENSE-FLUX1-schnell` で読んだ。
- 元のリポジトリ `black-forest-labs/FLUX.1-schnell` は、Hugging Face のアカウントで条件に同意しないと取得できない。制作者が 2026-11-23 に自分のアカウントで同意した。
- 実際に取得したのは `Comfy-Org/Flux-1-Schnell` の FP8 の 1 ファイルで、カードのライセンス欄は `apache-2.0`。テキストエンコーダー (T5-XXL、CLIP-L) と VAE を同梱している。

## Z-Image-Turbo

- Apache-2.0。`Tongyi-MAI/Z-Image-Turbo` のカード、GitHub の LICENSE、`Comfy-Org/Z-Image-Turbo` のカードで確かめた。
- テキストエンコーダーは Qwen3-4B で、`Qwen/Qwen3-4B` の LICENSE は Apache-2.0。

## 見送ったもの

| 名前 | 理由 |
|---|---|
| FLUX.1-dev | 非商用のライセンス。取得していない |
| `Kijai/flux-fp8` | カードのライセンス欄が `other` |
| `city96/FLUX.1-schnell-gguf` | ライセンスは Apache-2.0 だが、読み込みに追加のカスタムノードが要る |

## 確かめていないこと

- ControlNet の 2 つは、カードに `openrail++` とあるだけで、リポジトリにライセンスの本文がない。SDXL Base 1.0 と同じ本文として扱っている。
- FLUX.1-schnell に同梱の CLIP-L の重み。`openai/clip-vit-large-patch14` のカードにライセンス欄がない (コードのリポジトリは MIT)。
- RealVisXL V5.0 に混ぜられた各モデルのライセンス。
- SDXL Base 1.0 を取得した版 (コミット)。`v1.0.0` より前に入れたもので、記録が残っていない。上のハッシュは手元のファイルのもの。
