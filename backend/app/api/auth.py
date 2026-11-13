"""Steam sign-in via OpenID 2.0 (the official "Sign in through Steam" flow; no password ever touches this app).

Session = HttpOnly, HMAC-signed cookie holding only the SteamID. Name/avatar come from the public profile feed.
"""
import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from typing import Annotated
from urllib.parse import quote, urlencode

import aiosqlite
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse

from ..cache import cache_get, cache_set
from ..config import Settings
from ..deps import get_cfg, get_db, get_steam, rate_limit
from ..errors import AppError
from ..steam.client import SteamClient

log = logging.getLogger("app.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"], dependencies=[Depends(rate_limit)])

COOKIE = "gl_session"
OPENID_NS = "http://specs.openid.net/auth/2.0"
CLAIMED = re.compile(r"^https://steamcommunity\.com/openid/id/(\d{17})$")
_dev_secret = secrets.token_bytes(32)  # used only when SESSION_SECRET is unset (sessions reset on restart)


def _key(s: Settings) -> bytes:
    return s.session_secret.encode() if s.session_secret else _dev_secret


def sign_session(s: Settings, steamid: str, now: float | None = None) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"sid": steamid, "exp": int((now or time.time()) + s.session_ttl_days * 86400)}).encode()).decode()
    sig = hmac.new(_key(s), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def read_session(s: Settings, token: str | None, now: float | None = None) -> str | None:
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, hmac.new(_key(s), payload.encode(), hashlib.sha256).hexdigest()):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
    except (ValueError, json.JSONDecodeError):
        return None
    if data.get("exp", 0) < (now or time.time()) or not re.fullmatch(r"\d{17}", str(data.get("sid", ""))):
        return None
    return data["sid"]


def safe_next(nxt: str | None) -> str:
    """Only same-site relative paths (prevents open redirects)."""
    if nxt and nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt and len(nxt) < 300:
        return nxt
    return "/"


@router.get("/steam/login", summary="Steam 로그인 시작 (Steam OpenID로 이동)")
async def steam_login(s: Annotated[Settings, Depends(get_cfg)], next: str = "/"):
    base = s.public_origin
    return_to = f"{base}/api/auth/steam/callback?next={quote(safe_next(next), safe='')}"
    q = urlencode({
        "openid.ns": OPENID_NS, "openid.mode": "checkid_setup", "openid.return_to": return_to, "openid.realm": base,
        "openid.identity": f"{OPENID_NS}/identifier_select", "openid.claimed_id": f"{OPENID_NS}/identifier_select",
    })
    return RedirectResponse(f"{s.steam_community_base_url}/openid/login?{q}", status_code=302)


@router.get("/steam/callback", include_in_schema=False)
async def steam_callback(request: Request, s: Annotated[Settings, Depends(get_cfg)], steam: Annotated[SteamClient, Depends(get_steam)]):
    p = dict(request.query_params)
    nxt = safe_next(p.get("next"))
    fail = RedirectResponse(f"{s.public_origin}{nxt}{'&' if '?' in nxt else '?'}login=failed", status_code=302)
    if p.get("openid.mode") != "id_res" or not str(p.get("openid.return_to", "")).startswith(f"{s.public_origin}/api/auth/steam/callback"):
        return fail
    m = CLAIMED.match(p.get("openid.claimed_id", ""))
    if not m or p.get("openid.identity") != p.get("openid.claimed_id"):
        return fail
    openid = {k: v for k, v in p.items() if k.startswith("openid.")}
    if not await steam.openid_check(openid):
        log.warning("steam openid verification failed")
        return fail
    resp = RedirectResponse(f"{s.public_origin}{nxt}", status_code=302)
    resp.set_cookie(COOKIE, sign_session(s, m[1]), max_age=s.session_ttl_days * 86400, httponly=True,
                    samesite="lax", secure=s.public_origin.startswith("https://"), path="/")
    return resp


@router.get("/me", summary="현재 로그인 사용자")
async def me(request: Request, response: Response, s: Annotated[Settings, Depends(get_cfg)],
             steam: Annotated[SteamClient, Depends(get_steam)], db: Annotated[aiosqlite.Connection, Depends(get_db)]):
    response.headers["Cache-Control"] = "no-store"
    sid = read_session(s, request.cookies.get(COOKIE))
    if not sid:
        return {"logged_in": False}
    key = f"profile:{sid}"
    prof = await cache_get(db, key)
    if prof is None:
        prof = await steam.community_profile(sid) or {"name": None, "avatar": None}
        await cache_set(db, key, prof, 3600)
    return {"logged_in": True, "steamid": sid, "name": prof["name"], "avatar": prof["avatar"],
            "profile_url": f"https://steamcommunity.com/profiles/{sid}"}


@router.post("/logout", summary="로그아웃")
async def logout(response: Response, s: Annotated[Settings, Depends(get_cfg)]):
    response.delete_cookie(COOKIE, path="/", samesite="lax", secure=s.public_origin.startswith("https://"), httponly=True)
    return {"logged_in": False}
