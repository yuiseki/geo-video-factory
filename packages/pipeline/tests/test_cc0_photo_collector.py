import io
import json
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from support import import_pipeline


class _FakeHTTPResponse:
    def __init__(self, payload: bytes, headers: dict | None = None):
        self._payload = payload
        self.headers = headers or {"Content-Type": "application/json"}

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class CC0PhotoCollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = import_pipeline("photos.cc0_photo_collector")

    def test_is_strict_cc0_accepts_only_cc0(self):
        m = self.mod
        self.assertTrue(m.is_strict_cc0("CC0"))
        self.assertTrue(m.is_strict_cc0("CC0 1.0"))
        self.assertTrue(m.is_strict_cc0("CC-Zero"))
        self.assertTrue(m.is_strict_cc0("cc0 1.0 universal"))
        self.assertTrue(
            m.is_strict_cc0(
                "No restrictions",
                "https://creativecommons.org/publicdomain/zero/1.0/deed.en",
            )
        )

        for bad in (
            "CC BY 4.0",
            "CC-BY-2.0",
            "CC BY-SA 3.0",
            "Public domain",
            "PD-old-100",
            "PDM",
            "CC0-NC",
            "CC BY-NC-ND 4.0",
            "",
            None,
        ):
            self.assertFalse(m.is_strict_cc0(bad or ""), f"Expected False for {bad!r}")

    def test_is_urban_scene_candidate_filters_noise_and_bad_sizes(self):
        m = self.mod
        ok, reason = m.is_urban_scene_candidate(
            {
                "title": "File:Shibuya Scramble Crossing dusk 2023.jpg",
                "description": "View of Shibuya crossing and QFRONT building",
                "categories": "Category:Shibuya Crossing",
                "orig_width": 4000,
                "orig_height": 3000,
            }
        )
        self.assertTrue(ok, reason)

        noisy_cases = [
            {"title": "File:Ramen bowl in Shinjuku.jpg", "orig_width": 3000, "orig_height": 2000},
            {"title": "File:Shibuya 109 cosplay event.jpg", "orig_width": 3000, "orig_height": 2000},
            {"title": "File:Ukiyo-e print of Asakusa.jpg", "orig_width": 3000, "orig_height": 2000},
            {"title": "File:Map of Akihabara station.png", "orig_width": 3000, "orig_height": 2000},
            {"title": "File:JR ticket gate machine.jpg", "orig_width": 3000, "orig_height": 2000},
            {"title": "File:Shibuya street.jpg", "description": "ラーメン店のメニュー", "orig_width": 3000, "orig_height": 2000},
            {"title": "File:Small Shibuya.jpg", "orig_width": 800, "orig_height": 600},
            {"title": "File:Ultra thin banner.jpg", "orig_width": 5000, "orig_height": 500},
        ]
        for case in noisy_cases:
            ok, reason = m.is_urban_scene_candidate(case)
            self.assertFalse(ok, f"Should reject {case}")
            self.assertTrue(reason)

    def test_datetime_season_time_and_weather_classification(self):
        m = self.mod
        p1 = m.parse_datetime("2023:11:14 21:30:05")
        self.assertEqual((p1["year"], p1["month"], p1["hour"]), (2023, 11, 21))

        p2 = m.parse_datetime("Taken on 14 November 2023")
        self.assertEqual((p2["year"], p2["month"], p2["hour"]), (2023, 11, None))

        p3 = m.parse_datetime("5 March 2022 (according to Exif data)")
        self.assertEqual((p3["year"], p3["month"]), (2022, 3))

        p4 = m.parse_datetime("File:Sotokanda_20231114.png")
        self.assertEqual((p4["year"], p4["month"], p4["date"]), (2023, 11, "2023-11-14"))

        p5 = m.parse_datetime("August 2007 in Shinjuku 2.jpg")
        self.assertEqual((p5["year"], p5["month"]), (2007, 8))

        self.assertEqual(m.classify_season("Cherry blossom sakura in Ueno", 11), "spring")
        self.assertEqual(m.classify_season("Autumn leaves 紅葉 in Omotesando", None), "autumn")
        self.assertEqual(m.classify_season("Winter snow イルミネーション", None), "winter")
        self.assertEqual(m.classify_season("Street view", 4), "spring")
        self.assertEqual(m.classify_season("Street view", 7), "summer")
        self.assertEqual(m.classify_season("Street view", 10), "autumn")
        self.assertEqual(m.classify_season("Street view", 1), "winter")
        self.assertEqual(m.classify_season("Street view", None), "unknown")

        self.assertEqual(m.classify_time_of_day("Shinjuku at night neon", 14, (30.0, 20.0)), "night")
        self.assertEqual(m.classify_time_of_day("Morning walk in Ginza", None, (150.0, 170.0)), "morning")
        self.assertEqual(m.classify_time_of_day("Dusk twilight crossing", None, None), "dusk")
        self.assertEqual(m.classify_time_of_day("Street view", 22, (40.0, 25.0)), "night")
        self.assertEqual(m.classify_time_of_day("Street view", 13, (145.0, 170.0)), "day")
        self.assertEqual(m.classify_time_of_day("Street view", None, (22.0, 15.0)), "night")
        self.assertEqual(m.classify_time_of_day("Street view", None, (155.0, 180.0)), "day")

        self.assertEqual(m.classify_weather("Rainy night wet asphalt 雨"), "rain")
        self.assertEqual(m.classify_weather("Snowy Shibuya 雪"), "snow")
        self.assertEqual(m.classify_weather("Misty morning fog"), "fog")
        self.assertEqual(m.classify_weather("Clear sunny afternoon"), "normal")

    def test_select_diverse_candidates_caps_creator_day_and_balances_buckets(self):
        m = self.mod
        cands = []
        # 6 burst shots by same creator/date in same spot
        for i in range(6):
            cands.append(
                {
                    "title": f"File:Burst_{i}.jpg",
                    "creator": "Alice",
                    "date": "2024-05-01",
                    "spot_slug": "scramble",
                    "time_of_day": "night",
                    "season": "spring",
                    "score": 100 - i,
                }
            )
        # Diverse shots in other spots/times/seasons
        cands.extend(
            [
                {
                    "title": "File:Morning_Dogenzaka.jpg",
                    "creator": "Bob",
                    "date": "2024-04-02",
                    "spot_slug": "dogenzaka",
                    "time_of_day": "morning",
                    "season": "spring",
                    "score": 50,
                },
                {
                    "title": "File:Autumn_Koen.jpg",
                    "creator": "Carol",
                    "date": "2024-11-10",
                    "spot_slug": "koen_dori",
                    "time_of_day": "dusk",
                    "season": "autumn",
                    "score": 40,
                },
                {
                    "title": "File:Winter_Centergai.jpg",
                    "creator": "Dave",
                    "date": "2024-01-15",
                    "spot_slug": "center_gai",
                    "time_of_day": "day",
                    "season": "winter",
                    "score": 30,
                },
            ]
        )
        picked = m.select_diverse_candidates(cands, limit=5, max_per_creator_day=2)
        alice_count = sum(1 for r in picked if r["creator"] == "Alice")
        self.assertEqual(alice_count, 2)
        self.assertEqual(len(picked), 5)
        picked_titles = {r["title"] for r in picked}
        self.assertIn("File:Morning_Dogenzaka.jpg", picked_titles)
        self.assertIn("File:Autumn_Koen.jpg", picked_titles)
        self.assertIn("File:Winter_Centergai.jpg", picked_titles)

    def test_safe_filename_preserves_extension_and_length(self):
        m = self.mod
        long_title = "File:" + ("very_long_shibuya_photo_name_" * 5) + ".jpeg"
        name = m.safe_filename(7, long_title, "https://example.org/img/test.jpg?width=1600")
        self.assertTrue(name.startswith("007_"))
        self.assertTrue(name.endswith(".jpg"))
        self.assertLessEqual(len(name), 90)

        png_name = m.safe_filename(12, "File:Test_No_Ext", "https://example.org/raw?id=1", mime="image/png")
        self.assertTrue(png_name.endswith(".png"))

        webp_name = m.safe_filename(3, "File:Test.webp", "https://example.org/a.webp")
        self.assertTrue(webp_name.endswith(".webp"))

    def test_load_existing_dedup_keys_and_gitleaks_hex32_check(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            img_dir = root / "existing"
            img_dir.mkdir()
            img_file = img_dir / "sample.png"
            Image.new("RGB", (64, 64), (100, 120, 140)).save(img_file)

            manifest_file = root / "manifest.json"
            manifest_file.write_text(
                json.dumps(
                    {
                        "photos": [
                            {
                                "title": "File:Existing_01.jpg",
                                "original_url": "https://example.org/existing01.jpg",
                                "download_url": "https://example.org/thumb01.jpg",
                                "sha256": "a" * 64,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            keys = m.load_existing_dedup_keys([img_dir], [manifest_file])
            self.assertIn("https://example.org/existing01.jpg", keys["urls"])
            self.assertIn("file:existing_01.jpg", keys["titles"])
            self.assertIn("a" * 64, keys["sha256s"])
            self.assertEqual(len(keys["sha256s"]), 2)

        bad_32 = "0123456789abcdef" * 2
        good_64 = "0123456789abcdef" * 4
        uuid_str = "01234567-89ab-cdef-0123-456789abcdef"
        matches = m.find_gitleaks_hex32_matches(
            {"url": f"https://example.com/{bad_32}/img.jpg", "sha256": good_64, "uuid": uuid_str}
        )
        self.assertEqual(matches, [bad_32])
        clean_matches = m.find_gitleaks_hex32_matches({"sha256": good_64, "uuid": uuid_str})
        self.assertEqual(clean_matches, [])

    def test_api_query_formatting_and_openverse_skip_rawpixel(self):
        m = self.mod
        seen_urls = []

        def fake_fetch(url: str, **kwargs):
            seen_urls.append(url)
            if "commons.wikimedia.org" in url:
                return {
                    "query": {
                        "search": [{"title": "File:Shinjuku_test.jpg"}],
                    }
                }
            return {
                "results": [
                    {
                        "id": "1",
                        "source": "rawpixel",
                        "license": "cc0",
                        "url": "https://rawpixel.com/1.jpg",
                        "width": 2000,
                        "height": 1500,
                    },
                    {
                        "id": "2",
                        "source": "flickr",
                        "license": "cc0",
                        "title": "Shinjuku street dusk",
                        "creator": "Tester",
                        "url": "https://live.staticflickr.com/2.jpg",
                        "foreign_landing_url": "https://flickr.com/photos/2",
                        "width": 2400,
                        "height": 1600,
                    },
                    {
                        "id": "3",
                        "source": "flickr",
                        "license": "by",
                        "url": "https://live.staticflickr.com/3.jpg",
                        "width": 2400,
                        "height": 1600,
                    },
                ]
            }

        with patch.object(m, "fetch_json_with_retry", side_effect=fake_fetch):
            titles = m.query_commons_search("Shinjuku Station", limit=10)
            self.assertEqual(titles, ["File:Shinjuku_test.jpg"])
            self.assertIn('srsearch=Shinjuku+Station+incategory%3A%22CC-Zero%22+filetype%3Abitmap', seen_urls[0])
            self.assertNotIn("(", seen_urls[0])

            ov = m.query_openverse_cc0("Shinjuku", pages=1, skip_rawpixel=True)
            self.assertIn("license=cc0", seen_urls[1])
            self.assertIn("category=photograph", seen_urls[1])
            self.assertEqual(len(ov), 1)
            self.assertEqual(ov[0]["source"], "openverse/flickr")

    def test_contact_sheet_prune_and_merge_index_roundtrip(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            flyover_dir = root / "flyover"
            photos_dir = flyover_dir / "assets" / "photos" / "tokyo_cc0"
            research_dir = root / "research" / "tokyo_cc0"
            review_dir = root / "review"
            research_dir.mkdir(parents=True)

            photo_entries = []
            for idx, (kind, spot, tod, season, color) in enumerate(
                [
                    ("landmarks", "kaminarimon", "day", "spring", (180, 190, 210)),
                    ("streets", "nakamise_dori", "night", "winter", (25, 25, 45)),
                ],
                start=1,
            ):
                rel = f"assets/photos/tokyo_cc0/asakusa/{kind}/{spot}/{idx:03d}_test.jpg"
                p = flyover_dir / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                img = Image.new("RGB", (320, 240), color)
                draw = ImageDraw.Draw(img)
                draw.rectangle([40, 40, 280, 200], outline=(255, 255, 255), width=2)
                img.save(p, format="JPEG")
                info = m.inspect_image_file(p)
                photo_entries.append(
                    {
                        "id": f"asakusa_{idx:04d}",
                        "area": "asakusa",
                        "kind": kind,
                        "spot_slug": spot,
                        "spot_label": spot,
                        "source": "wikimedia_commons",
                        "title": f"File:Asakusa_{idx}.jpg",
                        "creator": f"Author{idx}",
                        "license": "CC0 1.0",
                        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                        "landing_url": f"https://commons.wikimedia.org/wiki/File:Asakusa_{idx}.jpg",
                        "original_url": f"https://upload.wikimedia.org/a_{idx}.jpg",
                        "download_url": f"https://upload.wikimedia.org/a_{idx}.jpg",
                        "local_path": rel,
                        "width": info["width"],
                        "height": info["height"],
                        "sha256": info["sha256"],
                        "time_of_day": tod,
                        "season": season,
                        "weather": "normal",
                        "date": "2024-04-01" if idx == 1 else "2024-12-20",
                        "coordinates": [139.7964, 35.7111],
                        "exif_preserved": True,
                    }
                )

            manifest_path = research_dir / "asakusa_manifest.json"
            manifest_path.write_text(
                json.dumps(m.build_manifest_payload("asakusa", photo_entries), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            sheets = m.build_contact_sheets(manifest_path, review_dir, photos_root=flyover_dir, per_sheet=16)
            self.assertEqual(len(sheets), 1)
            self.assertTrue(sheets[0].exists())

            # Prune item 1
            updated = m.prune_manifest(manifest_path, flyover_dir, {"asakusa_0001"})
            self.assertEqual(updated["summary"]["total_photos"], 1)
            self.assertFalse((flyover_dir / photo_entries[0]["local_path"]).exists())
            self.assertTrue((flyover_dir / photo_entries[1]["local_path"]).exists())

            # Merge index
            merged = m.merge_area_manifests(research_dir)
            self.assertEqual(merged["summary"]["total_photos"], 1)
            self.assertIn("asakusa", merged["summary"]["by_area"])
            self.assertTrue((research_dir / "index.json").exists())
            self.assertTrue((research_dir / "README.md").exists())
            readme = (research_dir / "README.md").read_text(encoding="utf-8")
            self.assertIn("asakusa", readme)
            self.assertIn("CC0", readme)

    def test_fetch_retry_and_collect_append_pipeline(self):
        m = self.mod
        attempts = {"n": 0}

        def flaky_urlopen(req, timeout=25):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise TimeoutError("transient timeout")
            return _FakeHTTPResponse(json.dumps({"ok": True}).encode("utf-8"))

        res = m.fetch_json_with_retry("https://example.org/api", max_retries=2, sleep_fn=lambda _: None, opener=flaky_urlopen)
        self.assertEqual(res, {"ok": True})
        self.assertEqual(attempts["n"], 2)

        # End-to-end mocked collect + append
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            flyover_dir = root / "flyover"
            out_photos = flyover_dir / "assets" / "photos" / "tokyo_cc0"
            out_manifest = root / "research" / "tokyo_cc0" / "ginza_manifest.json"

            buf = io.BytesIO()
            Image.new("RGB", (1400, 1000), (140, 150, 160)).save(buf, format="JPEG")
            jpg_bytes = buf.getvalue()

            cfg = {
                "area": "ginza",
                "target_total": 10,
                "spots": [
                    {
                        "kind": "landmarks",
                        "slug": "ginza_wako",
                        "label": "銀座和光",
                        "commons_searches": ["Ginza Wako"],
                        "commons_categories": [],
                        "geosearch": [[35.6712, 139.7650, 200]],
                        "openverse_queries": ["Ginza Tokyo"],
                    }
                ],
            }

            fake_details = [
                {
                    "source": "wikimedia_commons",
                    "title": "File:Ginza_Wako_day.jpg",
                    "creator": "Alice",
                    "license": "CC0",
                    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                    "description": "Ginza Wako building daytime",
                    "categories": "Category:Ginza",
                    "datetime": "2024-05-10 12:00:00",
                    "download_url": "https://upload.wikimedia.org/wako_thumb.jpg",
                    "original_url": "https://upload.wikimedia.org/wako_orig.jpg",
                    "landing_url": "https://commons.wikimedia.org/wiki/File:Ginza_Wako_day.jpg",
                    "orig_width": 1400,
                    "orig_height": 1000,
                    "orig_bytes": len(jpg_bytes),
                    "coordinates": [139.7650, 35.6712],
                }
            ]

            with (
                patch.object(m, "query_commons_search", return_value=["File:Ginza_Wako_day.jpg"]),
                patch.object(m, "query_commons_geosearch", return_value=[]),
                patch.object(m, "fetch_commons_details", return_value=fake_details),
                patch.object(m, "query_openverse_cc0", return_value=[]),
                patch.object(m, "download_bytes_with_retry", return_value=(jpg_bytes, "image/jpeg")),
            ):
                payload = m.collect_from_config(cfg, out_photos, out_manifest)
                self.assertEqual(payload["summary"]["total_photos"], 1)
                self.assertEqual(payload["photos"][0]["spot_slug"], "ginza_wako")
                self.assertTrue((flyover_dir / payload["photos"][0]["local_path"]).exists())

            # Append with a second distinct image
            buf2 = io.BytesIO()
            Image.new("RGB", (1400, 1000), (15, 18, 30)).save(buf2, format="JPEG")
            jpg_bytes2 = buf2.getvalue()
            fake_details2 = [
                {
                    "source": "wikimedia_commons",
                    "title": "File:Ginza_Chuo_night.jpg",
                    "creator": "Bob",
                    "license": "CC0 1.0",
                    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                    "description": "Ginza Chuo-dori at night",
                    "categories": "Category:Ginza at night",
                    "datetime": "2024-12-20 21:00:00",
                    "download_url": "https://upload.wikimedia.org/chuo_thumb.jpg",
                    "original_url": "https://upload.wikimedia.org/chuo_orig.jpg",
                    "landing_url": "https://commons.wikimedia.org/wiki/File:Ginza_Chuo_night.jpg",
                    "orig_width": 1400,
                    "orig_height": 1000,
                    "orig_bytes": len(jpg_bytes2),
                    "coordinates": [139.7655, 35.6715],
                }
            ]
            cfg["spots"].append(
                {
                    "kind": "streets",
                    "slug": "ginza_chuo_dori",
                    "label": "銀座中央通り",
                    "commons_searches": ["Ginza Chuo-dori"],
                }
            )
            with (
                patch.object(m, "query_commons_search", return_value=["File:Ginza_Wako_day.jpg", "File:Ginza_Chuo_night.jpg"]),
                patch.object(m, "query_commons_geosearch", return_value=[]),
                patch.object(m, "fetch_commons_details", return_value=fake_details + fake_details2),
                patch.object(m, "query_openverse_cc0", return_value=[]),
                patch.object(m, "download_bytes_with_retry", return_value=(jpg_bytes2, "image/jpeg")),
            ):
                payload2 = m.collect_from_config(cfg, out_photos, out_manifest, append=True)
                self.assertEqual(payload2["summary"]["total_photos"], 2)
                self.assertEqual(payload2["summary"]["by_kind"]["landmarks"], 1)
                self.assertEqual(payload2["summary"]["by_kind"]["streets"], 1)

    def test_append_after_prune_avoids_id_collision_and_spot_cap_and_geo_limit(self):
        m = self.mod
        # (b) Per-candidate max_per_creator_day override beats global cap=2
        cands = [
            {
                "title": f"File:Kaminarimon_{i}.jpg",
                "creator": "SameUser",
                "date": "2024-05-01",
                "spot_slug": "kaminarimon",
                "time_of_day": "day",
                "season": "spring",
                "score": 50 - i,
                "max_per_creator_day": 999,
            }
            for i in range(5)
        ] + [
            {
                "title": f"File:Other_{i}.jpg",
                "creator": "SameUser",
                "date": "2024-05-01",
                "spot_slug": "nakamise",
                "time_of_day": "day",
                "season": "spring",
                "score": 50 - i,
            }
            for i in range(5)
        ]
        picked = m.select_diverse_candidates(cands, limit=10, max_per_creator_day=2)
        k_cnt = sum(1 for r in picked if r["spot_slug"] == "kaminarimon")
        n_cnt = sum(1 for r in picked if r["spot_slug"] == "nakamise")
        self.assertEqual(k_cnt, 5)
        self.assertEqual(n_cnt, 2)

        # (a) & (c) Prune _001 leaving _002, then append -> next ID must be _003; geosearch 4th arg / geo_limit forwarded
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            flyover_dir = root / "flyover"
            out_photos = flyover_dir / "assets" / "photos" / "tokyo_cc0"
            out_manifest = root / "research" / "tokyo_cc0" / "asakusa_manifest.json"
            out_manifest.parent.mkdir(parents=True, exist_ok=True)

            # Seed manifest with _002 only (as if _001 was pruned)
            seed_rel = "assets/photos/tokyo_cc0/asakusa/landmarks/kaminarimon/002_seed.jpg"
            seed_path = flyover_dir / seed_rel
            seed_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (1400, 1000), (80, 90, 100)).save(seed_path, format="JPEG")
            seed_info = m.inspect_image_file(seed_path)
            seed_entry = {
                "id": "asakusa_kaminarimon_002",
                "area": "asakusa",
                "kind": "landmarks",
                "spot_slug": "kaminarimon",
                "spot_label": "雷門",
                "source": "wikimedia_commons",
                "title": "File:Seed_002.jpg",
                "creator": "SeedUser",
                "license": "CC0",
                "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                "landing_url": "https://commons.wikimedia.org/wiki/File:Seed_002.jpg",
                "original_url": "https://upload.wikimedia.org/seed_002.jpg",
                "download_url": "https://upload.wikimedia.org/seed_002.jpg",
                "local_path": seed_rel,
                "width": 1400,
                "height": 1000,
                "sha256": seed_info["sha256"],
                "time_of_day": "day",
                "season": "spring",
                "weather": "normal",
                "date": "2024-05-01",
                "coordinates": [139.7964, 35.7111],
                "exif_preserved": False,
            }
            out_manifest.write_text(
                json.dumps(m.build_manifest_payload("asakusa", [seed_entry]), ensure_ascii=False),
                encoding="utf-8",
            )

            buf3 = io.BytesIO()
            Image.new("RGB", (1400, 1000), (200, 180, 160)).save(buf3, format="JPEG")
            jpg3 = buf3.getvalue()

            cfg = {
                "area": "asakusa",
                "target_total": 10,
                "spots": [
                    {
                        "kind": "landmarks",
                        "slug": "kaminarimon",
                        "label": "雷門",
                        "target": 10,
                        "max_per_creator_day": 999,
                        "geosearch": [[35.7111, 139.7964, 150, 450]],
                    }
                ],
            }
            geo_calls = []

            def fake_geo(lat, lon, radius_m=300, limit=80, **kwargs):
                geo_calls.append((lat, lon, radius_m, limit))
                return ["File:New_003.jpg"]

            fake_detail = [
                {
                    "source": "wikimedia_commons",
                    "title": "File:New_003.jpg",
                    "creator": "SeedUser",
                    "license": "CC0",
                    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                    "description": "Kaminarimon gate",
                    "categories": "Category:Kaminarimon",
                    "datetime": "2024-05-01 12:00:00",
                    "download_url": "https://upload.wikimedia.org/new_003_t.jpg",
                    "original_url": "https://upload.wikimedia.org/new_003.jpg",
                    "landing_url": "https://commons.wikimedia.org/wiki/File:New_003.jpg",
                    "orig_width": 1400,
                    "orig_height": 1000,
                    "orig_bytes": len(jpg3),
                    "coordinates": [139.7964, 35.7111],
                }
            ]
            with (
                patch.object(m, "query_commons_geosearch", side_effect=fake_geo),
                patch.object(m, "fetch_commons_details", return_value=fake_detail),
                patch.object(m, "download_bytes_with_retry", return_value=(jpg3, "image/jpeg")),
            ):
                res = m.collect_from_config(cfg, out_photos, out_manifest, append=True)

            self.assertEqual(geo_calls, [(35.7111, 139.7964, 150, 450)])
            ids = [p["id"] for p in res["photos"]]
            self.assertEqual(ids, ["asakusa_kaminarimon_002", "asakusa_kaminarimon_003"])

    def test_commons_category_geosearch_details_and_cli(self):
        m = self.mod

        def fake_fetch(url: str, **kwargs):
            if "list=categorymembers" in url:
                return {"query": {"categorymembers": [{"title": "File:Cat1.jpg"}]}}
            if "list=geosearch" in url:
                return {"query": {"geosearch": [{"title": "File:Geo1.jpg"}]}}
            if "prop=imageinfo" in url:
                return {
                    "query": {
                        "pages": {
                            "1": {
                                "title": "File:Cat1.jpg",
                                "coordinates": [{"lat": 35.6595, "lon": 139.7005}],
                                "categories": [{"title": "Category:Shibuya at night"}],
                                "imageinfo": [
                                    {
                                        "mime": "image/jpeg",
                                        "width": 2400,
                                        "height": 1600,
                                        "size": 500000,
                                        "url": "https://upload.wikimedia.org/cat1.jpg",
                                        "thumburl": "https://upload.wikimedia.org/cat1_thumb.jpg",
                                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Cat1.jpg",
                                        "extmetadata": {
                                            "LicenseShortName": {"value": "CC0"},
                                            "LicenseUrl": {"value": "https://creativecommons.org/publicdomain/zero/1.0/"},
                                            "Artist": {"value": "Tester"},
                                            "ImageDescription": {"value": "Night view"},
                                            "DateTimeOriginal": {"value": "2024-01-10 21:00:00"},
                                        },
                                    }
                                ],
                            },
                            "2": {
                                "title": "File:NonCC0.jpg",
                                "imageinfo": [
                                    {
                                        "mime": "image/jpeg",
                                        "width": 2400,
                                        "height": 1600,
                                        "size": 500000,
                                        "url": "https://upload.wikimedia.org/noncc0.jpg",
                                        "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}},
                                    }
                                ],
                            },
                        }
                    }
                }
            return {}

        with patch.object(m, "fetch_json_with_retry", side_effect=fake_fetch):
            cats = m.query_commons_category("Shibuya", limit=5, sleep_fn=lambda _: None)
            self.assertEqual(cats, ["File:Cat1.jpg"])
            geos = m.query_commons_geosearch(35.6595, 139.7005, sleep_fn=lambda _: None)
            self.assertEqual(geos, ["File:Geo1.jpg"])
            details = m.fetch_commons_details(["File:Cat1.jpg", "File:NonCC0.jpg"], sleep_fn=lambda _: None)
            self.assertEqual(len(details), 1)
            self.assertEqual(details[0]["title"], "File:Cat1.jpg")
            self.assertEqual(details[0]["coordinates"], [139.7005, 35.6595])

        # Sanitization check
        dummy_hex32 = "0123456789abcdef" * 2
        rec, warns = m.sanitize_hex32_for_gitleaks(
            {"title": f"File:Test_{dummy_hex32}.jpg", "original_url": "https://example.com/ok.jpg"}
        )
        self.assertIn("[redacted-id]", rec["title"])
        self.assertEqual(warns, ["redacted_text:title"])

        # CLI main() subcommands
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            flyover_dir = root / "flyover"
            out_photos = flyover_dir / "assets" / "photos" / "tokyo_cc0"
            research_dir = root / "research" / "tokyo_cc0"
            manifest_path = research_dir / "ueno_manifest.json"
            review_dir = root / "review"
            cfg_path = root / "cfg.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "area": "ueno",
                        "target_total": 4,
                        "spots": [{"kind": "landmarks", "slug": "ueno_park", "label": "上野公園", "commons_searches": ["Ueno Park"]}],
                    }
                ),
                encoding="utf-8",
            )
            buf = io.BytesIO()
            img = Image.new("RGB", (1400, 1000), (120, 140, 120))
            exif = img.getexif()
            exif[36867] = "2024:04:05 10:15:00"
            img.save(buf, format="JPEG", exif=exif.tobytes())
            jpg_bytes = buf.getvalue()

            with (
                patch.object(m, "query_commons_search", return_value=["File:Ueno_sakura.jpg"]),
                patch.object(m, "fetch_commons_details", return_value=[
                    {
                        "source": "wikimedia_commons",
                        "title": "File:Ueno_sakura.jpg",
                        "creator": "SakuraUser",
                        "license": "CC0",
                        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                        "description": "Ueno park cherry blossom",
                        "categories": "Category:Ueno Park",
                        "datetime": "",
                        "download_url": "https://upload.wikimedia.org/ueno_t.jpg",
                        "original_url": "https://upload.wikimedia.org/ueno.jpg",
                        "landing_url": "https://commons.wikimedia.org/wiki/File:Ueno_sakura.jpg",
                        "orig_width": 1400,
                        "orig_height": 1000,
                        "orig_bytes": len(jpg_bytes),
                        "coordinates": None,
                    }
                ]),
                patch.object(m, "download_bytes_with_retry", return_value=(jpg_bytes, "image/jpeg")),
            ):
                self.assertEqual(
                    m.main(["collect", str(cfg_path), "--out-photos", str(out_photos), "--out-manifest", str(manifest_path)]),
                    0,
                )
            self.assertEqual(
                m.main(["contact-sheet", str(manifest_path), str(review_dir), "--photos-root", str(flyover_dir)]),
                0,
            )
            self.assertEqual(m.main(["merge-index", str(research_dir)]), 0)
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            pid = loaded["photos"][0]["id"]
            self.assertEqual(loaded["photos"][0]["season"], "spring")
            self.assertEqual(
                m.main(["prune", str(manifest_path), "--photos-root", str(flyover_dir), "--drop", pid]),
                0,
            )
            after = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(after["summary"]["total_photos"], 0)

    def test_retry_respects_429_retry_after_and_merge_outputs_spot_time_matrix(self):
        m = self.mod
        sleeps: list[float] = []
        calls = {"n": 0}

        def opener_429(req, timeout=25):
            calls["n"] += 1
            if calls["n"] == 1:
                hdrs = Message()
                hdrs["Retry-After"] = "7"
                raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", hdrs, None)
            return _FakeHTTPResponse(json.dumps({"ok": True}).encode("utf-8"))

        out = m.fetch_json_with_retry(
            "https://example.org/429", max_retries=2, sleep_fn=sleeps.append, opener=opener_429
        )
        self.assertEqual(out, {"ok": True})
        self.assertEqual(sleeps, [7.0])

        with tempfile.TemporaryDirectory() as td:
            research_dir = Path(td)
            shibuya_photos = [
                {
                    "id": f"shibuya_scramble_{i:03d}",
                    "area": "shibuya",
                    "kind": "landmarks",
                    "spot_slug": "scramble_hachiko",
                    "spot_label": "渋谷スクランブル交差点",
                    "source": "wikimedia_commons",
                    "creator": "A",
                    "license": "CC0",
                    "time_of_day": "day" if i <= 25 else "night",
                    "season": "spring",
                    "weather": "normal",
                }
                for i in range(1, 36)
            ]
            asakusa_photos = [
                {
                    "id": f"asakusa_kami_{i:03d}",
                    "area": "asakusa",
                    "kind": "landmarks",
                    "spot_slug": "kaminarimon",
                    "spot_label": "雷門",
                    "source": "wikimedia_commons",
                    "creator": "B",
                    "license": "CC0",
                    "time_of_day": "day",
                    "season": "autumn",
                    "weather": "normal",
                }
                for i in range(1, 5)
            ]
            (research_dir / "shibuya_manifest.json").write_text(
                json.dumps(m.build_manifest_payload("shibuya", shibuya_photos), ensure_ascii=False),
                encoding="utf-8",
            )
            (research_dir / "asakusa_manifest.json").write_text(
                json.dumps(m.build_manifest_payload("asakusa", asakusa_photos), ensure_ascii=False),
                encoding="utf-8",
            )
            merged = m.merge_area_manifests(research_dir)
            summary = merged["summary"]
            self.assertIn("spot_time_matrix", summary)
            self.assertIn("sfm_ready_slots", summary)
            ready = {(s["area"], s["spot_slug"], s["time_of_day"]): s["count"] for s in summary["sfm_ready_slots"]}
            self.assertEqual(ready.get(("shibuya", "scramble_hachiko", "day")), 25)
            self.assertEqual(ready.get(("shibuya", "scramble_hachiko", "night")), 10)
            self.assertNotIn(("asakusa", "kaminarimon", "day"), ready)

            readme = (research_dir / "README.md").read_text(encoding="utf-8")
            self.assertIn("★★", readme)
            self.assertIn("★", readme)
            self.assertIn("scramble_hachiko", readme)

    def test_ccby_nosa_license_filter_and_search_mode(self):
        m = self.mod
        for good in (
            ("CC0", ""),
            ("CC BY 2.0", ""),
            ("CC BY 4.0", ""),
            ("CC-BY-3.0", ""),
            ("CC BY 2.1 jp", ""),
            ("Attribution", "https://creativecommons.org/licenses/by/2.0/"),
        ):
            self.assertTrue(m.is_ccby_nosa_or_cc0(*good), f"Expected True for {good}")

        for bad in (
            ("CC BY-SA 3.0", ""),
            ("CC BY-NC 4.0", ""),
            ("CC BY-ND 2.0", ""),
            ("PD-old", ""),
            ("Fair use", ""),
            ("", ""),
        ):
            self.assertFalse(m.is_ccby_nosa_or_cc0(*bad), f"Expected False for {bad}")

        seen_urls = []

        def fake_fetch(url: str, **kwargs):
            seen_urls.append(url)
            if "list=search" in url:
                return {"query": {"search": [{"title": "File:Yodobashi.jpg"}]}}
            if "prop=imageinfo" in url:
                return {
                    "query": {
                        "pages": {
                            "1": {
                                "title": "File:Yodobashi_by.jpg",
                                "imageinfo": [
                                    {
                                        "mime": "image/jpeg",
                                        "width": 2000,
                                        "height": 1500,
                                        "size": 400000,
                                        "url": "https://upload.wikimedia.org/y_by.jpg",
                                        "extmetadata": {"LicenseShortName": {"value": "CC BY 2.0"}},
                                    }
                                ],
                            },
                            "2": {
                                "title": "File:Yodobashi_bysa.jpg",
                                "imageinfo": [
                                    {
                                        "mime": "image/jpeg",
                                        "width": 2000,
                                        "height": 1500,
                                        "size": 400000,
                                        "url": "https://upload.wikimedia.org/y_bysa.jpg",
                                        "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}},
                                    }
                                ],
                            },
                        }
                    }
                }
            return {
                "results": [
                    {
                        "id": "10",
                        "source": "flickr",
                        "license": "by",
                        "license_version": "2.0",
                        "url": "https://live.staticflickr.com/10.jpg",
                        "width": 2000,
                        "height": 1500,
                    },
                    {
                        "id": "11",
                        "source": "flickr",
                        "license": "by-sa",
                        "license_version": "4.0",
                        "url": "https://live.staticflickr.com/11.jpg",
                        "width": 2000,
                        "height": 1500,
                    },
                ]
            }

        with patch.object(m, "fetch_json_with_retry", side_effect=fake_fetch):
            titles = m.query_commons_search("Yodobashi-Akiba", limit=10, license_mode="ccby_nosa")
            self.assertEqual(titles, ["File:Yodobashi.jpg"])
            self.assertNotIn("CC-Zero", seen_urls[0])
            det = m.fetch_commons_details(["File:Yodobashi_by.jpg", "File:Yodobashi_bysa.jpg"], license_mode="ccby_nosa")
            self.assertEqual([d["title"] for d in det], ["File:Yodobashi_by.jpg"])
            ov = m.query_openverse("Yodobashi Akiba", pages=1, license_mode="ccby_nosa")
            self.assertIn("license=cc0%2Cby", seen_urls[2])
            self.assertEqual(len(ov), 1)
            self.assertEqual(ov[0]["license"], "CC BY 2.0")


if __name__ == "__main__":
    unittest.main()
