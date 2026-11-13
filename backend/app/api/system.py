import asyncio
import time
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request

from ..cache import cache_purge
from ..config import Settings
from ..db import connect
from ..deps import get_cfg, get_db, require_admin
from ..services import catalog, collector

router = APIRouter(prefix="/api")
admin = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)], tags=["admin"])


@router.get("/health", summary="Health check")
async def health(db: Annotated[aiosqlite.Connection, Depends(get_db)]):
    await db.execute("SELECT 1")
    return {"status": "ok", "time": int(time.time())}


@router.get("/status", summary="카탈로그/수집 상태")
async def status(db: Annotated[aiosqlite.Connection, Depends(get_db)], s: Annotated[Settings, Depends(get_cfg)], request: Request):
    stats = await catalog.catalog_stats(db)
    async with db.execute("SELECT key, value, updated_at FROM crawl_state") as c:
        state = {r["key"]: {"value": r["value"], "updated_at": r["updated_at"]} for r in await c.fetchall()}
    async with db.execute("SELECT COUNT(*) FROM fetch_log WHERE ok=0 AND ts > ?", (int(time.time()) - 86400,)) as c:
        failures = (await c.fetchone())[0]
    return {
        "catalog": stats,
        "steam_api_key_configured": bool(s.steam_api_key),
        "crawl": state,
        "failures_24h": failures,
        "running_jobs": sorted(request.app.state.jobs),
        "env": s.app_env,
    }


async def _run_job(app, name: str, coro_factory):
    if name in app.state.jobs:
        return
    app.state.jobs.add(name)
    db = await connect(app.state.settings.db_file)
    try:
        await coro_factory(db)
    finally:
        await db.close()
        app.state.jobs.discard(name)


@admin.post("/crawl/search", summary="[관리] 검색 목록 수집 (키 불필요, 재개 가능)")
async def admin_crawl_search(request: Request, tasks: BackgroundTasks, max_games: Annotated[int, Query(ge=100, le=100000)] = 5000, reset: bool = False):
    steam = request.app.state.steam
    tasks.add_task(_run_job, request.app, "crawl_search",
                   lambda db: collector.crawl_search(db, steam, max_games=max_games, reset=reset))
    return {"started": "crawl_search"}


@admin.post("/crawl/applist", summary="[관리] IStoreService/GetAppList 수집 (STEAM_API_KEY 필요)")
async def admin_crawl_applist(request: Request, tasks: BackgroundTasks):
    steam = request.app.state.steam
    tasks.add_task(_run_job, request.app, "crawl_applist", lambda db: collector.crawl_applist(db, steam))
    return {"started": "crawl_applist"}


@admin.post("/refresh-details", summary="[관리] 상세 정보 갱신")
async def admin_refresh(request: Request, tasks: BackgroundTasks, limit: Annotated[int, Query(ge=1, le=500)] = 50):
    steam, s = request.app.state.steam, request.app.state.settings
    tasks.add_task(_run_job, request.app, "refresh_details", lambda db: collector.refresh_details(db, steam, s, limit=limit))
    return {"started": "refresh_details"}


@admin.post("/cache/purge", summary="[관리] 만료 캐시 정리")
async def admin_purge(db: Annotated[aiosqlite.Connection, Depends(get_db)]):
    return {"purged": await cache_purge(db)}


@admin.get("/failures", summary="[관리] 최근 수집 실패 로그")
async def admin_failures(db: Annotated[aiosqlite.Connection, Depends(get_db)], limit: Annotated[int, Query(ge=1, le=200)] = 50):
    async with db.execute("SELECT * FROM fetch_log WHERE ok=0 ORDER BY ts DESC LIMIT ?", (limit,)) as c:
        return [dict(r) for r in await c.fetchall()]
