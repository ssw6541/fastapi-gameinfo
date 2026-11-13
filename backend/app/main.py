import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .api import games as games_api
from .api import system as system_api
from .config import get_settings
from .db import run_migrations
from .errors import install_error_handlers
from .ratelimit import RateLimiter
from .steam.client import SteamClient


class _RedactKey(logging.Filter):
    """Never let the Steam API key reach logs (httpx logs request URLs)."""

    def filter(self, record: logging.LogRecord) -> bool:
        key = get_settings().steam_api_key
        if key:
            record.msg = str(record.msg).replace(key, "***")
            if record.args:
                record.args = tuple(str(a).replace(key, "***") if isinstance(a, str) else a for a in (record.args if isinstance(record.args, tuple) else (record.args,)))
        return True


def create_app(settings=None, steam: SteamClient | None = None) -> FastAPI:
    s = settings or get_settings()
    logging.basicConfig(level=s.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for h in logging.getLogger().handlers:
        h.addFilter(_RedactKey())
    logging.getLogger("httpx").setLevel(logging.WARNING)  # request URLs may include secrets

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        run_migrations(s.db_file)
        app.state.settings = s
        app.state.steam = steam or SteamClient(s)
        app.state.limiter = RateLimiter(s.rate_limit_per_minute)
        app.state.jobs = set()
        yield
        await app.state.steam.aclose()

    app = FastAPI(
        title="Steam GameInfo API", version="1.0.0", lifespan=lifespan,
        docs_url=None if s.is_production else "/docs", redoc_url=None if s.is_production else "/redoc",
        openapi_url=None if s.is_production else "/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_origin_list, allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Admin-Token"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        return resp

    install_error_handlers(app)
    app.include_router(system_api.router)
    app.include_router(system_api.admin)
    app.include_router(games_api.router)
    return app


app = create_app()
