"""Two-level TTL cache: process memory in front of the SQLite kv_cache table."""
import json
import time
from typing import Any

import aiosqlite

_mem: dict[str, tuple[float, Any]] = {}


async def cache_get(db: aiosqlite.Connection, key: str) -> Any | None:
    now = time.time()
    hit = _mem.get(key)
    if hit and hit[0] > now:
        return hit[1]
    async with db.execute("SELECT value, expires_at FROM kv_cache WHERE key=?", (key,)) as c:
        row = await c.fetchone()
    if row and row["expires_at"] > now:
        val = json.loads(row["value"])
        _mem[key] = (row["expires_at"], val)
        return val
    return None


async def cache_set(db: aiosqlite.Connection, key: str, value: Any, ttl: int) -> None:
    exp = time.time() + ttl
    _mem[key] = (exp, value)
    await db.execute(
        "INSERT INTO kv_cache(key,value,expires_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, expires_at=excluded.expires_at",
        (key, json.dumps(value, ensure_ascii=False), int(exp)),
    )
    await db.commit()


async def cache_purge(db: aiosqlite.Connection) -> int:
    _mem.clear()
    cur = await db.execute("DELETE FROM kv_cache WHERE expires_at < ?", (int(time.time()),))
    await db.commit()
    return cur.rowcount
