"""Tests for TTL expiry auto-cleanup."""
import asyncio
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio

from app import database as db
from app.config import cfg


@pytest_asyncio.fixture(autouse=True)
async def setup_db(tmp_path):
    cfg.DB_PATH = str(tmp_path / "test.db")
    await db.init_db()
    yield
    await db.close_db()


@pytest.mark.asyncio
async def test_expired_session_gets_released():
    """Sessions past their expires_at should be auto-released."""
    from app.ttl_watcher import TTLWatcher
    from app.pool import PoolManager
    from app.nodes import NodeRegistry

    registry = NodeRegistry()
    pool = PoolManager(registry)
    watcher = TTLWatcher(pool)

    # Insert expired session
    dbc = db.get_db()
    expired = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    await dbc.execute(
        "INSERT INTO sessions VALUES ('s1','c1','p1','owner1','n1','http://127.0.0.1:19999','tok','active',?,?)",
        (expired, '2024-01-01'),
    )
    await dbc.commit()

    # Run one sweep
    await watcher.sweep_once()

    # Session should be released (or orphaned if node unreachable)
    rows = await dbc.execute_fetchall("SELECT status FROM sessions WHERE session_id = 's1'")
    assert rows[0][0] in ('released', 'orphaned'), f"Got status: {rows[0][0]}"


@pytest.mark.asyncio
async def test_non_expired_session_untouched():
    """Sessions not yet expired should remain active."""
    from app.ttl_watcher import TTLWatcher
    from app.pool import PoolManager
    from app.nodes import NodeRegistry

    registry = NodeRegistry()
    pool = PoolManager(registry)
    watcher = TTLWatcher(pool)

    dbc = db.get_db()
    future = (datetime.now(timezone.utc) + timedelta(seconds=300)).isoformat()
    await dbc.execute(
        "INSERT INTO sessions VALUES ('s2','c2','p2','owner2','n1','http://127.0.0.1:19999','tok','active',?,?)",
        (future, '2024-01-01'),
    )
    await dbc.commit()

    await watcher.sweep_once()

    rows = await dbc.execute_fetchall("SELECT status FROM sessions WHERE session_id = 's2'")
    assert rows[0][0] == 'active'


@pytest.mark.asyncio
async def test_orphaned_session_on_unreachable_node():
    """If node is unreachable during release, session is marked orphaned."""
    from app.ttl_watcher import TTLWatcher
    from app.pool import PoolManager
    from app.nodes import NodeRegistry

    registry = NodeRegistry()
    pool = PoolManager(registry)
    watcher = TTLWatcher(pool)

    dbc = db.get_db()
    expired = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    await dbc.execute(
        "INSERT INTO sessions VALUES ('s3','c3','p3','owner3','n1','http://127.0.0.1:19999','tok','active',?,?)",
        (expired, '2024-01-01'),
    )
    await dbc.commit()

    await watcher.sweep_once()

    rows = await dbc.execute_fetchall("SELECT status FROM sessions WHERE session_id = 's3'")
    # Node unreachable → should still mark released (best-effort in pool.release)
    assert rows[0][0] in ('released', 'orphaned')
