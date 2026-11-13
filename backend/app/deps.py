import hmac
from typing import AsyncIterator

import aiosqlite
from fastapi import Depends, Header, Request

from .config import Settings, get_settings
from .db import connect
from .errors import AppError
from .ratelimit import client_ip
from .steam.client import SteamClient


def get_cfg(request: Request) -> Settings:
    return request.app.state.settings


async def get_db(request: Request) -> AsyncIterator[aiosqlite.Connection]:
    db = await connect(request.app.state.settings.db_file)
    try:
        yield db
    finally:
        await db.close()


def get_steam(request: Request) -> SteamClient:
    return request.app.state.steam


async def rate_limit(request: Request) -> None:
    request.app.state.limiter.check(client_ip(request))


async def require_admin(x_admin_token: str | None = Header(default=None), s: Settings = Depends(get_cfg)) -> None:
    if not s.admin_token:
        raise AppError(404, "not_found", "관리 기능이 비활성화되어 있습니다.")
    if not x_admin_token or not hmac.compare_digest(x_admin_token, s.admin_token):
        raise AppError(401, "unauthorized", "관리자 토큰이 올바르지 않습니다.")
