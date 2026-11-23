"""assemble.py <plan.json> <scenes root> <work dir> <out.mp4> [--crf=18]
Puts the rendered scenes of "Tokyo, Without People" together: a title card, every scene with its place name (fades
in and out) and a small credit line (stays), crossfades between them, an end card with every credit, the BGM
(generate_ambient_bgm.py, turning to the night chords where the first scene marked "night" begins), mastered to
-14 LUFS / -1.5 dBTP in two passes.
A scene is the frames <scenes root>/<name>/<frames dir>/%04d.png (frames dir defaults to f_mac). The cards are
drawn with Pillow in Noto CJK (FONT_SERIF, FONT_SANS override the paths). Nothing is overwritten: the work dir and
the output must be new. Run it under the host's resource limits; ffmpeg inherits them."""
import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "packages" / "pipeline"))
import ffmpeg_ops  # noqa: E402

plan = json.load(open(sys.argv[1]))
root, work, out = Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
opts = dict(a[2:].split("=", 1) for a in sys.argv[5:] if a.startswith("--"))
if out.exists():
    sys.exit(f"{out} exists: give a new version")
work.mkdir(parents=True, exist_ok=False)
W, H = plan["size"]
FPS, X = plan["fps"], plan["crossfade"]
SERIF = os.environ.get("FONT_SERIF", "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc")
SANS = os.environ.get("FONT_SANS", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
FF = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin"]


def font(path, size):
    return ImageFont.truetype(path, size, index=0)


def spaced(draw, xy, text, fnt, fill, spacing=0.0):
    """Text with extra space between the letters; returns the x where it ends."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + spacing
    return x


def width(draw, text, fnt, spacing=0.0):
    return sum(draw.textlength(ch, font=fnt) + spacing for ch in text) - spacing


def with_shadow(layer):
    """The text layer over a soft dark copy of itself, so that it reads on a bright road or sky."""
    alpha = layer.getchannel("A")
    shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(10)).point(lambda v: min(255, int(v * 1.6))))
    tight = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    tight.putalpha(alpha.filter(ImageFilter.GaussianBlur(2)).point(lambda v: min(255, int(v * 1.3))))
    return Image.alpha_composite(Image.alpha_composite(shadow, tight), layer)


def place_label(scene, path):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x, y = round(W * 0.05), round(H * 0.70)
    ja, en = font(SERIF, round(H * 0.075)), font(SANS, round(H * 0.031))
    spaced(d, (x, y), scene["ja"], ja, (255, 255, 255, 255), spacing=H * 0.006)
    d.rectangle([x + 4, y + H * 0.108, x + 4 + H * 0.09, y + H * 0.108 + 3], fill=(255, 255, 255, 230))
    spaced(d, (x + 4, y + H * 0.122), scene["en"].upper(), en, (255, 255, 255, 240), spacing=H * 0.004)
    with_shadow(im).save(path)


def credit_line(scene, path):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = font(SANS, round(H * 0.024))
    w = d.textlength(scene["credit"], font=f)
    d.text((W - round(W * 0.03) - w, H - round(H * 0.055)), scene["credit"], font=f, fill=(255, 255, 255, 225))
    with_shadow(im).save(path)


def title_card(t, path):
    im = Image.new("RGB", (W, H), (6, 7, 10))
    d = ImageDraw.Draw(im)
    ja, en = font(SERIF, round(H * 0.13)), font(SANS, round(H * 0.034))
    sp = H * 0.03
    spaced(d, ((W - width(d, t["ja"], ja, sp)) / 2, H * 0.36), t["ja"], ja, (245, 245, 240), sp)
    sp = H * 0.016
    spaced(d, ((W - width(d, t["en"], en, sp)) / 2, H * 0.56), t["en"], en, (190, 195, 205), sp)
    im.save(path)


def end_card(c, path):
    im = Image.new("RGB", (W, H), (6, 7, 10))
    d = ImageDraw.Draw(im)
    head, body = font(SERIF, round(H * 0.05)), font(SANS, round(H * 0.0285))
    block = H * 0.095 + sum(H * (0.047 if line else 0.02) for line in c["lines"])
    assert block < H * 0.9, f"the end card overflows: {block / H:.2f}"
    y = (H - block) / 2 - H * 0.01
    d.text((W * 0.08, y), c["heading"], font=head, fill=(245, 245, 240))
    y += H * 0.095
    for line in c["lines"]:
        if not line:
            y += H * 0.02
            continue
        label, _, text = line.partition("\t")
        if text:
            d.text((W * 0.08, y), label, font=body, fill=(150, 158, 172))
            d.text((W * 0.25, y), text, font=body, fill=(232, 232, 228))
        else:
            d.text((W * 0.08, y), label, font=body, fill=(232, 232, 228))
        y += H * 0.047
    im.save(path)


def run(args):
    subprocess.run(args, check=True)


def still(png, seconds, path, fade_in=0.0, fade_out=0.0):
    vf = [f"fps={FPS}", "format=yuv420p"]
    if fade_in:
        vf.append(f"fade=t=in:st=0:d={fade_in}")
    if fade_out:
        vf.append(f"fade=t=out:st={seconds - fade_out}:d={fade_out}")
    run([*FF, "-loop", "1", "-t", str(seconds), "-i", str(png), "-vf", ",".join(vf),
         "-c:v", "libx264", "-crf", "12", "-preset", "medium", str(path)])


clips, at, night_from = [], 0.0, None
title_card(plan["title"], work / "title.png")
still(work / "title.png", plan["title"]["seconds"], work / "00_title.mp4", fade_in=1.2)
clips.append((work / "00_title.mp4", plan["title"]["seconds"]))
for i, sc in enumerate(plan["scenes"], 1):
    frames = sorted((root / sc["name"] / sc.get("frames_dir", "f_mac")).glob("[0-9]*.png"))
    assert frames, f"no frames for {sc['name']}"
    assert Image.open(frames[0]).size == (W, H), f"{sc['name']} is not {W} x {H}"
    seconds = len(frames) / FPS
    place_label(sc, work / f"{i:02d}_label.png")
    credit_line(sc, work / f"{i:02d}_credit.png")
    clip = work / f"{i:02d}_{sc['name']}.mp4"
    fc = (f"[1]format=rgba,fade=t=in:st=1.2:d=1.0:alpha=1,fade=t=out:st={min(7.0, seconds - 3)}:d=1.2:alpha=1[l];"
          f"[2]format=rgba,fade=t=in:st=1.2:d=1.0:alpha=1[c];[0][l]overlay[a];[a][c]overlay,format=yuv420p")
    run([*FF, "-framerate", str(FPS), "-start_number", "0", "-i", str(frames[0].parent / "%04d.png"),
         "-loop", "1", "-t", str(seconds), "-i", str(work / f"{i:02d}_label.png"),
         "-loop", "1", "-t", str(seconds), "-i", str(work / f"{i:02d}_credit.png"),
         "-filter_complex", fc, "-frames:v", str(len(frames)), "-c:v", "libx264", "-crf", "12", "-preset", "medium", str(clip)])
    start = sum(s for _, s in clips) - len(clips) * X
    if sc.get("night") and night_from is None:
        night_from = start
    clips.append((clip, seconds))
    print(f"{sc['name']}: {len(frames)} frames, starts at {start:.1f} s", flush=True)
end_card(plan["credits"], work / "credits.png")
still(work / "credits.png", plan["credits"]["seconds"], work / "99_credits.mp4", fade_out=2.0)
clips.append((work / "99_credits.mp4", plan["credits"]["seconds"]))
total = sum(s for _, s in clips) - (len(clips) - 1) * X

bgm = work / "bgm.wav"
cmd = [sys.executable, str(Path(__file__).with_name("generate_ambient_bgm.py")), str(bgm), f"{total:.3f}"]
if night_from is not None:
    cmd.append(f"--night-from={night_from:.2f}")
run(cmd)

inputs, fc, last, offset = [], [], "0:v", 0.0
for k, (clip, seconds) in enumerate(clips):
    inputs += ["-i", str(clip)]
    if k:
        offset += clips[k - 1][1] - X
        fc.append(f"[{last}][{k}:v]xfade=transition=fade:duration={X}:offset={offset:.4f}[v{k}]")
        last = f"v{k}"
silent = work / "video.mp4"
run([*FF, *inputs, "-filter_complex", ";".join(fc), "-map", f"[{last}]", "-c:v", "libx264", "-crf", opts.get("crf", "18"),
     "-preset", "slow", "-pix_fmt", "yuv420p", "-r", str(FPS), str(silent)])
mixed = work / "mixed.mp4"
run([*FF, "-i", str(silent), "-i", str(bgm), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "pcm_s16le",
     "-shortest", str(mixed.with_suffix(".mov"))])
res = ffmpeg_ops.normalize_loudness(mixed.with_suffix(".mov"), out)
print(f"{out}: {total:.1f} s, night from {night_from}, loudness before mastering {res['measured']}")
