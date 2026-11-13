"""Review retrieval (cursor pagination, caching, dedup) and sample-based statistics."""
import asyncio
import hashlib
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

import aiosqlite

from ..cache import cache_get, cache_set
from ..config import Settings
from ..steam.client import SteamClient
from ..errors import UpstreamError
from ..steam.parsers import normalize_review
from .games import review_summary

SORT_TO_FILTER = {"helpful": "all", "recent": "recent", "updated": "updated"}


async def get_reviews(
    db: aiosqlite.Connection, steam: SteamClient, s: Settings, appid: int, *, sort: str, language: str,
    review_type: str, purchase_type: str, day_range: int | None, cursor: str, per_page: int,
) -> dict:
    key = "rv:" + hashlib.sha1(
        f"{appid}|{sort}|{language}|{review_type}|{purchase_type}|{day_range}|{cursor}|{per_page}".encode()
    ).hexdigest()
    hit = await cache_get(db, key)
    if hit:
        return {**hit, "cached": True}
    resp = await steam.reviews(
        appid, filter=SORT_TO_FILTER[sort], language=language, review_type=review_type, purchase_type=purchase_type,
        num_per_page=per_page, cursor=cursor,
        day_range=(0 if day_range is None else day_range) if sort == "helpful" else None,
    )
    try:  # query_summary totals are only sent on unfiltered first pages, so use the dedicated cached summary
        summary = await review_summary(db, steam, s, appid)
    except UpstreamError:
        summary = None
    seen, out = set(), []
    for r in resp.get("reviews") or []:
        n = normalize_review(r, appid)
        if n and n["id"] not in seen:
            seen.add(n["id"])
            out.append(n)
    next_cursor = resp.get("cursor")
    result = {
        "appid": appid,
        "reviews": out,
        "cursor": next_cursor,
        "has_more": bool(out) and bool(next_cursor) and next_cursor != cursor and len(out) >= per_page,
        # Steam-wide totals; NOT narrowed by the language/type filters above.
        "summary": summary,
        "query": {"sort": sort, "language": language, "review_type": review_type,
                  "purchase_type": purchase_type, "day_range": day_range, "per_page": per_page},
        "fetched_at": int(time.time()),
    }
    await cache_set(db, key, result, s.cache_ttl_seconds)
    return {**result, "cached": False}


async def get_stats(
    db: aiosqlite.Connection, steam: SteamClient, s: Settings, appid: int, *, pages: int, language: str,
) -> dict:
    """Official totals + a clearly-labelled sample (most recent N reviews) for language/trend breakdowns."""
    key = f"rstats:{appid}:{pages}:{language}"
    hit = await cache_get(db, key)
    if hit:
        return {**hit, "cached": True}
    summary_task = asyncio.create_task(review_summary(db, steam, s, appid))
    reviews: list[dict] = []
    cursor, seen = "*", set()
    for _ in range(pages):
        resp = await steam.reviews(appid, filter="recent", language=language, num_per_page=100, cursor=cursor,
                                   purchase_type="all")
        batch = resp.get("reviews") or []
        for r in batch:
            n = normalize_review(r, appid)
            if n and n["id"] not in seen:
                seen.add(n["id"])
                reviews.append(n)
        nxt = resp.get("cursor")
        if len(batch) < 100 or not nxt or nxt == cursor:
            break
        cursor = nxt
    summary = await summary_task

    langs = Counter(r["language"] for r in reviews)
    daily: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in reviews:
        d = datetime.fromtimestamp(r["created_at"], tz=timezone.utc).strftime("%Y-%m-%d")
        daily[d][0 if r["voted_up"] else 1] += 1
    pos = sum(1 for r in reviews if r["voted_up"])
    playtimes = sorted(r["playtime_forever_min"] for r in reviews)
    result = {
        "appid": appid,
        "official": summary,  # Steam-provided totals across ALL reviews
        "sample": {
            "kind": "most_recent",
            "language_filter": language,
            "size": len(reviews),
            "positive": pos,
            "negative": len(reviews) - pos,
            "positive_ratio": round(pos / len(reviews), 4) if reviews else None,
            "median_playtime_hours": round(playtimes[len(playtimes) // 2] / 60, 1) if playtimes else None,
            "oldest_at": min((r["created_at"] for r in reviews), default=None),
            "newest_at": max((r["created_at"] for r in reviews), default=None),
            "languages": [{"language": k, "count": v} for k, v in langs.most_common()],
            "daily": [{"date": d, "positive": v[0], "negative": v[1]} for d, v in sorted(daily.items())],
        },
        "fetched_at": int(time.time()),
    }
    await cache_set(db, key, result, s.cache_ttl_seconds * 2)
    return {**result, "cached": False}
