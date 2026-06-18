from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone

from app.database import get_db

logger = logging.getLogger("browser-pool.ttl")


class TTLWatcher:
    def __init__(self, pool_manager):
        self.pool = pool_manager
        self._sweeping = False

    async def sweep_once(self) -> None:
        if self._sweeping:
            return
        self._sweeping = True
        try:
            db = get_db()
            now = datetime.now(timezone.utc).isoformat()
            rows = await db.execute_fetchall(
                "SELECT session_id, owner FROM sessions WHERE status = 'active' AND expires_at < ?",
                (now,),
            )
            for row in rows:
                session_id, owner = row[0], row[1]
                try:
                    await self.pool.release(session_id, owner)
                except Exception as exc:
                    logger.warning("TTL release failed for %s: %s", session_id, exc)
                    await db.execute(
                        "UPDATE sessions SET status = 'orphaned' WHERE session_id = ? AND status = 'active'",
                        (session_id,),
                    )
                    await db.commit()
        finally:
            self._sweeping = False

    async def run(self, interval: float = 5.0) -> None:
        while True:
            try:
                await self.sweep_once()
            except Exception as exc:
                logger.error("TTL sweep error: %s", exc)
            await asyncio.sleep(interval)
