from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    database_path: str = "data/gameinfo.db"

    steam_api_key: str = ""
    steam_api_base_url: str = "https://api.steampowered.com"
    steam_store_base_url: str = "https://store.steampowered.com"
    steam_request_timeout: float = 15.0
    steam_max_retries: int = 3
    steam_max_concurrency: int = 4
    steam_min_interval_seconds: float = 0.25

    cache_ttl_seconds: int = 300
    detail_ttl_seconds: int = 86400
    rate_limit_per_minute: int = 120
    admin_token: str = ""

    # Steam login (OpenID 2.0). public_base_url = the origin users see (Vercel domain in prod, Vite in dev).
    public_base_url: str = "http://localhost:5173"
    session_secret: str = ""
    session_ttl_days: int = 14
    steam_community_base_url: str = "https://steamcommunity.com"

    @field_validator("steam_api_base_url", "steam_store_base_url", "steam_community_base_url")
    @classmethod
    def _only_steam_hosts(cls, v: str) -> str:
        # Outbound calls may only go to Steam hosts (guards against SSRF-style misconfiguration).
        p = urlparse(v)
        host = p.hostname or ""
        if p.scheme not in ("https", "http") or not (
            host.endswith("steampowered.com") or host.endswith("steamcommunity.com") or host in ("localhost", "127.0.0.1")
        ):
            raise ValueError(f"disallowed Steam base URL: {v}")
        return v.rstrip("/")

    @property
    def public_origin(self) -> str:
        return self.public_base_url.rstrip("/")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def db_file(self) -> Path:
        p = Path(self.database_path)
        return p if p.is_absolute() else BASE_DIR / p

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
