"""Collector CLI:  python -m app.cli crawl-search --max-games 3000 | crawl-applist | refresh-details --limit 50 | stats"""
import argparse
import asyncio
import json
import logging

from .config import get_settings
from .db import connect, run_migrations
from .services import catalog, collector
from .steam.client import SteamClient


async def main() -> None:
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crawl-search")
    c.add_argument("--max-games", type=int, default=5000)
    c.add_argument("--reset", action="store_true")
    sub.add_parser("crawl-applist")
    r = sub.add_parser("refresh-details")
    r.add_argument("--limit", type=int, default=50)
    r.add_argument("--force", action="store_true")
    sub.add_parser("stats")
    a = p.parse_args()

    s = get_settings()
    logging.basicConfig(level=s.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    run_migrations(s.db_file)
    db, steam = await connect(), SteamClient(s)
    try:
        if a.cmd == "crawl-search":
            out = await collector.crawl_search(db, steam, max_games=a.max_games, reset=a.reset)
        elif a.cmd == "crawl-applist":
            out = await collector.crawl_applist(db, steam)
        elif a.cmd == "refresh-details":
            out = await collector.refresh_details(db, steam, s, limit=a.limit, force=a.force)
        else:
            out = await catalog.catalog_stats(db)
        print(json.dumps(out, ensure_ascii=False))
    finally:
        await steam.aclose()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
