#!/usr/bin/env python3
"""Tokyo urban photo collector CLI (strict CC0, CC0 + public domain, or CC0+CC-BY non-SA), review sheet builder, and index manager."""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
if str(_Path(__file__).resolve().parents[1]) not in _sys.path:
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import time

from photos import photo_catalog_sources as _sources
from photos import photo_store
from photos.photo_catalog_review import (
    _count_dict, _extract_exif_gps, build_contact_sheets, build_manifest_payload, file_sha256,
    inspect_image_file, load_existing_dedup_keys, merge_area_manifests, prune_manifest,
)
from photos.photo_catalog_rules import (
    DISALLOWED_LICENSE_RE, GITLEAKS_HEX32_RE, MONTH_NAMES, NOISE_KEYWORDS, _license_allowed, date_rejection,
    _score_candidate, classify_season, classify_time_of_day, classify_weather, find_gitleaks_hex32_matches,
    is_ccby_nosa_or_cc0, is_strict_cc0, is_urban_scene_candidate, parse_datetime, safe_filename,
    sanitize_hex32_for_gitleaks, select_diverse_candidates, strip_html,
)
from photos.photo_catalog_sources import (
    USER_AGENT, _retry_wait_seconds, download_bytes_with_retry, fetch_json_with_retry,
)


def query_commons_search(query: str, limit: int = 80, license_mode: str = "cc0", sleep_fn=time.sleep) -> list[str]:
    return _sources.query_commons_search(
        query, limit=limit, license_mode=license_mode, sleep_fn=sleep_fn, fetch_fn=fetch_json_with_retry
    )


def query_commons_category(category: str, limit: int = 120, sleep_fn=time.sleep, depth: int = 0) -> list[str]:
    return _sources.query_commons_category(category, limit, sleep_fn, fetch_json_with_retry, depth)


def query_commons_geosearch(
    lat: float, lon: float, radius_m: int = 300, limit: int = 80, sleep_fn=time.sleep
) -> list[str]:
    return _sources.query_commons_geosearch(
        lat, lon, radius_m=radius_m, limit=limit, sleep_fn=sleep_fn, fetch_fn=fetch_json_with_retry
    )


def fetch_commons_details(titles: list[str], license_mode: str = "cc0", sleep_fn=time.sleep) -> list[dict]:
    return _sources.fetch_commons_details(
        titles, license_mode=license_mode, sleep_fn=sleep_fn, fetch_fn=fetch_json_with_retry
    )


def query_openverse(
    query: str, pages: int = 3, skip_rawpixel: bool = True, license_mode: str = "cc0", sleep_fn=time.sleep
) -> list[dict]:
    return _sources.query_openverse(
        query, pages=pages, skip_rawpixel=skip_rawpixel, license_mode=license_mode,
        sleep_fn=sleep_fn, fetch_fn=fetch_json_with_retry,
    )


def query_openverse_cc0(query: str, pages: int = 3, skip_rawpixel: bool = True, sleep_fn=time.sleep) -> list[dict]:
    return query_openverse(query, pages=pages, skip_rawpixel=skip_rawpixel, license_mode="cc0", sleep_fn=sleep_fn)


def _relative_to_flyover(path: Path, out_photos: Path) -> str:
    for ancestor in out_photos.parents:
        if ancestor.name == "flyover":
            return str(path.relative_to(ancestor))
    try:
        return str(path.relative_to(out_photos.parents[2]))
    except Exception:
        return str(path)


def collect_from_config(
    config: dict,
    out_photos: Path,
    out_manifest: Path,
    existing_dirs: list[Path] | None = None,
    existing_manifests: list[Path] | None = None,
    append: bool = False,
    license_mode: str | None = None,
    registration_only: bool = False,
) -> dict:
    area = config["area"]
    target_total = int(config.get("target_total") or 60)
    spots = config.get("spots") or []
    max_per_creator_day = int(config.get("max_per_creator_day") or 2)
    eff_license_mode = license_mode or config.get("license_mode") or "cc0"
    if (eff_license_mode == "registration") != registration_only:     # CC BY / BY-SA only when asked for twice
        raise ValueError("--license-mode=registration and --registration-only go together (photos/photo_use.py)")

    out_photos = Path(out_photos)
    out_manifest = Path(out_manifest)
    out_manifest.parent.mkdir(parents=True, exist_ok=True)

    existing_photos: list[dict] = []
    if append and out_manifest.exists():
        old_data = json.loads(out_manifest.read_text(encoding="utf-8"))
        existing_photos = list(old_data.get("photos", []))

    manifest_list = list(existing_manifests or [])
    if append and out_manifest.exists():
        manifest_list.append(out_manifest)
    dir_list = list(existing_dirs or [])
    area_photo_dir = out_photos / area
    if append and area_photo_dir.exists():
        dir_list.append(area_photo_dir)

    dedup = load_existing_dedup_keys(dir_list, manifest_list)

    spot_candidates: dict[str, list[dict]] = {}
    rejected: dict[str, int] = defaultdict(int)

    for spot in spots:
        slug, kind, label = spot["slug"], spot["kind"], spot.get("label", spot["slug"])
        title_seen: set[str] = set()
        ordered_titles: list[str] = []

        def add_titles(ts: list[str]) -> None:
            for t in ts:
                if t not in title_seen:
                    title_seen.add(t)
                    ordered_titles.append(t)

        for cat in spot.get("commons_categories", []):
            add_titles(query_commons_category(cat, int(spot.get("cat_limit", 100)), depth=int(spot.get("category_depth", 0))))
        for q in spot.get("commons_searches", []):
            add_titles(query_commons_search(q, limit=int(spot.get("search_limit", 60)), license_mode=eff_license_mode))
        for geo in spot.get("geosearch", []):
            lat, lon = float(geo[0]), float(geo[1])
            rad = int(geo[2]) if len(geo) > 2 else 300
            geo_lim = int(geo[3]) if len(geo) > 3 else int(spot.get("geo_limit", 120))
            add_titles(query_commons_geosearch(lat, lon, radius_m=rad, limit=geo_lim))

        details = fetch_commons_details(ordered_titles, license_mode=eff_license_mode) if ordered_titles else []
        for q in spot.get("openverse_queries", []):
            if eff_license_mode == "cc0":
                details.extend(query_openverse_cc0(q, pages=int(spot.get("openverse_pages", 2))))
            else:
                details.extend(query_openverse(q, pages=int(spot.get("openverse_pages", 2)), license_mode=eff_license_mode))

        spot_cap = int(spot.get("max_per_creator_day") or max_per_creator_day)
        clean_list: list[dict] = []
        for raw in details:
            rec, warns = sanitize_hex32_for_gitleaks(raw)
            if any(w.startswith("url_hex32:") for w in warns):
                rejected["gitleaks_url_hex32"] += 1
                continue
            orig_u = rec.get("original_url") or ""
            dl_u = rec.get("download_url") or ""
            t_low = (rec.get("title") or "").strip().lower()
            if (
                orig_u in dedup["urls"]
                or orig_u.split("?")[0] in dedup["urls"]
                or dl_u in dedup["urls"]
                or (t_low and t_low in dedup["titles"])
            ):
                rejected["already_exists"] += 1
                continue

            ok, reason = is_urban_scene_candidate(rec)
            if not ok:
                rejected[reason.split(":")[0]] += 1
                continue

            blob = " ".join([rec.get("title", ""), rec.get("description", ""), rec.get("categories", ""), rec.get("datetime", "")])
            dt_info = parse_datetime(rec.get("datetime") or "")
            if not dt_info["year"]:
                dt_info = parse_datetime(rec.get("title") or "")
            too_old = date_rejection(dt_info["year"], rec.get("license", ""), rec.get("license_url", ""),
                                     spot.get("min_year", config.get("min_year")))   # the city as it stands now
            if too_old:
                rejected[too_old] += 1
                continue
            rec.update({
                "area": area, "kind": kind, "spot_slug": slug, "spot_label": label,
                "date": dt_info["date"], "hour": dt_info["hour"],
                "time_of_day": classify_time_of_day(blob, hour=dt_info["hour"]),
                "season": classify_season(blob, month=dt_info["month"]),
                "weather": classify_weather(blob),
                "max_per_creator_day": spot_cap,
            })
            rec["score"] = _score_candidate(rec)
            clean_list.append(rec)

        spot_candidates[slug] = clean_list

    existing_by_spot = _count_dict(existing_photos, "spot_slug")
    per_spot_default = max(4, (target_total + max(1, len(spots)) - 1) // max(1, len(spots)))
    selected: list[dict] = []
    for spot in spots:
        slug = spot["slug"]
        want_spot = int(spot.get("target") or per_spot_default)
        need = max(0, want_spot - existing_by_spot.get(slug, 0)) if append else want_spot
        if need <= 0:
            continue
        spot_cap = int(spot.get("max_per_creator_day") or max_per_creator_day)
        buf = 30 if (spot.get("take_all") or want_spot >= 100) else 4
        selected.extend(select_diverse_candidates(spot_candidates.get(slug, []), limit=need + buf, max_per_creator_day=spot_cap))

    remaining_total = max(0, target_total - len(existing_photos)) if append else target_total
    selected = select_diverse_candidates(selected, limit=max(remaining_total + 10, remaining_total), max_per_creator_day=max_per_creator_day)

    next_seq_by_spot: dict[str, int] = defaultdict(int)
    for item in existing_photos:
        s = item.get("spot_slug", "")
        m_seq = re.search(r"_(\d+)$", str(item.get("id", "")))
        val = int(m_seq.group(1)) if m_seq else next_seq_by_spot[s] + 1
        if val > next_seq_by_spot[s]:
            next_seq_by_spot[s] = val

    def fetch_and_save(rec: dict, seq: int) -> tuple[dict | None, str]:
        use_original = bool(rec.get("original_url")) and 0 < int(rec.get("orig_bytes") or 0) <= 8_000_000
        fetch_url = rec["original_url"] if use_original else rec["download_url"]
        try:
            data, ctype = download_bytes_with_retry(fetch_url)
        except Exception as exc:
            if use_original and rec.get("download_url") and rec["download_url"] != fetch_url:
                try:
                    fetch_url = rec["download_url"]
                    use_original = False
                    data, ctype = download_bytes_with_retry(fetch_url)
                except Exception as exc2:
                    return None, f"download_error:{exc2}"
            else:
                return None, f"download_error:{exc}"

        if len(data) < 4096:
            return None, "too_small_bytes"

        dest = out_photos / area / rec["kind"] / rec["spot_slug"] / safe_filename(seq, rec["title"], fetch_url, ctype or rec.get("mime", ""))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

        try:
            info = inspect_image_file(dest)
        except Exception:
            dest.unlink(missing_ok=True)
            return None, "corrupt_image"

        if max(info["width"], info["height"]) < 1200:
            dest.unlink(missing_ok=True)
            return None, "low_res_actual"
        if info["sha256"] in dedup["sha256s"]:
            dest.unlink(missing_ok=True)
            return None, "duplicate_sha256"

        dt_info = parse_datetime(info.get("exif_datetime") or "")
        final_date = rec.get("date") or dt_info["date"]
        final_hour = rec.get("hour") if rec.get("hour") is not None else dt_info["hour"]
        final_month = dt_info["month"]
        if not final_month and final_date and len(final_date) >= 7:
            try:
                final_month = int(final_date[5:7])
            except ValueError:
                final_month = None

        blob = " ".join([rec.get("title", ""), rec.get("description", ""), rec.get("categories", "")])
        return {
            "id": f"{area}_{rec['spot_slug']}_{seq:03d}",
            "area": area, "kind": rec["kind"], "spot_slug": rec["spot_slug"], "spot_label": rec["spot_label"],
            "source": rec["source"], "title": rec["title"], "creator": rec["creator"],
            "license": rec["license"], "license_url": rec["license_url"], "landing_url": rec["landing_url"],
            "original_url": rec["original_url"], "download_url": fetch_url,
            "local_path": _relative_to_flyover(dest, out_photos),
            "width": info["width"], "height": info["height"], "sha256": info["sha256"], "mean_luma": info["mean_luma"],
            "time_of_day": classify_time_of_day(blob, hour=final_hour, luma=(info["mean_luma"], info["top_third_luma"])),
            "season": classify_season(blob, month=final_month), "weather": rec["weather"],
            "date": final_date, "coordinates": rec.get("coordinates") or info.get("gps"),
            "exif_preserved": bool(use_original and info.get("exif_datetime")),
            **({"use": "registration"} if eff_license_mode == "registration" else {}),
        }, "ok"

    new_entries: list[dict] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = []
        for rec in selected:
            s = rec["spot_slug"]
            next_seq_by_spot[s] += 1
            futures.append(pool.submit(fetch_and_save, rec, next_seq_by_spot[s]))
            time.sleep(0.15)
        for fut in futures:
            entry, status = fut.result()
            if entry is None:
                rejected[status.split(":")[0]] += 1
                continue
            if entry["sha256"] in dedup["sha256s"]:
                for ancestor in out_photos.parents:
                    if ancestor.name == "flyover":
                        (ancestor / entry["local_path"]).unlink(missing_ok=True)
                        break
                rejected["duplicate_sha256"] += 1
                continue
            dedup["sha256s"].add(entry["sha256"])
            if entry.get("original_url"):
                dedup["urls"].add(entry["original_url"])
            new_entries.append(entry)

    if remaining_total > 0 and len(new_entries) > remaining_total:
        for extra in new_entries[remaining_total:]:
            for ancestor in out_photos.parents:
                if ancestor.name == "flyover":
                    (ancestor / extra["local_path"]).unlink(missing_ok=True)
                    break
        new_entries = new_entries[:remaining_total]

    flyover = next((a for a in out_photos.parents if a.name == "flyover"), out_photos.parents[2])
    new_entries = photo_store.adopt(new_entries, flyover, rejected)   # into the shared store, out of the project
    all_photos = sorted(existing_photos + new_entries, key=lambda r: (r["kind"], r["spot_slug"], r["id"]))
    payload = build_manifest_payload(area, all_photos, dict(rejected))
    hex32 = find_gitleaks_hex32_matches(payload)
    if hex32:
        raise ValueError(f"Refusing to write manifest containing 32-hex gitleaks tokens: {hex32}")
    out_manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tokyo urban photo collector CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_col = sub.add_parser("collect", help="Collect photos from a config JSON")
    p_col.add_argument("config", type=Path)
    p_col.add_argument("--out-photos", type=Path, required=True)
    p_col.add_argument("--out-manifest", type=Path, required=True)
    p_col.add_argument("--existing-dir", type=Path, action="append", default=[])
    p_col.add_argument("--existing-manifest", type=Path, action="append", default=[])
    p_col.add_argument("--append", action="store_true")
    p_col.add_argument("--license-mode", choices=["cc0", "cc0_pd", "ccby_nosa", "registration"], default=None)
    p_col.add_argument("--registration-only", action="store_true", help="CC BY / BY-SA to place the others, never painted")

    p_cs = sub.add_parser("contact-sheet", help="Build contact sheets for visual QA")
    p_cs.add_argument("manifest", type=Path)
    p_cs.add_argument("out_dir", type=Path)
    p_cs.add_argument("--photos-root", type=Path, default=None)
    p_cs.add_argument("--per-sheet", type=int, default=16)

    p_pr = sub.add_parser("prune", help="Drop noisy/unwanted IDs from manifest and delete files")
    p_pr.add_argument("manifest", type=Path)
    p_pr.add_argument("--photos-root", type=Path, required=True)
    p_pr.add_argument("--drop", required=True, help="Comma-separated photo IDs")

    p_mg = sub.add_parser("merge-index", help="Merge all area manifests into index.json and README.md")
    p_mg.add_argument("research_dir", type=Path)

    args = parser.parse_args(argv)
    if args.cmd == "collect":
        if (args.license_mode == "registration") != args.registration_only:
            parser.error("--license-mode=registration and --registration-only go together")
        cfg = json.loads(args.config.read_text(encoding="utf-8"))
        res = collect_from_config(
            cfg, args.out_photos, args.out_manifest,
            existing_dirs=args.existing_dir, existing_manifests=args.existing_manifest,
            append=args.append, license_mode=args.license_mode, registration_only=args.registration_only,
        )
        print(json.dumps(res["summary"], ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "contact-sheet":
        sheets = build_contact_sheets(args.manifest, args.out_dir, photos_root=args.photos_root, per_sheet=args.per_sheet)
        print(json.dumps([str(s) for s in sheets], ensure_ascii=False))
        return 0
    if args.cmd == "prune":
        drop_ids = {s.strip() for s in args.drop.split(",") if s.strip()}
        res = prune_manifest(args.manifest, args.photos_root, drop_ids)
        print(json.dumps(res["summary"], ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "merge-index":
        res = merge_area_manifests(args.research_dir)
        print(json.dumps(res["summary"], ensure_ascii=False, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
