"""API tests against a mocked Steam transport (no network). Real-Steam checks are in scripts/live_check.py."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.steam.client import SteamClient
from app.steam.parsers import clean_review_text, parse_release_ts, parse_search_html

SEARCH_HTML = """
<a href="https://store.steampowered.com/app/1245620/ELDEN_RING/" data-ds-appid="1245620" data-ds-tagids="[122,21,999]" class="x">
 <span class="title">ELDEN RING</span>
 <div class="search_released responsive_secondrow">Feb 25, 2022</div>
 <span class="search_review_summary positive" data-tooltip-html="Very Positive&lt;br&gt;94% of the 437,411 user reviews for this game are positive."></span>
 <div class="search_price_discount_combined" data-price-final="6480000"><div class="discount_block" data-price-final="6480000" data-discount="20"></div></div>
</a>
<a href="https://store.steampowered.com/app/220/Half_Life_2/" data-ds-appid="220" data-ds-tagids="[19]">
 <span class="title">Half-Life 2</span>
 <div class="search_released responsive_secondrow">2004년 11월 16일</div>
</a>
"""

DETAIL = {"1245620": {"success": True, "data": {
    "type": "game", "name": "엘든 링", "steam_appid": 1245620, "is_free": False,
    "short_description": "<b>짧은</b> 설명", "about_the_game": "<p>본문</p><script>alert(1)</script>",
    "header_image": "https://x/h.jpg", "developers": ["FromSoftware"], "publishers": ["Bandai"],
    "price_overview": {"currency": "KRW", "initial": 6480000, "final": 5184000, "discount_percent": 20},
    "release_date": {"coming_soon": False, "date": "2022년 2월 25일"},
    "genres": [{"id": "1", "description": "액션"}], "platforms": {"windows": True},
    "screenshots": [{"path_full": "https://x/s1.jpg"}], "supported_languages": "한국어<strong>*</strong>, English",
}}}


def make_review(i, lang="english", up=True):
    return {"recommendationid": str(i), "language": lang, "review": f"[h1]Great {i}[/h1] [b]yes[/b]", "voted_up": up,
            "votes_up": 3, "timestamp_created": 1700000000 + i, "timestamp_updated": 1700000000 + i,
            "weighted_vote_score": "0.9", "author": {"steamid": "7656119", "playtime_forever": 600, "playtime_at_review": 300}}


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        url = str(request.url)
        if "appdetails" in url:
            appid = request.url.params["appids"]
            return httpx.Response(200, json=DETAIL if appid == "1245620" else {appid: {"success": False}})
        if "GetAppReviews" in url:
            payload = json.loads(request.url.params["input_json"])
            if payload["appid"] == 500:
                return httpx.Response(429, headers={"Retry-After": "0"})
            n = payload.get("num_per_page", 20)
            return httpx.Response(200, json={"response": {
                "query_summary": {"num_reviews": n, "review_score": 8, "review_score_desc": "Very Positive",
                                  "total_positive": 90, "total_negative": 10, "total_reviews": 100},
                "reviews": [make_review(i, payload["languages"][0] if payload["languages"][0] != "all" else "korea") for i in range(n)],
                "cursor": "AoJ4+/=" if payload.get("cursor", "*") == "*" else payload["cursor"]}})
        if "search/results" in url:
            self.search_params = dict(request.url.params)
            return httpx.Response(200, json={"success": 1, "results_html": SEARCH_HTML, "total_count": 2})
        if "storesearch" in url:
            return httpx.Response(200, json={"total": 0, "items": []})
        if "GetAppList" in url:
            return httpx.Response(200, json={"response": {"apps": []}})
        return httpx.Response(404)


@pytest.fixture
def ctx(tmp_path):
    rec = Recorder()
    s = Settings(database_path=str(tmp_path / "t.db"), steam_min_interval_seconds=0, steam_max_retries=1,
                 admin_token="secret", rate_limit_per_minute=1000, _env_file=None)
    steam = SteamClient(s, transport=httpx.MockTransport(rec))
    with TestClient(create_app(s, steam)) as c:
        yield c, rec, s


def seed(c, s):
    import asyncio
    from app.db import connect
    from app.services import catalog

    async def go():
        db = await connect(s.db_file)
        for r in parse_search_html(SEARCH_HTML):
            await catalog.upsert_listing(db, r, "english")
        await catalog.upsert_listing(db, {**parse_search_html(SEARCH_HTML)[0], "title": "엘든 링"}, "koreana")
        await db.commit()
        await db.close()
    asyncio.run(go())


def test_parsers():
    rows = parse_search_html(SEARCH_HTML)
    assert [r["appid"] for r in rows] == [1245620, 220]
    assert rows[0]["tag_ids"] == [122, 21, 999] and rows[0]["review_pct"] == 94 and rows[0]["review_count"] == 437411
    assert rows[0]["price_final"] == 6480000 and rows[0]["discount_percent"] == 20
    assert rows[1]["release_ts"] == parse_release_ts("2004년 11월 16일")
    assert clean_review_text("[h1]A[/h1][url=http://x]link[/url][img]a.png[/img][list][*]x[/list]") == "Alink\n• x"


def test_health_and_validation(ctx):
    c, _, _ = ctx
    assert c.get("/api/health").json()["status"] == "ok"
    r = c.get("/api/games/abc")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
    assert c.get("/api/games/search?page_size=1000").status_code == 422
    assert c.get("/api/games/1/reviews?language=klingon").status_code == 422
    assert c.get("/api/games/1/reviews?cursor=%3Cscript%3E").status_code == 422


def test_search_korean_english_partial_filters(ctx):
    c, _, s = ctx
    seed(c, s)
    assert c.get("/api/games/search?q=elde").json()["total"] == 1           # partial, english
    assert c.get("/api/games/search?q=엘든").json()["items"][0]["appid"] == 1245620  # korean
    assert c.get("/api/games/search?q=' OR 1=1 --").json()["total"] == 0     # injection-safe
    assert c.get("/api/games/search?q=%22").json()["total"] == 0             # FTS quote safe
    assert c.get("/api/games/search?genre=19").json()["items"][0]["appid"] == 220
    assert c.get("/api/games/search?min_rating=90").json()["total"] == 1
    assert c.get("/api/games/search?sort=newest").json()["items"][0]["appid"] == 1245620
    assert c.get("/api/genres").json()[0]["count"] >= 0


def test_detail_sanitised_persisted_and_cached(ctx):
    c, rec, _ = ctx
    d = c.get("/api/games/1245620").json()
    assert d["name"] == "엘든 링" and "<" not in d["about"] and d["price"]["final"] == 51840
    assert d["review_summary"]["total_reviews"] == 100
    n = len(rec.calls)
    c.get("/api/games/1245620")
    assert len(rec.calls) == n  # served from DB + cache, no new Steam calls
    # now discoverable via local search
    assert c.get("/api/games/search?q=엘든").json()["total"] == 1


def test_unknown_game_404(ctx):
    c, _, _ = ctx
    r = c.get("/api/games/777")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_reviews_params_pagination_and_cache(ctx):
    c, rec, _ = ctx
    r = c.get("/api/games/1245620/reviews?sort=recent&language=koreana&review_type=negative&per_page=3").json()
    payload = json.loads([x for x in rec.calls if "GetAppReviews" in str(x.url)][0].url.params["input_json"])
    assert payload["languages"] == ["koreana"] and payload["filter"] == 1 and payload["review_type"] == 2
    assert len(r["reviews"]) == 3 and r["has_more"] and r["cursor"] == "AoJ4+/="
    assert r["reviews"][0]["text"] == "Great 0 yes"
    n = len(rec.calls)
    r2 = c.get("/api/games/1245620/reviews?sort=recent&language=koreana&review_type=negative&per_page=3").json()
    assert r2["cached"] and len(rec.calls) == n
    c.get("/api/games/1245620/reviews", params={"cursor": "AoJ4+/="})  # cursor round-trips URL-encoded


def test_stats_separates_official_and_sample(ctx):
    c, _, _ = ctx
    s = c.get("/api/games/1245620/review-stats?pages=1").json()
    assert s["official"]["total_reviews"] == 100 and s["sample"]["kind"] == "most_recent" and s["sample"]["size"] == 100


def test_steam_429_maps_to_503(ctx):
    c, _, _ = ctx
    r = c.get("/api/games/500/reviews")
    assert r.status_code == 503 and r.json()["error"]["code"] == "steam_rate_limited"


def test_admin_protected(ctx):
    c, _, _ = ctx
    assert c.post("/api/admin/crawl/applist").status_code == 401
    assert c.post("/api/admin/cache/purge", headers={"X-Admin-Token": "secret"}).status_code == 200


def test_admin_disabled_without_token(tmp_path):
    s = Settings(database_path=str(tmp_path / "t.db"), admin_token="", _env_file=None)
    with TestClient(create_app(s, SteamClient(s, transport=httpx.MockTransport(Recorder())))) as c:
        assert c.post("/api/admin/cache/purge", headers={"X-Admin-Token": ""}).status_code == 404


def test_applist_requires_key(ctx):
    import asyncio
    from app.errors import UpstreamError
    c, _, s = ctx
    st = SteamClient(s, transport=httpx.MockTransport(Recorder()))
    with pytest.raises(UpstreamError) as e:
        asyncio.run(st.app_list())
    assert e.value.code == "steam_key_missing"


def test_rate_limit(tmp_path):
    s = Settings(database_path=str(tmp_path / "t.db"), rate_limit_per_minute=3, _env_file=None)
    with TestClient(create_app(s, SteamClient(s, transport=httpx.MockTransport(Recorder())))) as c:
        codes = [c.get("/api/genres").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_disallowed_steam_url():
    with pytest.raises(Exception):
        Settings(steam_api_base_url="https://evil.example.com", _env_file=None)


def test_home_tabs(ctx):
    c, rec, _ = ctx
    items = c.get("/api/games/home?tab=sale&limit=5").json()
    assert [i["appid"] for i in items] == [1245620, 220]
    assert items[0]["price"]["discount_percent"] == 20 and items[0]["review_pct"] == 94
    assert rec.search_params["specials"] == "1" and rec.search_params["category1"] == "998"
    n = len(rec.calls)
    c.get("/api/games/home?tab=sale")
    assert len(rec.calls) == n  # cached
    assert c.get("/api/games/home?tab=new").status_code == 200
    assert rec.search_params["filter"] == "popularnew"
    assert c.get("/api/games/home?tab=hack").status_code == 422
