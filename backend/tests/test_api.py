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
        if "openid/login" in url:
            self.openid_body = request.content.decode()
            ok = "true" if getattr(self, "openid_ok", True) else "false"
            return httpx.Response(200, text=f"ns:http://specs.openid.net/auth/2.0\nis_valid:{ok}\n")
        if "steamcommunity.com/profiles" in url:
            return httpx.Response(200, text="<profile><steamID><![CDATA[Tester]]></steamID><avatarFull><![CDATA[https://avatars.example/a.jpg]]></avatarFull></profile>")
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


SID = "76561198000000001"


def _cb(next_="/game/1", **over):
    q = {"openid.ns": "http://specs.openid.net/auth/2.0", "openid.mode": "id_res",
         "openid.return_to": "http://localhost:5173/api/auth/steam/callback?next=%2Fgame%2F1",
         "openid.claimed_id": f"https://steamcommunity.com/openid/id/{SID}",
         "openid.identity": f"https://steamcommunity.com/openid/id/{SID}", "openid.sig": "x", "next": next_}
    q.update(over)
    return q


def test_login_redirect_and_open_redirect_guard(ctx):
    c, _, _ = ctx
    r = c.get("/api/auth/steam/login?next=//evil.com", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("https://steamcommunity.com/openid/login?")
    assert "evil.com" not in r.headers["location"] and "next%3D%252F" in r.headers["location"]


def test_callback_success_sets_signed_cookie_and_me(ctx):
    c, rec, _ = ctx
    r = c.get("/api/auth/steam/callback", params=_cb(), follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "http://localhost:5173/game/1"
    assert "check_authentication" in rec.openid_body and "HttpOnly" in r.headers["set-cookie"]
    me = c.get("/api/auth/me").json()
    assert me["logged_in"] and me["steamid"] == SID and me["name"] == "Tester"
    assert c.post("/api/auth/logout").json()["logged_in"] is False
    c.cookies.clear()
    assert c.get("/api/auth/me").json() == {"logged_in": False}


def test_callback_rejects_bad_assertions(ctx):
    c, rec, _ = ctx
    for over in ({"openid.claimed_id": "https://evil.com/openid/id/" + SID}, {"openid.mode": "cancel"},
                 {"openid.return_to": "http://evil.com/api/auth/steam/callback"},
                 {"openid.identity": "https://steamcommunity.com/openid/id/76561198000000002"}):
        r = c.get("/api/auth/steam/callback", params=_cb(**over), follow_redirects=False)
        assert "login=failed" in r.headers["location"] and "set-cookie" not in r.headers
    rec.openid_ok = False  # Steam says the assertion is invalid
    r = c.get("/api/auth/steam/callback", params=_cb(), follow_redirects=False)
    assert "login=failed" in r.headers["location"] and "set-cookie" not in r.headers


def test_forged_and_expired_sessions(ctx):
    from app.api.auth import read_session, sign_session
    c, _, s = ctx
    tok = sign_session(s, SID)
    assert read_session(s, tok) == SID
    assert read_session(s, tok[:-2] + "00") is None
    assert read_session(s, sign_session(s, SID, now=1)) is None  # expired
    c.cookies.set("gl_session", "e30=.deadbeef")
    assert c.get("/api/auth/me").json() == {"logged_in": False}


def test_home_genre(ctx):
    c, rec, _ = ctx
    assert c.get("/api/games/home?tab=new&genre=122").status_code == 200
    assert rec.search_params["tags"] == "122"
    assert c.get("/api/games/home?tab=new&genre=999999").status_code == 422



def test_rate_limit_uses_forwarded_ip_only_when_trusted(tmp_path):
    for trust, expected in ((True, [200, 200, 200, 200]), (False, [200, 200, 429, 429])):
        s = Settings(database_path=str(tmp_path / f"t{trust}.db"), rate_limit_per_minute=2, trust_proxy=trust, _env_file=None)
        with TestClient(create_app(s, SteamClient(s, transport=httpx.MockTransport(Recorder())))) as c:
            codes = [c.get("/api/genres", headers={"x-forwarded-for": f"1.2.3.{i % 2 + 1}"}).status_code for i in range(4)]
        assert codes == expected, (trust, codes)
