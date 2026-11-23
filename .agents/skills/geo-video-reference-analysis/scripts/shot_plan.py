"""Build a 4-layer shot-by-shot deconstruction & remake skeleton from measured reference outputs.

Combines cuts.txt (from media.py), motion.tsv (from motion.py), transcript.txt (from transcript.py),
and optional info.json (for duration and chapters) into either JSON or a layered Markdown blueprint.

usage:
  python3 shot_plan.py --cuts cuts.txt --duration 600 \
    [--motion motion.tsv] [--transcript transcript.txt] [--info a.info.json] \
    [--min-shot 0.5] [--out SHOT_PLAN.md] [--json]
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import statistics as st
from typing import Any

REMAKE_ROUTES = ('renderer標準', 'pipeline事前生成', '素材収集', '要新規実装')
TRANSCRIPT_LINE = re.compile(r'^(\d+):(\d{2})\s+(.*)$')


def fmt_mmss(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    return f'{total // 60:02d}:{total % 60:02d}'


def parse_cuts_txt(text: str) -> list[float]:
    return [float(line.strip()) for line in text.splitlines() if line.strip()]


def parse_motion_tsv(text: str) -> list[tuple[float, str]]:
    rows: list[tuple[float, str]] = []
    for line in text.splitlines():
        if not line.strip() or line.startswith('t\t'):
            continue
        parts = line.split('\t')
        if len(parts) >= 6:
            rows.append((float(parts[0]), parts[5].strip()))
    return rows


def parse_transcript_txt(text: str) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    for line in text.splitlines():
        m = TRANSCRIPT_LINE.match(line.strip())
        if m:
            t = int(m.group(1)) * 60 + int(m.group(2))
            out.append((float(t), m.group(3).strip()))
    return out


def build_intervals(cuts: list[float], duration: float, min_shot: float = 0.5) -> list[tuple[float, float]]:
    if duration <= 0:
        return []
    points = [0.0]
    for c in sorted(cuts):
        if c <= 0.0 or c >= duration:
            continue
        if c - points[-1] < min_shot:
            continue
        points.append(c)
    if duration - points[-1] < min_shot and len(points) > 1:
        points.pop()
    points.append(duration)
    return [(round(a, 2), round(b, 2)) for a, b in zip(points, points[1:])]


def _chapter_at(t: float, chapters: list[dict[str, Any]]) -> str:
    for c in chapters:
        start = float(c.get('start_time', 0.0))
        end = float(c.get('end_time', float('inf')))
        if start <= t < end:
            return str(c.get('title') or '')
    return ''


def _dominant_motion(start: float, end: float, motion_rows: list[tuple[float, str]]) -> str:
    labels = [lbl for t, lbl in motion_rows if start <= t < end and lbl != 'cut']
    if not labels:
        return 'unknown'
    return collections.Counter(labels).most_common(1)[0][0]


def _caption_excerpt(start: float, end: float, captions: list[tuple[float, str]], max_chars: int = 40) -> str:
    joined = ' '.join(text for t, text in captions if start <= t < end).strip()
    if len(joined) > max_chars:
        return joined[:max_chars - 1] + '…'
    return joined


def build_shots(
    cuts: list[float],
    duration: float,
    motion_rows: list[tuple[float, str]] | None = None,
    captions: list[tuple[float, str]] | None = None,
    chapters: list[dict[str, Any]] | None = None,
    min_shot: float = 0.5,
) -> list[dict[str, Any]]:
    motion_rows = motion_rows or []
    captions = captions or []
    chapters = chapters or []
    shots: list[dict[str, Any]] = []
    for idx, (start, end) in enumerate(build_intervals(cuts, duration, min_shot=min_shot), start=1):
        mid = (start + end) / 2.0
        shots.append({
            'id': f'S{idx:03d}',
            'start': start,
            'end': end,
            'duration': round(end - start, 2),
            'chapter': _chapter_at(mid, chapters),
            'dominant_motion': _dominant_motion(start, end, motion_rows),
            'caption': _caption_excerpt(start, end, captions),
        })
    return shots


def summarise_shots(shots: list[dict[str, Any]], duration: float) -> dict[str, Any]:
    durations = [s['duration'] for s in shots]
    motion_counts = dict(collections.Counter(s['dominant_motion'] for s in shots))
    cuts_count = max(0, len(shots) - 1)
    return {
        'duration_seconds': round(duration, 2),
        'shot_count': len(shots),
        'cuts_per_min': round(cuts_count / (duration / 60.0), 2) if duration > 0 else 0.0,
        'mean_shot_seconds': round(st.mean(durations), 2) if durations else 0.0,
        'median_shot_seconds': round(st.median(durations), 2) if durations else 0.0,
        'min_shot_seconds': round(min(durations), 2) if durations else 0.0,
        'max_shot_seconds': round(max(durations), 2) if durations else 0.0,
        'motion_counts': motion_counts,
    }


def render_markdown(shots: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    motion_str = ', '.join(f'{k}: {v}' for k, v in sorted(summary['motion_counts'].items(), key=lambda kv: -kv[1]))
    routes_str = ' / '.join(REMAKE_ROUTES)
    lines = [
        '# ショット分解・再現プラン',
        '',
        '## Layer 1: 全体要約・フック構造',
        '',
        '| 項目 | 測定値 / 記入欄 |',
        '|---|---|',
        f"| 長さ / ショット数 | {summary['duration_seconds']} 秒 / {summary['shot_count']} ショット |",
        f"| カット頻度 | {summary['cuts_per_min']} 回/分 |",
        f"| ショット長 (中央値 / 平均 / 最短〜最長) | {summary['median_shot_seconds']}s / {summary['mean_shot_seconds']}s / {summary['min_shot_seconds']}〜{summary['max_shot_seconds']}s |",
        f'| カメラ動き分布 | {motion_str or "未測定"} |',
        '| 冒頭フック (0〜5秒 / 0〜30秒) | (観察事実と推定を分けて記入) |',
        '| 全体を貫く物差し | (時計 / 年 / 目次 / 積む地図 など) |',
        '',
        '## Layer 2: マスターショットタイムライン',
        '',
        f'再現手段の分類: `{routes_str}`',
        '',
        '| Shot | 開始-終了 | 秒 | 章 | カメラ動き (測定) | カット種別 | 画面レイヤー | 音声レイヤー | 再現手段 | 発話抜粋 |',
        '|---|---|---:|---|---|---|---|---|---|---|',
    ]
    for s in shots:
        span = f"{fmt_mmss(s['start'])}-{fmt_mmss(s['end'])}"
        cap = s['caption'].replace('|', '｜')
        chap = s['chapter'].replace('|', '｜')
        lines.append(
            f"| {s['id']} | {span} | {s['duration']:.1f} | {chap} | {s['dominant_motion']} |  |  |  |  | {cap} |"
        )
    lines.extend([
        '',
        '## Layer 3: 主要ショット詳細分解と再現プラン',
        '',
        '代表ショットや導入・転換点について、**観察事実**と**推定**を分けて記録する。',
        '',
        '- **ベース画層**: 地図カメラ / 3D地形・建物 / 写真 / 平らな図解 / タイトルカード / 左右比較',
        '- **オーバーレイ層**: 字幕（位置・色・縁取り）/ 地名・注釈 / 常駐物差し / 数値カード / 立ち絵 / 出典',
        '- **再現ルート**: `renderer標準` / `pipeline事前生成` / `素材収集` / `要新規実装`',
        '',
        '## Layer 4: 音声・リズム・字幕アライメント',
        '',
        '- **声**: 話者数・役割・発話速度・沈黙の間',
        '- **BGM**: 連続性・テンポ (BPM)・ダッキング有無',
        '- **効果音・音ハメ**: カット点や図解出現と音の立ち上がりの一致',
        '- **字幕設計**: 同期の粒度・色分け・画面占有率',
        '',
    ])
    return '\n'.join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description='Generate a 4-layer shot deconstruction skeleton.')
    ap.add_argument('--cuts', help='path to cuts.txt from media.py')
    ap.add_argument('--motion', help='path to motion.tsv from motion.py')
    ap.add_argument('--transcript', help='path to transcript.txt from transcript.py')
    ap.add_argument('--info', help='path to <ID>.info.json for duration and chapters')
    ap.add_argument('--duration', type=float, help='video duration in seconds (overrides info.json)')
    ap.add_argument('--min-shot', type=float, default=0.5, help='merge cuts shorter than this (seconds)')
    ap.add_argument('--out', help='output file path (prints to stdout if omitted)')
    ap.add_argument('--json', action='store_true', dest='as_json', help='output JSON instead of Markdown')
    a = ap.parse_args()

    info = json.loads(pathlib.Path(a.info).read_text(encoding='utf-8')) if a.info else {}
    duration = a.duration if a.duration is not None else float(info.get('duration') or 0.0)
    if duration <= 0:
        raise SystemExit('duration is required (pass --duration or --info with duration)')

    cuts = parse_cuts_txt(pathlib.Path(a.cuts).read_text(encoding='utf-8')) if a.cuts else []
    motion_rows = parse_motion_tsv(pathlib.Path(a.motion).read_text(encoding='utf-8')) if a.motion else []
    captions = parse_transcript_txt(pathlib.Path(a.transcript).read_text(encoding='utf-8')) if a.transcript else []
    chapters = info.get('chapters') or []

    shots = build_shots(cuts, duration, motion_rows=motion_rows, captions=captions,
                        chapters=chapters, min_shot=a.min_shot)
    summary = summarise_shots(shots, duration)
    output = (json.dumps({'summary': summary, 'shots': shots}, ensure_ascii=False, indent=2) + '\n'
              if a.as_json else render_markdown(shots, summary))
    if a.out:
        pathlib.Path(a.out).write_text(output, encoding='utf-8')
    else:
        print(output)


if __name__ == '__main__':
    main()
