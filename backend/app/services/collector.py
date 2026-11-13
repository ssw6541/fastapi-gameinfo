"""Resumable catalog collection. Progress lives in crawl_state, failures in fetch_log.

Jobs:
  crawl_search   keyless: pages through the public store search listing (English + Korean names).
  crawl_applist  needs STEAM_API_KEY: IStoreService/GetAppList (complete id/name list).
  refresh_details re-fetch appdetails for the most-reviewed games whose cached details are missing/stale.
"""
import asyncio
import logging
import time

import aiosqlite

from ..config import Settings
from ..errors import UpstreamError
from ..steam.client import SteamClient
from ..steam.parsers import parse_search_html
from . import catalog
from .games import get_game, log_fetch

log = logging.getLogger("app.collector")
PAGE = 100


async def _state_get(db, key, default=None):
    async with db.execute("SELECT value FROM crawl_state WHERE key=?", (key,)) as c:
        r = await c.fetchone()
    return r["value"] if r else default


async def _state_set(db, key, value):
    await db.execute(
        "INSERT INTO crawl_state(key,value,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, str(value), int(time.time())),
    )
    await db.commit()


async def crawl_search(db: aiosqlite.Connection, steam: SteamClient, *, max_games: int = 5000,
                       languages=("english", "koreana"), reset: bool = False) -> dict:
    """Walk the store listing ordered by review count. Resumes from the stored offset unless reset."""
    stats = {"pages": 0, "rows": 0, "errors": 0}
    for lang in languages:
        key = f"search_offset:{lang}"
        start = 0 if reset else int(await _state_get(db, key, 0))
        while start < max_games:
            try:
                data = await steam.search_page(start, PAGE, lang)
            except UpstreamError as e:
                stats["errors"] += 1
                await log_fetch(db, "crawl_search", f"{lang}@{start}", False, e.message)
                break  # stop; next run resumes at `start`
            rows = parse_search_html(data.get("results_html", ""))
            if not rows:
                await _state_set(db, f"search_total:{lang}", data.get("total_count", 0))
                await _state_set(db, key, 0)  # finished a full pass
                break
            for r in rows:
                await catalog.upsert_listing(db, r, lang)
            await db.commit()
            start += PAGE
            await _state_set(db, key, start)
            await _state_set(db, f"search_total:{lang}", data.get("total_count", 0))
            stats["pages"] += 1
            stats["rows"] += len(rows)
            log.info("crawl %s %d/%s", lang, start, data.get("total_count"))
    await _state_set(db, "last_crawl_at", int(time.time()))
    return stats


async def crawl_applist(db: aiosqlite.Connection, steam: SteamClient, *, max_pages: int = 5) -> dict:
    last = int(await _state_get(db, "applist_last_appid", 0))
    pages = rows = 0
    while pages < max_pages:
        resp = await steam.app_list(last_appid=last)
        apps = resp.get("apps") or []
        for a in apps:
            await catalog.upsert_names(db, a["appid"], a.get("name"), None)
        await db.commit()
        rows += len(apps)
        pages += 1
        last = resp.get("last_appid") or last
        await _state_set(db, "applist_last_appid", last)
        if not resp.get("have_more_results"):
            await _state_set(db, "applist_last_appid", 0)
            break
    return {"pages": pages, "rows": rows}


async def refresh_details(db: aiosqlite.Connection, steam: SteamClient, s: Settings, *, limit: int = 50, force: bool = False) -> dict:
    cutoff = int(time.time()) + 1 if force else int(time.time()) - s.detail_ttl_seconds  # force: refresh the top games regardless of age
    async with db.execute(
        "SELECT appid FROM games WHERE detail_fetched_at IS NULL OR detail_fetched_at < ? "
        "ORDER BY review_count DESC NULLS LAST LIMIT ?", (cutoff, limit)) as c:
        ids = [r["appid"] for r in await c.fetchall()]
    ok = failed = 0
    for appid in ids:
        try:
            await get_game(db, steam, s, appid, refresh=True)
            ok += 1
        except Exception as e:  # noqa: BLE001 - keep the batch going, failure is logged
            failed += 1
            await log_fetch(db, "refresh_details", str(appid), False, str(e))
        await asyncio.sleep(0)
    return {"requested": len(ids), "ok": ok, "failed": failed}
