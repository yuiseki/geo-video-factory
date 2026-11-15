"""Summarise the public numbers of a video from a yt-dlp .info.json.

The counts are a snapshot taken when yt-dlp ran (`epoch`), not final numbers. Hidden counts
(likes, subscribers) stay None instead of being treated as zero.

usage: python3 refstats.py <a.info.json> [<b.info.json> ...]
prints one JSON object per file.
"""
from __future__ import annotations

import json
import pathlib
import sys


def load(path) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding='utf-8'))


def ratio(a, b):
    if a is None or not b:
        return None
    return a / b


def summarise(info: dict) -> dict:
    views = info.get('view_count')
    followers = info.get('channel_follower_count')
    pub, fetched = info.get('timestamp'), info.get('epoch')
    days = round((fetched - pub) / 86400, 1) if pub and fetched else None
    chapters = info.get('chapters') or []
    ud = info.get('upload_date') or ''
    return {
        'id': info.get('id'),
        'title': info.get('title'),
        'channel': info.get('channel'),
        'published': f'{ud[:4]}-{ud[4:6]}-{ud[6:]}' if len(ud) == 8 else None,
        'days_since_publish': days,
        'duration_seconds': info.get('duration'),
        'views': views,
        'likes': info.get('like_count'),
        'comments': info.get('comment_count'),
        'followers': followers,
        'views_per_follower': ratio(views, followers),
        'like_rate': ratio(info.get('like_count'), views),
        'comment_rate': ratio(info.get('comment_count'), views),
        'views_per_day': ratio(views, days),
        'chapters': len(chapters),
        'mean_chapter_seconds': (round(sum(c['end_time'] - c['start_time'] for c in chapters) / len(chapters), 1)
                                 if chapters else None),
        'tags': info.get('tags') or [],
    }


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for p in sys.argv[1:]:
        print(json.dumps(summarise(load(p)), ensure_ascii=False))


if __name__ == '__main__':
    main()
