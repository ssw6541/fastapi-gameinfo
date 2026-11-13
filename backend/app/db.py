"""SQLite access (aiosqlite) + tiny versioned SQL migration runner."""
import logging
import sqlite3
from pathlib import Path

import aiosqlite

from .config import BASE_DIR, get_settings

log = logging.getLogger("app.db")
MIGRATIONS_DIR = BASE_DIR / "migrations"


def run_migrations(db_file: Path) -> list[str]:
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file)
    applied: list[str] = []
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at INTEGER)")
        done = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}
        for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if f.name in done:
                continue
            conn.executescript(f.read_text(encoding="utf8"))
            conn.execute("INSERT INTO schema_migrations VALUES (?, strftime('%s','now'))", (f.name,))
            conn.commit()
            applied.append(f.name)
            log.info("applied migration %s", f.name)
    finally:
        conn.close()
    return applied


async def connect(path: Path | None = None) -> aiosqlite.Connection:
    db = await aiosqlite.connect(path or get_settings().db_file)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    await db.execute("PRAGMA synchronous=NORMAL")
    return db
