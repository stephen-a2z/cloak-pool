from __future__ import annotations
import asyncio
import secrets
import uuid
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import HTTPException

from app.config import cfg
from app.database import get_db
from app.mapping import get_or_create_profile, derive_fingerprint_seed
from app.models import AcquireRequest, AcquireResponse
from app.nodes import NodeRegistry, NodeState
from app import storage
from app.engines import BrowserEngine, ProfileConfig
from app.engines.cloakbrowser import CloakBrowserEngine


class PoolManager:
    def __init__(self, registry: NodeRegistry, engine: BrowserEngine | None = None):
        self.registry = registry
        self.engine: BrowserEngine = engine or CloakBrowserEngine()

    async def _active_session_count(self) -> int:
        db = get_db()
        rows = await db.execute_fetchall("SELECT COUNT(*) FROM sessions WHERE status = 'active'")
        return rows[0][0]

    async def _get_active_session_for_profile(self, profile_id: str) -> dict | None:
        db = get_db()
        rows = await db.execute_fetchall(
            "SELECT * FROM sessions WHERE profile_id = ? AND status = 'active'", (profile_id,)
        )
        return dict(rows[0]) if rows else None

    async def acquire(self, req: AcquireRequest) -> AcquireResponse:
        # 1. Get or create profile mapping
        profile_id, is_new = await get_or_create_profile(req.consumer_id)
        fingerprint_seed = derive_fingerprint_seed(req.consumer_id)

        # 2. Check profile not already locked
        existing = await self._get_active_session_for_profile(profile_id)
        if existing:
            raise HTTPException(409, "Profile is already in use by an active session")

        # 3. Check global concurrency
        count = await self._active_session_count()
        if count >= cfg.MAX_GLOBAL_SESSIONS:
            raise HTTPException(429, "Global session limit reached")

        # 4. Select node
        node = self.registry.select_node(profile_id)
        if not node:
            raise HTTPException(503, "No available nodes")

        # 5. Build profile config
        defaults = await self._get_defaults()
        profile_cfg = self._build_profile_config(req, fingerprint_seed, defaults)

        try:
            node_url = node.url

            # 6. Create or ensure profile exists on node
            if is_new:
                engine_id = await self.engine.create_profile(node_url, profile_cfg)
                if engine_id and engine_id != profile_id:
                    profile_id = engine_id
                    await self._update_mapping(req.consumer_id, profile_id)
            else:
                exists = await self.engine.profile_exists(node_url, profile_id)
                if not exists:
                    engine_id = await self.engine.create_profile(node_url, profile_cfg)
                    if engine_id and engine_id != profile_id:
                        profile_id = engine_id
                        await self._update_mapping(req.consumer_id, profile_id)
                else:
                    update_fields = self._build_update_fields(req)
                    await self.engine.update_profile(node_url, profile_id, update_fields)

            # 7. Pull profile data from master to worker
            if storage.profile_exists(profile_id):
                worker_url = self._worker_url(node_url)
                local_dir = f"{cfg.LOCAL_PROFILES_DIR}/{profile_id}"
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.post(
                        f"{worker_url}/internal/sync/pull",
                        json={"profile_id": profile_id, "master_url": cfg.MASTER_URL, "local_dir": local_dir},
                    )
                    if r.status_code != 200:
                        raise HTTPException(502, f"Failed to pull profile data to worker: {r.text}")

            # 8. Launch browser
            await self.engine.launch(node_url, profile_id)

            # 9. Wait for browser to be ready
            await self.engine.wait_ready(node_url, profile_id, timeout=15)

        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(502, f"Node communication error: {exc}")

        # 10. Generate session + view token
        session_id = str(uuid.uuid4())
        view_token = secrets.token_urlsafe(32)
        ttl = min(req.ttl or cfg.TTL_DEFAULT, cfg.TTL_MAX)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

        # 11. Record session
        db = get_db()
        await db.execute(
            "INSERT INTO sessions (session_id, consumer_id, profile_id, owner, node_id, node_url, view_token, status, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)",
            (session_id, req.consumer_id, profile_id, req.owner, node.node_id, node.url, view_token, expires_at.isoformat()),
        )
        await db.commit()

        # 12. Update node state
        self.registry.increment_sessions(node.node_id)
        self.registry.update_affinity(node.node_id, profile_id)

        # 13. Build response
        cdp_url = self.engine.get_cdp_url(node.url, profile_id)
        master_host = cfg.MASTER_URL.replace("http://", "")
        view_url = f"http://{master_host}/view/{session_id}?token={view_token}"

        return AcquireResponse(
            session_id=session_id,
            consumer_id=req.consumer_id,
            profile_id=profile_id,
            cdp_url=cdp_url,
            view_url=view_url,
            node=node.node_id,
            expires_at=expires_at.isoformat(),
        )

    async def release(self, session_id: str, owner: str) -> None:
        db = get_db()
        rows = await db.execute_fetchall(
            "SELECT * FROM sessions WHERE session_id = ? AND status = 'active'", (session_id,)
        )
        if not rows:
            raise HTTPException(404, "Session not found or already released")
        session = dict(rows[0])
        if session["owner"] != owner:
            raise HTTPException(403, "Not the session owner")

        node_url = session["node_url"]
        profile_id = session["profile_id"]

        try:
            # Stop browser via engine
            await self.engine.stop(node_url, profile_id)
            # Push profile data back to master
            worker_url = self._worker_url(node_url)
            local_dir = f"{cfg.LOCAL_PROFILES_DIR}/{profile_id}"
            async with httpx.AsyncClient(timeout=60) as client:
                await client.post(
                    f"{worker_url}/internal/sync/push",
                    json={"profile_id": profile_id, "master_url": cfg.MASTER_URL, "local_dir": local_dir},
                )
        except HTTPException:
            raise
        except Exception:
            pass  # Best effort — still mark released

        await db.execute("UPDATE sessions SET status = 'released' WHERE session_id = ?", (session_id,))
        await db.commit()
        self.registry.decrement_sessions(session["node_id"])
        self.registry.update_affinity(session["node_id"], profile_id)

    async def renew(self, session_id: str, owner: str) -> str:
        db = get_db()
        rows = await db.execute_fetchall(
            "SELECT * FROM sessions WHERE session_id = ? AND status = 'active'", (session_id,)
        )
        if not rows:
            raise HTTPException(404, "Session not found or not active")
        session = dict(rows[0])
        if session["owner"] != owner:
            raise HTTPException(403, "Not the session owner")

        new_expires = datetime.now(timezone.utc) + timedelta(seconds=cfg.TTL_DEFAULT)
        max_expires = datetime.now(timezone.utc) + timedelta(seconds=cfg.TTL_MAX)
        if new_expires > max_expires:
            new_expires = max_expires

        await db.execute("UPDATE sessions SET expires_at = ? WHERE session_id = ?", (new_expires.isoformat(), session_id))
        await db.commit()
        return new_expires.isoformat()

    async def reset(self, consumer_id: str) -> None:
        from app.mapping import reset_consumer

        # Release active session if any
        db = get_db()
        rows = await db.execute_fetchall(
            "SELECT session_id, owner FROM sessions WHERE consumer_id = ? AND status = 'active'", (consumer_id,)
        )
        if rows:
            session = dict(rows[0])
            try:
                await self.release(session["session_id"], session["owner"])
            except Exception:
                await db.execute("UPDATE sessions SET status = 'released' WHERE session_id = ?", (session["session_id"],))
                await db.commit()

        # Delete mapping and storage
        profile_id = await reset_consumer(consumer_id)
        if profile_id:
            storage.delete_profile_data(profile_id)
            # Delete from all nodes via engine (best effort)
            for node in self.registry.all_nodes():
                try:
                    await self.engine.delete_profile(node.url, profile_id)
                except Exception:
                    pass

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _get_defaults(self) -> dict:
        dbc = get_db()
        rows = await dbc.execute_fetchall("SELECT * FROM global_defaults WHERE id = 1")
        if not rows:
            return {}
        return {k: v for k, v in dict(rows[0]).items() if k not in ("id", "updated_at", "notes") and v is not None}

    async def _update_mapping(self, consumer_id: str, profile_id: str) -> None:
        db = get_db()
        await db.execute(
            "UPDATE consumer_profiles SET profile_id = ? WHERE consumer_id = ?",
            (profile_id, consumer_id),
        )
        await db.commit()

    def _build_profile_config(self, req: AcquireRequest, seed: int, defaults: dict = None) -> ProfileConfig:
        d = defaults or {}
        def pick(field):
            val = getattr(req, field, None)
            return val if val is not None else d.get(field)

        return ProfileConfig(
            name=req.consumer_id,
            fingerprint_seed=seed,
            proxy=pick("proxy"),
            timezone=pick("timezone"),
            locale=pick("locale"),
            platform=pick("platform") or "windows",
            user_agent=pick("user_agent"),
            screen_width=pick("screen_width") or 1920,
            screen_height=pick("screen_height") or 1080,
            launch_args=["--disk-cache-size=1048576", "--media-cache-size=1048576"],
        )

    def _build_update_fields(self, req: AcquireRequest) -> dict:
        fields = {}
        for field in ("proxy", "timezone", "locale", "platform", "user_agent", "screen_width", "screen_height"):
            val = getattr(req, field, None)
            if val is not None:
                fields[field] = val
        return fields

    def _worker_url(self, node_url: str) -> str:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(node_url)
        return urlunparse(parsed._replace(netloc=f"{parsed.hostname}:{cfg.WORKER_PORT}"))
