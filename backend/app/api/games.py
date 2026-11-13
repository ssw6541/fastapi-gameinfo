import logging
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, Path, Query

from ..config import Settings
from ..deps import get_cfg, get_db, get_steam, rate_limit
from ..errors import UpstreamError
from ..schemas import (Genre, GameDetail, ReviewSort, ReviewStats, ReviewsResponse, SearchResponse, SortKey, GameSummary)
from ..services import catalog, games, reviews
from ..steam.client import SteamClient
from ..steam.parsers import REVIEW_LANGUAGES

log = logging.getLogger("app.api")
router = APIRouter(prefix="/api", dependencies=[Depends(rate_limit)])

AppId = Annotated[int, Path(ge=1, le=2_147_483_647, description="Steam AppID")]
Db = Annotated[aiosqlite.Connection, Depends(get_db)]
Steam = Annotated[SteamClient, Depends(get_steam)]
Cfg = Annotated[Settings, Depends(get_cfg)]


@router.get("/games/search", response_model=SearchResponse, summary="게임 검색 (영/한 부분일치)")
async def search_games(
    db: Db, steam: Steam,
    q: Annotated[str | None, Query(max_length=100, description="검색어 (부분 일치, 한국어/영어)")] = None,
    sort: SortKey = "relevance",
    genre: Annotated[list[int] | None, Query(description="장르 태그 ID (여러 개 가능)")] = None,
    free: bool | None = None,
    price_max: Annotated[int | None, Query(ge=0, le=10_000_000, description="최대 가격(원)")] = None,
    year_from: Annotated[int | None, Query(ge=1970, le=2100)] = None,
    year_to: Annotated[int | None, Query(ge=1970, le=2100)] = None,
    min_reviews: Annotated[int | None, Query(ge=0)] = None,
    min_rating: Annotated[int | None, Query(ge=0, le=100, description="최소 긍정 비율(%)")] = None,
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=60)] = 24,
):
    q = (q or "").strip() or None
    kw = dict(sort=sort, genre=genre, free=free, price_max=price_max, year_from=year_from, year_to=year_to,
              min_reviews=min_reviews, min_rating=min_rating, offset=(page - 1) * page_size, limit=page_size)
    total, items = await catalog.search_local(db, q, **kw)
    discovered = False
    # Local catalog may be incomplete (keyless setup): top it up from Steam's public search endpoint.
    if q and len(q) >= 2 and page == 1 and total < 5:
        try:
            if await catalog.live_discover(db, steam, q):
                discovered = True
                total, items = await catalog.search_local(db, q, **kw)
        except UpstreamError as e:
            log.warning("live discovery failed: %s", e.message)
    return SearchResponse(query=q, total=total, page=page, page_size=page_size, items=items, live_discovery=discovered)


@router.get("/games/suggest", response_model=list[GameSummary], summary="검색어 자동완성")
async def suggest(db: Db, steam: Steam, q: Annotated[str, Query(min_length=1, max_length=60)]):
    _, items = await catalog.search_local(db, q.strip(), limit=8)
    if len(items) < 3 and len(q.strip()) >= 2:
        try:
            if await catalog.live_discover(db, steam, q.strip()):
                _, items = await catalog.search_local(db, q.strip(), limit=8)
        except UpstreamError:
            pass
    return items


@router.get("/games/featured", response_model=list[GameSummary], summary="인기 게임 (리뷰 수 기준)")
async def featured(db: Db, genre: Annotated[int | None, Query()] = None, limit: Annotated[int, Query(ge=1, le=40)] = 12):
    _, items = await catalog.search_local(db, None, sort="reviews", genre=[genre] if genre else None, limit=limit,
                                          min_reviews=1000)
    return items


@router.get("/games/home", response_model=list[GameSummary], summary="홈 탭: 신작/할인/출시 예정")
async def home_tab(db: Db, steam: Steam, tab: Annotated[str, Query(pattern="^(new|sale|upcoming)$")],
                   limit: Annotated[int, Query(ge=1, le=24)] = 12):
    return await catalog.home_list(db, steam, tab, limit)


@router.get("/games/{appid}", response_model=GameDetail, summary="게임 상세 정보")
async def game_detail(appid: AppId, db: Db, steam: Steam, s: Cfg):
    return await games.get_game(db, steam, s, appid)


@router.get("/games/{appid}/reviews", response_model=ReviewsResponse, summary="Steam 리뷰 (커서 페이지네이션)")
async def game_reviews(
    appid: AppId, db: Db, steam: Steam, s: Cfg,
    sort: ReviewSort = "helpful",
    language: Annotated[str, Query(description="Steam 언어 코드 또는 all")] = "all",
    review_type: Annotated[str, Query(pattern="^(all|positive|negative)$")] = "all",
    purchase_type: Annotated[str, Query(pattern="^(all|steam|non_steam_purchase)$")] = "all",
    day_range: Annotated[int | None, Query(ge=1, le=365, description="helpful 정렬 시 최근 N일")] = None,
    cursor: Annotated[str, Query(pattern=r"^[A-Za-z0-9+/=_*%.\-]{1,300}$")] = "*",
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
):
    if language != "all" and language not in REVIEW_LANGUAGES:
        from ..errors import AppError
        raise AppError(422, "invalid_language", f"지원하지 않는 언어 코드입니다: {language}")
    return await reviews.get_reviews(db, steam, s, appid, sort=sort, language=language, review_type=review_type,
                                     purchase_type=purchase_type, day_range=day_range, cursor=cursor, per_page=per_page)


@router.get("/games/{appid}/review-stats", response_model=ReviewStats, summary="리뷰 통계 (공식 집계 + 표본)")
async def review_stats(
    appid: AppId, db: Db, steam: Steam, s: Cfg,
    pages: Annotated[int, Query(ge=1, le=5, description="표본 크기: 100개 × pages")] = 3,
    language: str = "all",
):
    if language != "all" and language not in REVIEW_LANGUAGES:
        from ..errors import AppError
        raise AppError(422, "invalid_language", f"지원하지 않는 언어 코드입니다: {language}")
    return await reviews.get_stats(db, steam, s, appid, pages=pages, language=language)


@router.get("/genres", response_model=list[Genre], summary="장르 목록")
async def genres(db: Db):
    return await catalog.list_genres(db)


@router.get("/languages", summary="리뷰 언어 코드 목록")
async def languages():
    return REVIEW_LANGUAGES
