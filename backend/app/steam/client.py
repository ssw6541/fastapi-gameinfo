"""Async Steam HTTP client: concurrency cap, min interval, retries with backoff, 429/403 handling."""
import asyncio
import json
import logging
import time
from typing import Any

import httpx

from ..config import Settings
from ..errors import UpstreamError

log = logging.getLogger("app.steam")

REVIEW_FILTER = {"helpful": 0, "all": 0, "recent": 1, "updated": 2, "funny": 3}
REVIEW_TYPE = {"all": 0, "positive": 1, "negative": 2}
PURCHASE_TYPE = {"steam": 0, "all": 1, "non_steam_purchase": 2}


class SteamClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.s = settings
        self._http = httpx.AsyncClient(
            timeout=settings.steam_request_timeout,
            transport=transport,
            headers={"User-Agent": "SteamGameInfoApp/1.0"},
            follow_redirects=False,
        )
        self._sem = asyncio.Semaphore(settings.steam_max_concurrency)
        self._lock = asyncio.Lock()
        self._next_at = 0.0
        self._blocked_until = 0.0  # set after a 429 so every caller backs off

    async def aclose(self):
        await self._http.aclose()

    async def _pace(self):
        async with self._lock:
            now = time.monotonic()
            start = max(self._next_at, self._blocked_until, now)
            self._next_at = start + self.s.steam_min_interval_seconds
        wait = start - now
        if wait > 0:
            await asyncio.sleep(wait)

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        last: Exception | None = None
        for attempt in range(self.s.steam_max_retries + 1):
            async with self._sem:
                await self._pace()
                try:
                    r = await self._http.get(url, params=params)
                except (httpx.TimeoutException, httpx.TransportError) as e:
                    last = e
                    log.warning("steam transport error (%s) attempt=%d", type(e).__name__, attempt)
                else:
                    if r.status_code == 200:
                        try:
                            return r.json()
                        except json.JSONDecodeError:
                            raise UpstreamError("Steam이 올바르지 않은 응답을 반환했습니다.")
                    if r.status_code == 429:
                        try:
                            delay = float(r.headers.get("Retry-After", 2 ** (attempt + 1)))
                        except ValueError:
                            delay = 2 ** (attempt + 1)
                        self._blocked_until = time.monotonic() + min(delay, 30)
                        last = UpstreamError("Steam 요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.", 503, "steam_rate_limited")
                        log.warning("steam 429; backing off %.1fs", delay)
                    elif r.status_code in (401, 403):
                        raise UpstreamError("Steam 접근이 거부되었습니다 (API 키 필요 또는 권한 없음).", 502, "steam_forbidden")
                    elif r.status_code >= 500:
                        last = UpstreamError(f"Steam 서버 오류({r.status_code})")
                    else:
                        raise UpstreamError(f"Steam 요청 실패({r.status_code})")
            if attempt < self.s.steam_max_retries:
                await asyncio.sleep(min(0.5 * 2**attempt, 8))
        if isinstance(last, UpstreamError):
            raise last
        raise UpstreamError("Steam에 연결할 수 없습니다. 네트워크 상태를 확인해 주세요.", 504, "steam_timeout")

    # ---- endpoints -------------------------------------------------------
    async def app_details(self, appid: int, lang: str) -> dict | None:
        data = await self.get_json(
            f"{self.s.steam_store_base_url}/api/appdetails",
            {"appids": appid, "l": lang, "cc": "kr"},
        )
        entry = (data or {}).get(str(appid)) or {}
        return entry["data"] if entry.get("success") else None

    async def store_search(self, term: str, lang: str = "koreana") -> list[dict]:
        data = await self.get_json(
            f"{self.s.steam_store_base_url}/api/storesearch/", {"term": term, "l": lang, "cc": "kr"}
        )
        return list((data or {}).get("items") or [])

    async def search_page(self, start: int, count: int, lang: str, sort_by: str | None = "Reviews_DESC",
                          **extra: Any) -> dict:
        """Store listing (games only). extra: filter=popularnew|comingsoon|topsellers, specials=1 ..."""
        return await self.get_json(
            f"{self.s.steam_store_base_url}/search/results/",
            {"query": "", "start": start, "count": count, "category1": 998, "infinite": 1, "json": 1,
             "l": lang, "cc": "kr", **({"sort_by": sort_by} if sort_by else {}), **extra},
        )

    async def reviews(self, appid: int, *, filter: str = "helpful", language: str = "all", review_type: str = "all",
                      purchase_type: str = "all", **params: Any) -> dict:
        """IUserReviewsService/GetAppReviews/v1 (official; works keyless, key not sent).

        Translates friendly names to the API's enum ints and `languages[]` array (see Steamworks docs).
        Note: score totals in query_summary come back only on unfiltered (review_type=all) first pages.
        """
        payload = {
            "appid": appid,
            "filter": REVIEW_FILTER[filter],
            "languages": [language],
            "review_type": REVIEW_TYPE[review_type],
            "purchase_type": PURCHASE_TYPE[purchase_type],
            **{k: v for k, v in params.items() if v is not None},
        }
        data = await self.get_json(
            f"{self.s.steam_api_base_url}/IUserReviewsService/GetAppReviews/v1/",
            {"input_json": json.dumps(payload, separators=(",", ":"))},
        )
        resp = (data or {}).get("response")
        if not isinstance(resp, dict) or "query_summary" not in resp:
            raise UpstreamError("Steam 리뷰 응답 형식이 올바르지 않습니다.")
        return resp

    async def app_list(self, last_appid: int = 0, max_results: int = 50000) -> dict:
        if not self.s.steam_api_key:
            raise UpstreamError("STEAM_API_KEY가 설정되지 않았습니다.", 501, "steam_key_missing")
        data = await self.get_json(
            f"{self.s.steam_api_base_url}/IStoreService/GetAppList/v1/",
            {"key": self.s.steam_api_key, "include_games": "true", "max_results": max_results, "last_appid": last_appid},
        )
        return (data or {}).get("response") or {}
