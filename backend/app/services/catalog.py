"""Local catalog: upserts from Steam sources + FTS5 (trigram) search over English/Korean names."""
import asyncio
import json
import logging
import time
from typing import Any

import aiosqlite

from ..cache import cache_get, cache_set
from ..steam.client import SteamClient
from ..steam.parsers import GENRE_TAGS, capsule_image, header_image

log = logging.getLogger("app.catalog")

SORTS = {
    "relevance": None,
    "reviews": "g.review_count DESC NULLS LAST",
    "rating": "g.review_pct DESC NULLS LAST, g.review_count DESC",
    "newest": "g.release_ts DESC NULLS LAST",
    "oldest": "g.release_ts ASC NULLS LAST",
    "price_asc": "g.price_final ASC NULLS LAST",
    "price_desc": "g.price_final DESC NULLS LAST",
    "name": "COALESCE(g.name_ko, g.name_en) COLLATE NOCASE ASC",
}


def _is_hangul_or_cjk(s: str) -> bool:
    return any(ord(c) > 0x2E80 for c in s)


async def _refresh_fts(db: aiosqlite.Connection, appid: int) -> None:
    async with db.execute("SELECT name_en, name_ko FROM games WHERE appid=?", (appid,)) as c:
        r = await c.fetchone()
    if not r:
        return
    names = " ".join(dict.fromkeys(n for n in (r["name_en"], r["name_ko"]) if n))
    await db.execute("DELETE FROM games_fts WHERE rowid=?", (appid,))
    await db.execute("INSERT INTO games_fts(rowid, names) VALUES(?,?)", (appid, names))


async def upsert_listing(db: aiosqlite.Connection, row: dict, lang: str) -> None:
    """Insert/update one catalog row coming from search-page crawling. lang: 'english'|'koreana'."""
    now = int(time.time())
    name_col = "name_en" if lang == "english" else "name_ko"
    await db.execute(
        f"""INSERT INTO games(appid, {name_col}, release_date, release_ts, price_final, discount_percent,
                              currency, review_pct, review_count, capsule_url, listed_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(appid) DO UPDATE SET
              {name_col}=excluded.{name_col},
              release_date=COALESCE(excluded.release_date, release_date),
              release_ts=COALESCE(excluded.release_ts, release_ts),
              price_final=COALESCE(excluded.price_final, price_final),
              discount_percent=COALESCE(excluded.discount_percent, discount_percent),
              currency=COALESCE(excluded.currency, currency),
              review_pct=COALESCE(excluded.review_pct, review_pct),
              review_count=COALESCE(excluded.review_count, review_count),
              capsule_url=COALESCE(excluded.capsule_url, capsule_url),
              updated_at=excluded.updated_at""",
        (row["appid"], row["title"], row.get("release_date"), row.get("release_ts"), row.get("price_final"),
         row.get("discount_percent"), "KRW" if row.get("price_final") is not None else None,
         row.get("review_pct"), row.get("review_count"), row.get("capsule_url"), now, now),
    )
    for t in row.get("tag_ids", []):
        if t in GENRE_TAGS:
            await db.execute("INSERT OR IGNORE INTO game_tags(appid, tag_id) VALUES(?,?)", (row["appid"], t))
    await _refresh_fts(db, row["appid"])


async def upsert_names(db: aiosqlite.Connection, appid: int, name_en: str | None, name_ko: str | None) -> None:
    now = int(time.time())
    await db.execute(
        """INSERT INTO games(appid, name_en, name_ko, listed_at, updated_at) VALUES(?,?,?,?,?)
           ON CONFLICT(appid) DO UPDATE SET name_en=COALESCE(excluded.name_en, name_en),
                                            name_ko=COALESCE(excluded.name_ko, name_ko), updated_at=excluded.updated_at""",
        (appid, name_en, name_ko, now, now),
    )
    await _refresh_fts(db, appid)


def to_summary(r: aiosqlite.Row, genre_ids: list[int] | None = None) -> dict:
    appid = r["appid"]
    final = r["price_final"]
    is_free = bool(r["is_free"]) if r["is_free"] is not None else (final == 0 if final is not None else None)
    ko = r["name_ko"] if r["name_ko"] != r["name_en"] else None  # no Korean title when Steam has none
    return {
        "appid": appid,
        "name": ko or r["name_en"],
        "name_en": r["name_en"],
        "name_ko": ko,
        "header_image": r["header_url"] or header_image(appid),
        "capsule_image": r["capsule_url"] or capsule_image(appid),
        "release_date": r["release_date"],
        "release_ts": r["release_ts"],
        "is_free": is_free,
        "price": None if final is None else {
            "currency": r["currency"] or "KRW",
            "final": final / 100,
            "discount_percent": r["discount_percent"] or 0,
        },
        "review_pct": r["review_pct"],
        "review_count": r["review_count"],
        "genres": [GENRE_TAGS[t][1] for t in (genre_ids or []) if t in GENRE_TAGS],
    }


def _like(s: str) -> str:
    return "%" + s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _fts_phrase(s: str) -> str:
    return '"' + s.replace('"', '""') + '"'


async def search_local(
    db: aiosqlite.Connection, q: str | None, *, sort: str = "relevance", genre: list[int] | None = None,
    free: bool | None = None, price_max: int | None = None, year_from: int | None = None,
    year_to: int | None = None, min_reviews: int | None = None, min_rating: int | None = None,
    offset: int = 0, limit: int = 24,
) -> tuple[int, list[dict]]:
    where, args = ["1=1"], []
    order_prefix = ""
    oargs: list[Any] = []
    tokens = [t for t in (q or "").split() if t][:6]
    long_t = [t for t in tokens if len(t) >= 3]
    short_t = [t for t in tokens if len(t) < 3]
    if long_t:
        where.append("g.appid IN (SELECT rowid FROM games_fts WHERE games_fts MATCH ?)")
        args.append(" AND ".join(_fts_phrase(t) for t in long_t))
    for t in short_t:
        where.append("(COALESCE(g.name_en,'') || ' ' || COALESCE(g.name_ko,'')) LIKE ? ESCAPE '\\'")
        args.append(_like(t))
    if tokens:
        full = " ".join(tokens)
        # rank exact > prefix > contains
        order_prefix = ("CASE WHEN lower(g.name_en)=lower(?) OR lower(g.name_ko)=lower(?) THEN 0 "
                        "WHEN g.name_en LIKE ? ESCAPE '\\' OR g.name_ko LIKE ? ESCAPE '\\' THEN 1 ELSE 2 END, ")
        pre = _like(full)[1:]
        oargs += [full, full, pre, pre]
    if genre:
        where.append(f"g.appid IN (SELECT appid FROM game_tags WHERE tag_id IN ({','.join('?' * len(genre))}))")
        args += genre
    if free is True:
        where.append("g.price_final = 0")
    elif free is False:
        where.append("g.price_final > 0")
    if price_max is not None:
        where.append("g.price_final <= ?")
        args.append(price_max * 100)
    if year_from is not None:
        where.append("g.release_ts >= strftime('%s', ?||'-01-01')")
        args.append(str(year_from))
    if year_to is not None:
        where.append("g.release_ts < strftime('%s', ?||'-01-01')")
        args.append(str(year_to + 1))
    if min_reviews is not None:
        where.append("g.review_count >= ?")
        args.append(min_reviews)
    if min_rating is not None:
        where.append("g.review_pct >= ?")
        args.append(min_rating)
    wsql = " AND ".join(where)
    sort_sql = SORTS.get(sort) or "g.review_count DESC NULLS LAST"
    async with db.execute(f"SELECT COUNT(*) FROM games g WHERE {wsql}", args) as c:
        total = (await c.fetchone())[0]
    order = (order_prefix if sort == "relevance" else "") + sort_sql
    oa = oargs if sort == "relevance" else []
    async with db.execute(
        f"SELECT g.* FROM games g WHERE {wsql} ORDER BY {order}, g.appid LIMIT ? OFFSET ?",
        [*args, *oa, limit, offset],
    ) as c:
        rows = await c.fetchall()
    ids = [r["appid"] for r in rows]
    tags: dict[int, list[int]] = {i: [] for i in ids}
    if ids:
        async with db.execute(f"SELECT appid, tag_id FROM game_tags WHERE appid IN ({','.join('?' * len(ids))})", ids) as c:
            for t in await c.fetchall():
                tags[t["appid"]].append(t["tag_id"])
    return total, [to_summary(r, tags[r["appid"]]) for r in rows]


async def live_discover(db: aiosqlite.Connection, steam: SteamClient, q: str, ttl: int = 3600) -> int:
    """Keyless discovery of games not yet in the local catalog via the public store search endpoint."""
    key = f"live:{q.lower()}"
    if await cache_get(db, key) is not None:
        return 0
    results = await asyncio.gather(
        steam.store_search(q, "english"), steam.store_search(q, "koreana"), return_exceptions=True
    )
    n = 0
    en, ko = (r if isinstance(r, list) else [] for r in results)
    if all(isinstance(r, Exception) for r in results):
        raise next(iter(results))  # type: ignore[misc]
    ko_by = {i["id"]: i for i in ko if i.get("type") == "app"}
    for it in en + ko:
        if it.get("type") != "app":
            continue
        appid = it["id"]
        name_en = next((x["name"] for x in en if x["id"] == appid), None)
        name_ko = ko_by.get(appid, {}).get("name")
        await upsert_names(db, appid, name_en, name_ko)
        price = it.get("price")
        if price and "final" in price:
            await db.execute("UPDATE games SET price_final=COALESCE(price_final, ?), currency=COALESCE(currency, ?) WHERE appid=?",
                             (price["final"], price.get("currency"), appid))
        n += 1
    await db.commit()
    await cache_set(db, key, {"n": n}, ttl)
    return n


HOME_TABS = {
    "new": {"filter": "popularnew", "sort_by": "Released_DESC"},  # 신작 (최신 출시순)
    "sale": {"specials": 1},                                       # 할인 중 (리뷰 많은 순)
    "upcoming": {"filter": "popularcomingsoon", "sort_by": None},  # 출시 예정 (인기순)
}


async def home_list(db: aiosqlite.Connection, steam: SteamClient, tab: str, limit: int, ttl: int = 900) -> list[dict]:
    """Curated home tabs from Steam's own store listing (games only). Ordered ids cached for `ttl` seconds."""
    from ..steam.parsers import parse_search_html

    key = f"home:{tab}"
    ids = await cache_get(db, key)
    if ids is None:
        data = await steam.search_page(0, 24, "koreana", **HOME_TABS[tab])
        rows = parse_search_html(data.get("results_html", ""))
        for r in rows:
            await upsert_listing(db, r, "koreana")
        await db.commit()
        ids = [r["appid"] for r in rows]
        await cache_set(db, key, ids, ttl)
    ids = ids[:limit]
    if not ids:
        return []
    async with db.execute(f"SELECT * FROM games WHERE appid IN ({','.join('?' * len(ids))})", ids) as c:
        by_id = {r["appid"]: r for r in await c.fetchall()}
    tags: dict[int, list[int]] = {i: [] for i in ids}
    async with db.execute(f"SELECT appid, tag_id FROM game_tags WHERE appid IN ({','.join('?' * len(ids))})", ids) as c:
        for t in await c.fetchall():
            tags[t["appid"]].append(t["tag_id"])
    return [to_summary(by_id[i], tags[i]) for i in ids if i in by_id]


async def list_genres(db: aiosqlite.Connection) -> list[dict]:
    counts: dict[int, int] = {}
    async with db.execute("SELECT tag_id, COUNT(*) n FROM game_tags GROUP BY tag_id") as c:
        for r in await c.fetchall():
            counts[r["tag_id"]] = r["n"]
    return [{"id": i, "name_en": n[0], "name": n[1], "count": counts.get(i, 0)} for i, n in GENRE_TAGS.items()]


async def catalog_stats(db: aiosqlite.Connection) -> dict:
    async with db.execute("SELECT COUNT(*) n, SUM(detail_fetched_at IS NOT NULL) d, MAX(updated_at) u FROM games") as c:
        r = await c.fetchone()
    return {"games": r["n"], "with_details": r["d"] or 0, "last_updated": r["u"]}


def dumps(o) -> str:
    return json.dumps(o, ensure_ascii=False)
