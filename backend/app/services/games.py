"""Game detail retrieval with DB persistence, TTL freshness and stale-on-error fallback."""
import asyncio
import json
import logging
import time

import aiosqlite

from ..cache import cache_get, cache_set
from ..config import Settings
from ..errors import NotFound, UpstreamError
from ..steam.client import SteamClient
from ..steam.parsers import normalize_details, normalize_summary, header_image
from . import catalog

log = logging.getLogger("app.games")


async def log_fetch(db: aiosqlite.Connection, kind: str, target: str, ok: bool, message: str = "") -> None:
    await db.execute("INSERT INTO fetch_log(ts, kind, target, ok, message) VALUES(?,?,?,?,?)",
                     (int(time.time()), kind, target, int(ok), message[:500]))
    await db.commit()


async def review_summary(db: aiosqlite.Connection, steam: SteamClient, s: Settings, appid: int) -> dict | None:
    key = f"rsum:{appid}"
    hit = await cache_get(db, key)
    if hit:
        return hit
    resp = await steam.reviews(appid, num_per_page=1, language="all", filter="all", purchase_type="all")
    summ = normalize_summary(resp["query_summary"])
    await cache_set(db, key, summ, s.cache_ttl_seconds)
    if summ["positive_ratio"] is not None:  # keep listing sorts consistent with official totals
        await db.execute("UPDATE games SET review_pct=?, review_count=? WHERE appid=?",
                         (round(summ["positive_ratio"] * 100), summ["total_reviews"], appid))
        await db.commit()
    return summ


async def _persist_details(db: aiosqlite.Connection, d: dict) -> None:
    now = int(time.time())
    price = d["price"]
    await catalog.upsert_names(db, d["appid"], d["name_en"], d["name"])
    await db.execute(
        """UPDATE games SET type=?, short_description=?, release_date=COALESCE(?, release_date),
           is_free=?, price_final=?, price_initial=?, discount_percent=?, currency=?,
           detail_json=?, detail_fetched_at=?, updated_at=?, header_url=? WHERE appid=?""",
        (d["type"], d["short_description"], d["release_date"], int(d["is_free"]),
         int(price["final"] * 100) if price else (0 if d["is_free"] else None),
         int(price["initial"] * 100) if price else None, (price or {}).get("discount_percent"),
         (price or {}).get("currency"), json.dumps(d, ensure_ascii=False), now, now, d["header_image"], d["appid"]),
    )
    await db.commit()


async def get_game(db: aiosqlite.Connection, steam: SteamClient, s: Settings, appid: int, refresh: bool = False) -> dict:
    async with db.execute("SELECT * FROM games WHERE appid=?", (appid,)) as c:
        row = await c.fetchone()
    fresh = bool(row and row["detail_fetched_at"] and time.time() - row["detail_fetched_at"] < s.detail_ttl_seconds)
    stale = False
    detail: dict | None = json.loads(row["detail_json"]) if row and row["detail_json"] else None
    if not fresh or refresh:
        try:
            ko, en = await asyncio.gather(steam.app_details(appid, "koreana"), steam.app_details(appid, "english"))
            if not ko:
                await log_fetch(db, "detail", str(appid), False, "appdetails success=false")
                if detail is None:
                    raise NotFound("Steam에서 해당 AppID의 게임 정보를 찾을 수 없습니다.")
            else:
                detail = normalize_details(ko, en)
                await _persist_details(db, detail)
                await log_fetch(db, "detail", str(appid), True)
        except UpstreamError as e:
            await log_fetch(db, "detail", str(appid), False, e.message)
            if detail is None:
                raise
            stale = True  # serve the last stored copy
    assert detail is not None
    try:
        summary = await review_summary(db, steam, s, appid)
    except UpstreamError:
        summary = None
    async with db.execute("SELECT detail_fetched_at FROM games WHERE appid=?", (appid,)) as c:
        ts = (await c.fetchone())["detail_fetched_at"]
    detail.setdefault("header_image", header_image(appid))
    return {**detail, "review_summary": summary, "fetched_at": ts, "stale": stale}
