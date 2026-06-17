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


class PoolManager:
    def __init__(self, registry: NodeRegistry):
        self.registry = registry

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

        # 5. Create or update profile on CloakBrowser-Manager
        cbm_url = node.url
        profile_config = self._build_profile_config(req, profile_id, fingerprint_seed)

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                if is_new:
                    r = await client.post(f"{cbm_url}/api/profiles", json=profile_config)
                    if r.status_code not in (200, 201):
                        raise HTTPException(502, f"Failed to create profile on node: {r.text}")
                else:
                    update_fields = self._build_update_fields(req)
                    if update_fields:
                        r = await client.put(f"{cbm_url}/api/profiles/{profile_id}", json=update_fields)
                        if r.status_code not in (200, 201):
                            raise HTTPException(502, f"Failed to update profile on node: {r.text}")

                # 6. Pull profile data from master to worker
                if storage.profile_exists(profile_id):
                    worker_url = self._worker_url(cbm_url)
                    r = await client.post(
                        f"{worker_url}/internal/sync/pull",
                        json={"profile_id": profile_id, "master_url": cfg.MASTER_URL, "local_dir": f"/data/cbm-profiles/{profile_id}"},
                        timeout=30,
                    )
                    if r.status_code != 200:
                        raise HTTPException(502, f"Failed to pull profile data to worker: {r.text}")

                # 7. Launch browser
                r = await client.post(f"{cbm_url}/api/profiles/{profile_id}/launch")
                if r.status_code not in (200, 201):
                    raise HTTPException(502, f"Failed to launch browser: {r.text}")

                # 8. Wait for browser to be ready
                for _ in range(30):
                    r = await client.get(f"{cbm_url}/api/profiles/{profile_id}/status")
                    if r.status_code == 200 and r.json().get("status") == "running":
                        break
                    await asyncio.sleep(0.5)
                else:
                    raise HTTPException(504, "Browser did not start in time")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(502, f"Node communication error: {exc}")

        # 9. Generate session + view token
        session_id = str(uuid.uuid4())
        view_token = secrets.token_urlsafe(32)
        ttl = min(req.ttl or cfg.TTL_DEFAULT, cfg.TTL_MAX)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

        # 10. Record session
        db = get_db()
        await db.execute(
            "INSERT INTO sessions (session_id, consumer_id, profile_id, owner, node_id, node_url, view_token, status, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)",
            (session_id, req.consumer_id, profile_id, req.owner, node.node_id, node.url, view_token, expires_at.isoformat()),
        )
        await db.commit()

        # 11. Update node state
        self.registry.increment_sessions(node.node_id)
        self.registry.update_affinity(node.node_id, profile_id)

        # 12. Build response
        cdp_url = f"ws://{node.url.replace('http://', '')}/api/profiles/{profile_id}/cdp"
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

    def _build_profile_config(self, req: AcquireRequest, profile_id: str, seed: int) -> dict:
        config = {
            "name": req.consumer_id,
            "fingerprint_seed": seed,
            "launch_args": ["--disk-cache-size=1048576", "--media-cache-size=1048576"],
        }
        if req.proxy:
            config["proxy"] = req.proxy
        if req.timezone:
            config["timezone"] = req.timezone
        if req.locale:
            config["locale"] = req.locale
        if req.platform:
            config["platform"] = req.platform
        if req.user_agent:
            config["user_agent"] = req.user_agent
        if req.screen_width:
            config["screen_width"] = req.screen_width
        if req.screen_height:
            config["screen_height"] = req.screen_height
        return config

    def _build_update_fields(self, req: AcquireRequest) -> dict:
        fields = {}
        if req.proxy is not None:
            fields["proxy"] = req.proxy
        if req.timezone is not None:
            fields["timezone"] = req.timezone
        if req.locale is not None:
            fields["locale"] = req.locale
        if req.platform is not None:
            fields["platform"] = req.platform
        if req.user_agent is not None:
            fields["user_agent"] = req.user_agent
        if req.screen_width is not None:
            fields["screen_width"] = req.screen_width
        if req.screen_height is not None:
            fields["screen_height"] = req.screen_height
        return fields

    def _worker_url(self, cbm_url: str) -> str:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(cbm_url)
        return urlunparse(parsed._replace(netloc=f"{parsed.hostname}:{cfg.WORKER_PORT}"))

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

        cbm_url = session["node_url"]
        worker_url = self._worker_url(cbm_url)
        profile_id = session["profile_id"]

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # Stop browser
                await client.post(f"{cbm_url}/api/profiles/{profile_id}/stop")
                # Push profile data back to master
                await client.post(
                    f"{worker_url}/internal/sync/push",
                    json={"profile_id": profile_id, "master_url": cfg.MASTER_URL, "local_dir": f"/data/cbm-profiles/{profile_id}"},
                    timeout=60,
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
                # Force mark released
                await db.execute("UPDATE sessions SET status = 'released' WHERE session_id = ?", (session["session_id"],))
                await db.commit()

        # Delete mapping and storage
        profile_id = await reset_consumer(consumer_id)
        if profile_id:
            storage.delete_profile_data(profile_id)
            # Try to delete from CBM nodes (best effort)
            for node in self.registry.all_nodes():
                try:
                    async with httpx.AsyncClient(timeout=5) as client:
                        await client.delete(f"{node.url}/api/profiles/{profile_id}")
                except Exception:
                    pass
