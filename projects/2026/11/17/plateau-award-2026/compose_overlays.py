#!/usr/bin/env python3
"""Generate custom transparent overlay videos (S08 AI workflow & S10 OSS ending)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PROJECT = Path(__file__).resolve().parent
OUT_OV = PROJECT / "overlays" / "generated"

# Noto Sans CJK JP or Hiragino fallback on macOS
FONT_CANDIDATES = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/NotoSansCJKjp-Bold.otf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]
MONO_CANDIDATES = [
    "/System/Library/Fonts/SFNSMono.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Courier.ttc",
]


def load_font(size: int, mono: bool = False) -> ImageFont.FreeTypeFont:
    for p in (MONO_CANDIDATES if mono else FONT_CANDIDATES):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def draw_round_rect(draw: ImageDraw.ImageDraw, xy, radius: int, fill, outline=None, width: int = 2) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def build_s08_overlay(fps: int = 30) -> Path:
    """S08 (11s): Prompt card -> Shot JSON snippet -> Rendered Mt. Fuji frame preview."""
    OUT_OV.mkdir(parents=True, exist_ok=True)
    frames_dir = OUT_OV / "s08_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    mov_path = OUT_OV / "S08_extra.mov"

    # Try to grab a sample frame from S06 if rendered (preview or final)
    fuji_img = None
    for cand in [
        PROJECT / "out/final/clips/S06/map/frames/00180.jpg",
        PROJECT / "out/preview/clips/S06/frames/00090.jpg",
    ]:
        if cand.exists():
            fuji_img = Image.open(cand).convert("RGBA").resize((760, 428), Image.Resampling.LANCZOS)
            break

    f_title = load_font(44)
    f_body = load_font(34)
    f_small = load_font(24)
    f_code = load_font(19, mono=False)

    total_frames = 11 * fps
    json_lines = [
        '{',
        '  "dem": "gsi", "exaggeration": 1.5,',
        '  "shots": [{',
        '    "duration": 10, "ease": "smooth",',
        '    "from": { "center": [138.727, 35.360], "zoom": 9.8 },',
        '    "to":   { "center": [138.705, 35.358], "zoom": 11.8 },',
        '    "lines": [{ "voice": "a", "text": "西側には大沢崩れ..." }]',
        '  }]',
        '}',
    ]

    for i in range(total_frames):
        t = i / fps
        img = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # Stage 1 (0.3s - 10.6s): Prompt card at top-left
        if 0.3 <= t <= 10.6:
            alpha = int(245 * min(1.0, (t - 0.3) / 0.35))
            draw_round_rect(d, [90, 80, 950, 290], 18, (14, 22, 36, alpha), outline=(96, 175, 255, alpha), width=3)
            d.text((125, 106), "自然言語での制作依頼", font=f_small, fill=(130, 200, 255, alpha))
            d.text((125, 152), "「富士山の大沢崩れについて、", font=f_body, fill=(245, 248, 252, alpha))
            d.text((125, 204), " 2人の掛け合いで3分の解説動画を作ってください」", font=f_body, fill=(245, 248, 252, alpha))

        # Stage 2 (3.2s - 10.6s): Shot JSON card at bottom-left
        if 3.2 <= t <= 10.6:
            alpha = int(245 * min(1.0, (t - 3.2) / 0.35))
            draw_round_rect(d, [90, 330, 950, 680], 18, (16, 20, 28, alpha), outline=(120, 220, 170, alpha), width=3)
            d.text((125, 354), "AIエージェントが生成するショット定義 (shots/fuji.json)", font=f_small, fill=(120, 230, 175, alpha))
            y = 402
            for line in json_lines:
                d.text((125, y), line, font=f_code, fill=(225, 236, 245, alpha))
                y += 29

        # Stage 3 (5.8s - 10.6s): Rendered video frame preview on right
        if 5.8 <= t <= 10.6:
            alpha = int(250 * min(1.0, (t - 5.8) / 0.4))
            draw_round_rect(d, [1020, 160, 1830, 680], 20, (14, 22, 36, alpha), outline=(255, 210, 90, alpha), width=3)
            d.text((1055, 186), "レンダラーが再現可能に描画 (1920×1080 MP4)", font=f_small, fill=(255, 220, 110, alpha))
            if fuji_img is not None:
                f_copy = fuji_img.copy()
                f_copy.putalpha(alpha)
                img.paste(f_copy, (1045, 230), f_copy)

        # Bottom summary telop
        if 3.5 <= t <= 10.6:
            msg = "書くのは、AIエージェント。" if t < 6.0 else "書くのは、AIエージェント。  動画は、ソフトウェアが描く。"
            alpha = int(240 * min(1.0, (t - 3.5) / 0.3))
            draw_round_rect(d, [90, 880, 1460, 970], 14, (10, 16, 28, alpha))
            d.text((125, 898), msg, font=f_title, fill=(255, 255, 255, alpha))

        img.save(frames_dir / f"{i:05d}.png")

    subprocess.run([
        "ffmpeg", "-y", "-framerate", str(fps),
        "-i", str(frames_dir / "%05d.png"),
        "-c:v", "png", "-pix_fmt", "rgba", str(mov_path),
    ], check=True)
    print(f"Built {mov_path}")
    return mov_path


def main() -> None:
    build_s08_overlay()


if __name__ == "__main__":
    main()
