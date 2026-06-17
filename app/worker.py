"""Worker process: heartbeat loop + sync endpoints."""
from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException

from app.config import cfg
from app.models import SyncRequest
from app.sync import pull_profile, push_profile

logger = logging.getLogger("browser-pool.worker")


async def _heartbeat_loop():
    """Send heartbeat to master every 10s."""
    while True:
        try:
            # Collect system metrics
            import shutil
            cpu = memory = disk = 0.0
            try:
                import os
                # CPU: load average / cpu count (approximate %)
                load = os.getloadavg()[0]
                cpu_count = os.cpu_count() or 1
                cpu = min(round(load / cpu_count * 100, 1), 100)
                # Memory: read from /proc/meminfo (Linux)
                with open('/proc/meminfo') as f:
                    lines = f.readlines()
                    total = int(lines[0].split()[1])
                    avail = int(lines[2].split()[1])
                    memory = round((1 - avail / total) * 100, 1)
                # Disk
                usage = shutil.disk_usage('/')
                disk = round(usage.used / usage.total * 100, 1)
            except Exception:
                pass

            async with httpx.AsyncClient(timeout=5) as client:
                try:
                    r = await client.get(f"{cfg.NODE_ADVERTISE_URL}/api/status")
                    current = r.json().get("running_count", 0) if r.status_code == 200 else 0
                except Exception:
                    current = 0

                await client.post(
                    f"{cfg.MASTER_URL}/api/nodes/heartbeat",
                    json={
                        "node_id": cfg.NODE_ID,
                        "url": cfg.NODE_ADVERTISE_URL,
                        "max_sessions": cfg.MAX_NODE_SESSIONS,
                        "current_sessions": current,
                        "cpu_percent": cpu,
                        "memory_percent": memory,
                        "disk_percent": disk,
                    },
                )
        except Exception as exc:
            logger.warning("Heartbeat failed: %s", exc)
        await asyncio.sleep(10)


@asynccontextmanager
async def worker_lifespan(app: FastAPI):
    task = asyncio.create_task(_heartbeat_loop())
    logger.info("Worker started: node_id=%s, master=%s", cfg.NODE_ID, cfg.MASTER_URL)
    yield
    task.cancel()


worker_app = FastAPI(title="Browser Pool Worker", lifespan=worker_lifespan)


@worker_app.post("/internal/sync/pull")
async def sync_pull(req: SyncRequest):
    try:
        local_dir = Path(req.local_dir)
        ok = await pull_profile(req.master_url, req.profile_id, local_dir)
        return {"ok": True, "had_data": ok}
    except Exception as exc:
        raise HTTPException(502, f"Pull failed: {exc}")


@worker_app.post("/internal/sync/push")
async def sync_push(req: SyncRequest):
    try:
        local_dir = Path(req.local_dir)
        await push_profile(req.master_url, req.profile_id, local_dir)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(502, f"Push failed: {exc}")


@worker_app.get("/health")
async def health():
    return {"ok": True, "role": "worker", "node_id": cfg.NODE_ID}
