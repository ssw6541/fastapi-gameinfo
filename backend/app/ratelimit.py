"""Small in-process sliding-window rate limiter keyed by client IP (per-minute)."""
import time
from collections import defaultdict, deque

from fastapi import Request

from .errors import AppError


class RateLimiter:
    def __init__(self, limit_per_minute: int):
        self.limit = limit_per_minute
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        q = self.hits[key]
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= self.limit:
            raise AppError(429, "rate_limited", "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.")
        q.append(now)
        if len(self.hits) > 10000:  # bound memory
            for k in [k for k, v in self.hits.items() if not v]:
                self.hits.pop(k, None)


def client_ip(request: Request) -> str:
    if request.app.state.settings.trust_proxy:
        fwd = request.headers.get("x-forwarded-for", "")
        first = fwd.split(",")[0].strip()
        if first and len(first) <= 45:
            return first
    return request.client.host if request.client else "unknown"
