"""Cards and overlays for a video of scenes, drawn with Pillow: a title card, an end card with the credits, and
per-scene overlays (a place name in two languages, a small credit line).

Every position and size is a fraction of the frame, so the same card works at any resolution. Each function
returns an image and takes the frame size and a font loader: nothing is read from globals, and a test can pass
Pillow's built-in face instead of an installed font. scene_assembly.py puts the results into a video.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# (role, pixel size) -> font. The roles are "serif" (titles, place names) and "sans" (everything small).
FontLoader = Callable[[str, int], ImageFont.FreeTypeFont]

DEFAULT_FONT_PATHS = {
    "serif": "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "sans": "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
}
FONT_VARIABLES = {"serif": "FONT_SERIF", "sans": "FONT_SANS"}
BACKGROUND = (6, 7, 10)
END_CARD_HEADING, END_CARD_LINE, END_CARD_GAP = 0.095, 0.047, 0.02  # fractions of the frame height
END_CARD_MAX = 0.9


def font_paths(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """The font file of each role: FONT_SERIF / FONT_SANS when set, Noto CJK where Debian and Ubuntu install it."""
    environ = os.environ if environ is None else environ
    return {role: environ.get(variable, DEFAULT_FONT_PATHS[role]) for role, variable in FONT_VARIABLES.items()}


def truetype_fonts(paths: Mapping[str, str]) -> FontLoader:
    def load(role: str, size: int) -> ImageFont.FreeTypeFont:
        path = paths[role]
        # FreeType's own message ("cannot open resource") names neither the file nor the way to move it.
        if not Path(path).is_file():
            raise FileNotFoundError(f"no font file at {path}: set {FONT_VARIABLES[role]} to the {role} font")
        return ImageFont.truetype(path, size, index=0)
    return load


def spaced(draw, xy, text, fnt, fill, spacing=0.0):
    """Text with extra space between the letters; returns the x where it ends."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + spacing
    return x


def width(draw, text, fnt, spacing=0.0):
    """The width spaced() covers, without the gap after the last letter (so that centring is exact)."""
    return sum(draw.textlength(ch, font=fnt) + spacing for ch in text) - spacing


def with_shadow(layer: Image.Image) -> Image.Image:
    """The text layer over a soft dark copy of itself, so that it reads on a bright road or sky."""
    alpha = layer.getchannel("A")
    shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(10)).point(lambda v: min(255, int(v * 1.6))))
    tight = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    tight.putalpha(alpha.filter(ImageFilter.GaussianBlur(2)).point(lambda v: min(255, int(v * 1.3))))
    return Image.alpha_composite(Image.alpha_composite(shadow, tight), layer)


def place_label(ja: str, en: str, size: tuple[int, int], fonts: FontLoader) -> Image.Image:
    """Transparent overlay: the place name large, a short rule, the second name in spaced capitals; lower left."""
    W, H = size
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x, y = round(W * 0.05), round(H * 0.70)
    big, small = fonts("serif", round(H * 0.075)), fonts("sans", round(H * 0.031))
    spaced(d, (x, y), ja, big, (255, 255, 255, 255), spacing=H * 0.006)
    d.rectangle([x + 4, y + H * 0.108, x + 4 + H * 0.09, y + H * 0.108 + 3], fill=(255, 255, 255, 230))
    spaced(d, (x + 4, y + H * 0.122), en.upper(), small, (255, 255, 255, 240), spacing=H * 0.004)
    return with_shadow(im)


def credit_line(text: str, size: tuple[int, int], fonts: FontLoader) -> Image.Image:
    """Transparent overlay: one small line that ends at the right margin, at the bottom of the frame."""
    W, H = size
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = fonts("sans", round(H * 0.024))
    w = d.textlength(text, font=f)
    d.text((W - round(W * 0.03) - w, H - round(H * 0.055)), text, font=f, fill=(255, 255, 255, 225))
    return with_shadow(im)


def title_card(ja: str, en: str, size: tuple[int, int], fonts: FontLoader) -> Image.Image:
    """Opaque dark frame with the title and a smaller second line, both letter-spaced and centred."""
    W, H = size
    im = Image.new("RGB", (W, H), BACKGROUND)
    d = ImageDraw.Draw(im)
    big, small = fonts("serif", round(H * 0.13)), fonts("sans", round(H * 0.034))
    sp = H * 0.03
    spaced(d, ((W - width(d, ja, big, sp)) / 2, H * 0.36), ja, big, (245, 245, 240), sp)
    sp = H * 0.016
    spaced(d, ((W - width(d, en, small, sp)) / 2, H * 0.56), en, small, (190, 195, 205), sp)
    return im


def end_card_block_height(lines: Sequence[str], height: float) -> float:
    """Pixels the heading and the lines take; an empty line is a short gap."""
    return height * END_CARD_HEADING + sum(height * (END_CARD_LINE if line else END_CARD_GAP) for line in lines)


def end_card(heading: str, lines: Sequence[str], size: tuple[int, int], fonts: FontLoader) -> Image.Image:
    """Opaque dark frame with a heading and the credits, the block centred vertically.

    A line "label<TAB>text" puts a dim label at the left margin and the text in a second column; a line without
    a tab is a sentence from the left margin; an empty line is a gap. The lines are not wrapped or shrunk, so a
    block taller than END_CARD_MAX of the frame is refused instead of being drawn off the edge.
    """
    W, H = size
    block = end_card_block_height(lines, H)
    if not block < H * END_CARD_MAX:
        raise ValueError(f"the end card overflows: {block / H:.2f} of the frame height (limit {END_CARD_MAX})")
    im = Image.new("RGB", (W, H), BACKGROUND)
    d = ImageDraw.Draw(im)
    head, body = fonts("serif", round(H * 0.05)), fonts("sans", round(H * 0.0285))
    y = (H - block) / 2 - H * 0.01
    d.text((W * 0.08, y), heading, font=head, fill=(245, 245, 240))
    y += H * END_CARD_HEADING
    for line in lines:
        if not line:
            y += H * END_CARD_GAP
            continue
        label, _, text = line.partition("\t")
        if text:
            d.text((W * 0.08, y), label, font=body, fill=(150, 158, 172))
            d.text((W * 0.25, y), text, font=body, fill=(232, 232, 228))
        else:
            d.text((W * 0.08, y), label, font=body, fill=(232, 232, 228))
        y += H * END_CARD_LINE
    return im
