"""Pure keyframe selection and non-occluding storyboard layout/composition.

Ports watch-mcp's core algorithms without external runtime dependencies beyond Pillow:
1. Activity-episode + binary-search-budget adaptive keyframe selection.
2. Non-occluding storyboard grids (caption strip above each tile, never over the frame).
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont

DEFAULT_PIXEL_THRESHOLD = 10
CUT_SHARE = 0.4
TILES_PER_SHEET = 16
SHEET_MAX_EDGE = 1556
LABEL_HEIGHT = 22
GUTTER = 4


@dataclass(frozen=True)
class SelectedFrame:
    index: int
    change: float
    cut: bool
    same_until: int


@dataclass(frozen=True)
class GridLayout:
    cols: int
    rows: int
    tile_w: int
    tile_h: int
    gutter: int
    label_h: int
    width: int
    height: int


def parse_time(raw: str | float | int) -> float:
    if isinstance(raw, (int, float)):
        val = float(raw)
        if val < 0 or not math.isfinite(val):
            raise ValueError(f'invalid time: {raw}')
        return val
    text = str(raw).strip()
    if not text:
        raise ValueError('empty time string')
    if ':' not in text:
        val = float(text)
        if val < 0:
            raise ValueError(f'negative time: {raw}')
        return val
    parts = [float(p) for p in text.split(':')]
    if len(parts) == 2:
        return parts[0] * 60.0 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600.0 + parts[1] * 60.0 + parts[2]
    raise ValueError(f'invalid timestamp "{raw}"')


def format_time(seconds: float, decimals: int = 1, with_hours: bool = False) -> str:
    sec = max(0.0, seconds)
    hrs = int(sec // 3600)
    mins = int((sec % 3600) // 60)
    rem = sec % 60.0
    sec_fmt = f'{rem:0{3 + decimals if decimals > 0 else 2}.{decimals}f}'
    if with_hours or hrs > 0:
        return f'{hrs:d}:{mins:02d}:{sec_fmt}'
    return f'{mins:02d}:{sec_fmt}'


def parse_crop(raw: str | None) -> tuple[float, float, float, float] | None:
    if raw is None:
        return None
    parts = [float(p.strip()) for p in raw.split(',')]
    if len(parts) != 4:
        raise ValueError(f'crop must be x,y,w,h (got "{raw}")')
    x, y, w, h = parts
    if not (0.0 <= x < 1.0 and 0.0 <= y < 1.0 and 0.0 < w <= 1.0 and 0.0 < h <= 1.0):
        raise ValueError(f'crop values out of range (0..1): {parts}')
    if x + w > 1.001 or y + h > 1.001:
        raise ValueError(f'crop box exceeds frame bounds: {parts}')
    return (x, y, min(w, 1.0 - x), min(h, 1.0 - y))


def count_changed_pixels(a: bytes, b: bytes, threshold: int, stop_at: int) -> int:
    count = 0
    for pa, pb in zip(a, b):
        if abs(pa - pb) > threshold:
            count += 1
            if count >= stop_at:
                return count
    return count


def select_keyframes(
    sigs: Sequence[bytes],
    *,
    budget: int = 16,
    pixel_threshold: int = DEFAULT_PIXEL_THRESHOLD,
    merge_gap_samples: int = 1,
) -> list[SelectedFrame]:
    n = len(sigs)
    if n == 0:
        return []
    size = len(sigs[0])
    if size == 0 or any(len(s) != size for s in sigs):
        raise ValueError('select_keyframes: signatures must be non-empty and uniform in size')

    budget = max(1, int(budget))
    min_need = max(2, math.ceil(size * 0.0003))
    steps = [0] + [count_changed_pixels(sigs[k - 1], sigs[k], pixel_threshold, size + 1) for k in range(1, n)]

    episodes: list[tuple[int, int]] = []
    k = 1
    while k < n:
        if steps[k] < min_need:
            k += 1
            continue
        before = k - 1
        best_rep, best_score = k, -1
        quiet = 0
        while k < n and quiet <= merge_gap_samples:
            if steps[k] >= min_need:
                quiet = 0
                score = count_changed_pixels(sigs[before], sigs[k], pixel_threshold, size + 1)
                if score >= best_score:
                    best_rep, best_score = k, score
            else:
                quiet += 1
            k += 1
        episodes.append((best_rep, best_score))

    target = max(1, budget - 1)
    ep_limit = max(0, target - 1)
    chosen_eps = episodes if len(episodes) <= ep_limit else sorted(episodes, key=lambda e: e[1], reverse=True)[:ep_limit]
    seeds = set(sorted(rep for rep, _ in chosen_eps))

    def greedy(need: int) -> list[int]:
        kept = [0]
        last = 0
        for idx in range(1, n):
            if idx in seeds or count_changed_pixels(sigs[last], sigs[idx], pixel_threshold, need) >= need:
                kept.append(idx)
                last = idx
        return kept

    if len(greedy(min_need)) <= target:
        picked = greedy(min_need)
    else:
        lo, hi = min_need, size + 1
        while lo < hi:
            mid = (lo + hi) // 2
            if len(greedy(mid)) <= target:
                hi = mid
            else:
                lo = mid + 1
        picked = greedy(lo)[:target]

    last_idx = n - 1
    if picked[-1] != last_idx and len(picked) < budget:
        if count_changed_pixels(sigs[picked[-1]], sigs[last_idx], pixel_threshold, min_need) >= min_need:
            picked.append(last_idx)

    selected: list[SelectedFrame] = []
    for p, idx in enumerate(picked):
        change = 0.0 if p == 0 else count_changed_pixels(sigs[picked[p - 1]], sigs[idx], pixel_threshold, size + 1) / size
        next_picked = picked[p + 1] if p + 1 < len(picked) else n
        same_until = idx
        while same_until + 1 < next_picked and count_changed_pixels(sigs[idx], sigs[same_until + 1], pixel_threshold, min_need) < min_need:
            same_until += 1
        selected.append(SelectedFrame(index=idx, change=change, cut=(steps[idx] / size) >= CUT_SHARE, same_until=same_until))
    return selected


def choose_grid(
    aspect: float,
    *,
    count: int,
    per_sheet: int = TILES_PER_SHEET,
    max_edge: int = SHEET_MAX_EDGE,
    gutter: int = GUTTER,
    label_h: int = LABEL_HEIGHT,
) -> GridLayout:
    if aspect <= 0 or count < 1:
        raise ValueError('aspect and count must be positive')
    cap = min(per_sheet, count)
    best: tuple[int, int, int, int] | None = None
    for cols in range(1, cap + 1):
        rows = math.ceil(cap / cols)
        if cols * rows > per_sheet:
            continue
        by_w = (max_edge - (cols + 1) * gutter) / (cols * aspect)
        by_h = (max_edge - (rows + 1) * gutter - rows * label_h) / rows
        tile_h = int(min(by_w, by_h) // 2) * 2
        tile_w = int((tile_h * aspect) // 2) * 2
        if tile_h < 2 or tile_w < 2:
            continue
        area = tile_w * tile_h
        if best is None or area > best[2] * best[3]:
            best = (cols, rows, tile_w, tile_h)
    if best is None:
        raise ValueError('no grid fits within max_edge')
    cols, rows, tile_w, tile_h = best
    width = cols * tile_w + (cols + 1) * gutter
    height = rows * (tile_h + label_h) + (rows + 1) * gutter
    return GridLayout(cols=cols, rows=rows, tile_w=tile_w, tile_h=tile_h, gutter=gutter, label_h=label_h, width=width, height=height)


def compose_storyboard(
    tiles: Sequence[tuple[Image.Image, str]],
    layout: GridLayout,
    out_path: Path,
    *,
    overwrite: bool = False,
) -> Path:
    if out_path.exists() and not overwrite:
        raise FileExistsError(f'output already exists: {out_path}')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new('RGB', (layout.width, layout.height), (24, 24, 24))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for i, (img, label) in enumerate(tiles):
        col = i % layout.cols
        row = i // layout.cols
        if row >= layout.rows:
            break
        x = layout.gutter + col * (layout.tile_w + layout.gutter)
        y = layout.gutter + row * (layout.tile_h + layout.label_h + layout.gutter)
        draw.rectangle([x, y, x + layout.tile_w - 1, y + layout.label_h - 1], fill=(0, 0, 0))
        draw.text((x + 6, y + 5), label, fill=(255, 255, 255), font=font)
        resized = img.convert('RGB').resize((layout.tile_w, layout.tile_h), Image.Resampling.LANCZOS)
        canvas.paste(resized, (x, y + layout.label_h))
    canvas.save(out_path, quality=92)
    return out_path


def format_timeline(selected: Sequence[SelectedFrame], times: Sequence[float], per_sheet: int = TILES_PER_SHEET) -> str:
    with_hours = times[-1] >= 3600 if times else False
    lines = ['TIMELINE (SEEN = keyframe; in time order):']
    for i, sf in enumerate(selected, start=1):
        sheet = ((i - 1) // per_sheet) + 1
        t_str = format_time(times[sf.index], 1, with_hours)
        if i == 1:
            desc = 'start'
        elif sf.cut:
            desc = 'cut (new scene)'
        elif sf.change < 0.01:
            desc = 'small change (<1%)'
        else:
            desc = f'{round(sf.change * 100)}% changed'
        if sf.same_until > sf.index:
            desc += f'; unchanged until {format_time(times[sf.same_until], 1, with_hours)}'
        lines.append(f'{t_str}  SEEN #{i} (storyboard {sheet})  {desc}')
    return '\n'.join(lines)
