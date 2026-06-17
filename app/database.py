from __future__ import annotations
import aiosqlite
from pathlib import Path
from app.config import cfg

_db: aiosqlite.Connection | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS consumer_profiles (
    consumer_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    consumer_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    owner TEXT NOT NULL,
    node_id TEXT NOT NULL,
    node_url TEXT NOT NULL,
    view_token TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS global_defaults (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    proxy TEXT,
    timezone TEXT,
    locale TEXT,
    platform TEXT DEFAULT 'windows',
    user_agent TEXT,
    screen_width INTEGER DEFAULT 1920,
    screen_height INTEGER DEFAULT 1080,
    notes TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO global_defaults (id) VALUES (1);
"""


async def init_db() -> None:
    global _db
    Path(cfg.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(cfg.DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(_SCHEMA)
    await _db.commit()


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None


def get_db() -> aiosqlite.Connection:
    assert _db is not None, "Database not initialized"
    return _db
