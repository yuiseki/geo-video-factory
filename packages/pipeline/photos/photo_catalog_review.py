"""Image inspection, deduplication, contact sheet generation, pruning, and index merging."""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
if str(_Path(__file__).resolve().parents[1]) not in _sys.path:
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from datetime import datetime
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from photos.photo_catalog_rules import find_gitleaks_hex32_matches, is_strict_cc0
from photos.photo_store import photo_file


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_existing_dedup_keys(
    existing_dirs: list[Path] | None = None,
    existing_manifests: list[Path] | None = None,
) -> dict:
    """Load URLs, lowercase titles, and SHA-256 digests from existing directories/manifests."""
    urls: set[str] = set()
    titles: set[str] = set()
    sha256s: set[str] = set()

    for mpath in existing_manifests or []:
        p = Path(mpath)
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        entries = data.get("photos", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        for item in entries:
            if not isinstance(item, dict):
                continue
            for uk in ("original_url", "download_url", "landing_url", "url"):
                u = item.get(uk)
                if isinstance(u, str) and u:
                    urls.add(u.split("?")[0])
                    urls.add(u)
            t = item.get("title")
            if isinstance(t, str) and t:
                titles.add(t.strip().lower())
            s = item.get("sha256")
            if isinstance(s, str) and len(s) == 64:
                sha256s.add(s.lower())

    for dpath in existing_dirs or []:
        d = Path(dpath)
        if not d.exists():
            continue
        for fp in d.rglob("*"):
            if not fp.is_file() or fp.name.startswith("."):
                continue
            if fp.stat().st_size < 128:
                continue
            try:
                sha256s.add(file_sha256(fp))
            except OSError:
                continue

    return {"urls": urls, "titles": titles, "sha256s": sha256s}


def _extract_exif_gps(exif) -> list[float] | None:
    try:
        gps = exif.get_ifd(34853)
        if not gps or not all(k in gps for k in (1, 2, 3, 4)):
            return None

        def deg(val, ref):
            x = float(val[0]) + float(val[1]) / 60.0 + float(val[2]) / 3600.0
            return -x if ref in ("S", "W") else x

        lat, lon = deg(gps[2], gps[1]), deg(gps[4], gps[3])
        if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
            return [round(lon, 6), round(lat, 6)]
    except Exception:
        return None
    return None


def inspect_image_file(path: Path) -> dict:
    """Validate image file with Pillow and compute dimensions, sha256, luma, and EXIF."""
    sha = file_sha256(path)
    with Image.open(path) as im:
        im.load()
        width, height = im.size
        exif = im.getexif()
        exif_dt = None
        if exif:
            raw_dt = exif.get(36867) or exif.get(306)
            if isinstance(raw_dt, str) and raw_dt.strip():
                exif_dt = raw_dt.strip()
        gps = _extract_exif_gps(exif) if exif else None

        small = ImageOps.exif_transpose(im).convert("L").resize((96, 72))
        px = list(small.tobytes())  # mode L: one byte per pixel, row by row
        mean_luma = sum(px) / max(1, len(px))
        top_px = px[: 96 * 24]
        top_luma = sum(top_px) / max(1, len(top_px))

    return {
        "width": width,
        "height": height,
        "sha256": sha,
        "mean_luma": round(mean_luma, 1),
        "top_third_luma": round(top_luma, 1),
        "exif_datetime": exif_dt,
        "gps": gps,
    }


def _count_dict(items: list[dict], field: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        k = str(item.get(field) or "unknown")
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def build_manifest_payload(
    area: str,
    photos: list[dict],
    rejected_counts: dict | None = None,
    license_policy: str | None = None,
) -> dict:
    if not license_policy:
        has_non_cc0 = any(not is_strict_cc0(p.get("license", ""), p.get("license_url", "")) for p in photos)
        license_policy = (
            "CC0 + CC BY (non-SA, attribution required)" if has_non_cc0 else "CC0 / CC-Zero only"
        )
    return {
        "area": area,
        "license_policy": license_policy,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "total_photos": len(photos),
            "by_kind": _count_dict(photos, "kind"),
            "by_spot": _count_dict(photos, "spot_slug"),
            "by_time_of_day": _count_dict(photos, "time_of_day"),
            "by_season": _count_dict(photos, "season"),
            "by_weather": _count_dict(photos, "weather"),
            "by_license": _count_dict(photos, "license"),
            "by_source": _count_dict(photos, "source"),
            "rejected": rejected_counts or {},
        },
        "photos": photos,
    }


def build_contact_sheets(
    manifest_path: Path,
    out_dir: Path,
    photos_root: Path | None = None,
    per_sheet: int = 16,
) -> list[Path]:
    """Generate 1600x1200 contact sheet JPEGs for manual visual QA."""
    manifest_path = Path(manifest_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    area = data.get("area", manifest_path.stem.replace("_manifest", ""))
    photos = data.get("photos", [])
    if photos_root is None:
        photos_root = manifest_path.parents[2] / "flyover"

    cols, rows = 4, 4
    cell_w, cell_h = 400, 300
    banner_h = 26
    sheet_paths: list[Path] = []

    for page_idx in range(0, len(photos), per_sheet):
        chunk = photos[page_idx : page_idx + per_sheet]
        canvas = Image.new("RGB", (cols * cell_w, rows * cell_h), (18, 18, 22))
        draw = ImageDraw.Draw(canvas)
        for i, item in enumerate(chunk):
            r = i // cols
            c = i % cols
            x0, y0 = c * cell_w, r * cell_h
            img_path = photo_file(item, photos_root)
            if img_path.exists():
                try:
                    with Image.open(img_path) as im:
                        im = ImageOps.exif_transpose(im).convert("RGB")
                        thumb = ImageOps.contain(im, (cell_w - 8, cell_h - banner_h - 8))
                        px = x0 + (cell_w - thumb.width) // 2
                        py = y0 + banner_h + (cell_h - banner_h - thumb.height) // 2
                        canvas.paste(thumb, (px, py))
                except Exception:
                    draw.rectangle([x0 + 4, y0 + banner_h + 4, x0 + cell_w - 4, y0 + cell_h - 4], fill=(80, 20, 20))
            draw.rectangle([x0, y0, x0 + cell_w - 1, y0 + banner_h], fill=(32, 34, 42))
            label = (
                f"{item['id']} | {item['kind'][0].upper()}:{item['spot_slug'][:14]} | "
                f"{item['time_of_day']}/{item['season']} | {item.get('width', 0)}x{item.get('height', 0)}"
            )
            draw.text((x0 + 6, y0 + 6), label[:62], fill=(240, 240, 245))
            draw.rectangle([x0, y0, x0 + cell_w - 1, y0 + cell_h - 1], outline=(55, 58, 70), width=1)

        sheet_num = page_idx // per_sheet + 1
        out_path = out_dir / f"{area}_sheet_{sheet_num:02d}.jpg"
        canvas.save(out_path, format="JPEG", quality=88)
        sheet_paths.append(out_path)

    return sheet_paths


def prune_manifest(manifest_path: Path, photos_root: Path, drop_ids: set[str]) -> dict:
    """Remove specified photo IDs from manifest and delete their image files."""
    manifest_path = Path(manifest_path)
    photos_root = Path(photos_root)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    area = data.get("area", manifest_path.stem.replace("_manifest", ""))
    kept: list[dict] = []
    removed = 0
    for item in data.get("photos", []):
        if item.get("id") in drop_ids:
            fp = photos_root / item["local_path"]
            fp.unlink(missing_ok=True)
            removed += 1
        else:
            kept.append(item)

    rejected = dict(data.get("summary", {}).get("rejected", {}))
    rejected["manual_prune"] = rejected.get("manual_prune", 0) + removed
    updated = build_manifest_payload(area, kept, rejected)
    manifest_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    return updated


def merge_area_manifests(research_dir: Path) -> dict:
    """Combine all *_manifest.json files into index.json and README.md."""
    research_dir = Path(research_dir)
    manifest_files = sorted(research_dir.glob("*_manifest.json"))
    all_photos: list[dict] = []
    by_area: dict[str, dict] = {}

    for mf in manifest_files:
        data = json.loads(mf.read_text(encoding="utf-8"))
        area = data.get("area", mf.stem.replace("_manifest", ""))
        photos = data.get("photos", [])
        all_photos.extend(photos)
        by_area[area] = {
            "manifest": mf.name,
            "total": len(photos),
            "by_kind": _count_dict(photos, "kind"),
            "by_time_of_day": _count_dict(photos, "time_of_day"),
            "by_season": _count_dict(photos, "season"),
            "by_weather": _count_dict(photos, "weather"),
            "by_license": _count_dict(photos, "license"),
            "spots": sorted({p.get("spot_slug", "") for p in photos}),
        }

    spot_buckets: dict[tuple[str, str], dict] = {}
    for p in all_photos:
        key = (p.get("area", "unknown"), p.get("spot_slug", "unknown"))
        if key not in spot_buckets:
            spot_buckets[key] = {
                "area": key[0],
                "kind": p.get("kind", "unknown"),
                "spot_slug": key[1],
                "spot_label": p.get("spot_label", key[1]),
                "morning": 0, "day": 0, "dusk": 0, "night": 0, "unknown": 0, "total": 0,
            }
        tod = str(p.get("time_of_day") or "unknown")
        if tod not in ("morning", "day", "dusk", "night"):
            tod = "unknown"
        spot_buckets[key][tod] += 1
        spot_buckets[key]["total"] += 1

    spot_time_matrix = sorted(spot_buckets.values(), key=lambda r: (-r["total"], r["area"], r["spot_slug"]))
    sfm_ready_slots: list[dict] = []
    for row in spot_time_matrix:
        for tod in ("morning", "day", "dusk", "night"):
            if row[tod] >= 10:
                sfm_ready_slots.append({
                    "area": row["area"], "kind": row["kind"],
                    "spot_slug": row["spot_slug"], "spot_label": row["spot_label"],
                    "time_of_day": tod, "count": row[tod],
                })
    sfm_ready_slots.sort(key=lambda r: (-r["count"], r["area"], r["spot_slug"], r["time_of_day"]))

    has_non_cc0 = any(not is_strict_cc0(p.get("license", ""), p.get("license_url", "")) for p in all_photos)
    license_policy = "CC0 + CC BY (non-SA, attribution required)" if has_non_cc0 else "CC0 / CC-Zero only"

    index_payload = {
        "license_policy": license_policy,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "total_areas": len(by_area),
            "total_photos": len(all_photos),
            "by_kind": _count_dict(all_photos, "kind"),
            "by_time_of_day": _count_dict(all_photos, "time_of_day"),
            "by_season": _count_dict(all_photos, "season"),
            "by_weather": _count_dict(all_photos, "weather"),
            "by_license": _count_dict(all_photos, "license"),
            "by_source": _count_dict(all_photos, "source"),
            "by_area": by_area,
            "spot_time_matrix": spot_time_matrix,
            "sfm_ready_slots": sfm_ready_slots,
        },
        "photos": all_photos,
    }
    hex32 = find_gitleaks_hex32_matches(index_payload)
    if hex32:
        raise ValueError(f"Refusing to write index.json containing 32-hex gitleaks tokens: {hex32}")

    (research_dir / "index.json").write_text(
        json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# 東京主要エリア 街並み写真カタログ",
        "",
        f"ライセンス方針: **{license_policy}**。目視検品済みのカタログです。",
        "実画像ファイルは各 `local_path`（`.gitignore` 対象）に保存しています。",
        "",
        f"- **総枚数**: {len(all_photos)} 枚（{len(by_area)} エリア）",
        f"- **SfM / 3DGS 投入可能バケット（同一スポット×同一時間帯 >= 10枚）**: {len(sfm_ready_slots)} 件",
        f"- **ライセンス内訳**: {json.dumps(index_payload['summary']['by_license'], ensure_ascii=False)}",
        f"- **種別内訳**: {json.dumps(index_payload['summary']['by_kind'], ensure_ascii=False)}",
        f"- **時間帯内訳**: {json.dumps(index_payload['summary']['by_time_of_day'], ensure_ascii=False)}",
        f"- **季節内訳**: {json.dumps(index_payload['summary']['by_season'], ensure_ascii=False)}",
        "",
        "## エリア別サマリー",
        "",
        "| エリア | 合計 | ランドマーク | 通り | 朝 | 昼 | 夕 | 夜 | 春 | 夏 | 秋 | 冬 | マニフェスト |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for area, info in by_area.items():
        bk, bt, bs = info["by_kind"], info["by_time_of_day"], info["by_season"]
        lines.append(
            f"| `{area}` | {info['total']} | {bk.get('landmarks', 0)} | {bk.get('streets', 0)} | "
            f"{bt.get('morning', 0)} | {bt.get('day', 0)} | {bt.get('dusk', 0)} | {bt.get('night', 0)} | "
            f"{bs.get('spring', 0)} | {bs.get('summer', 0)} | {bs.get('autumn', 0)} | {bs.get('winter', 0)} | "
            f"[{info['manifest']}]({info['manifest']}) |"
        )

    def _fmt_cell(val: int) -> str:
        if val >= 25:
            return f"**{val}★★**"
        if val >= 10:
            return f"**{val}★**"
        return str(val)

    lines.extend([
        "", "## フォトグラメトリ / 3DGS 密度マトリクス（スポット × 時間帯）", "",
        "同一スポット・同一時間帯の枚数目安: `★` = 10枚以上、`★★` = 25枚以上。", "",
        "| エリア | スポット | 種別 | 合計 | 朝 | 昼 | 夕 | 夜 |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ])
    for row in spot_time_matrix:
        lines.append(
            f"| `{row['area']}` | `{row['spot_slug']}` ({row['spot_label']}) | {row['kind']} | {row['total']} | "
            f"{_fmt_cell(row['morning'])} | {_fmt_cell(row['day'])} | {_fmt_cell(row['dusk'])} | {_fmt_cell(row['night'])} |"
        )

    lines.extend([
        "", "## 出典・ライセンス規約", "",
        f"- 本カタログのライセンス方針は **{license_policy}** です。",
        "- 動画公開時には [index.json](index.json) に記録した作者名 (`creator`)・ライセンス (`license`)・取得元 URL (`landing_url`) を参考にクレジットを記録してください（CC BY 写真は帰属表記必須）。",
    ])
    (research_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return index_payload
