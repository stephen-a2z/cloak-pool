"""CloakBrowser-Manager engine adapter."""
from __future__ import annotations
import asyncio
import logging
import httpx
from fastapi import HTTPException
from app.engines import BrowserEngine, ProfileConfig

logger = logging.getLogger("browser-pool.engine.cbm")


class CloakBrowserEngine:
    """Adapter for CloakBrowser-Manager API."""

    def __init__(self, timeout: float = 15):
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def create_profile(self, node_url: str, config: ProfileConfig, token: str = "") -> str:
        payload = {"name": config.name, "platform": config.platform,
                   "screen_width": config.screen_width, "screen_height": config.screen_height}
        if config.fingerprint_seed is not None:
            payload["fingerprint_seed"] = config.fingerprint_seed
        if config.proxy:
            payload["proxy"] = config.proxy
        if config.timezone:
            payload["timezone"] = config.timezone
        if config.locale:
            payload["locale"] = config.locale
        if config.user_agent:
            payload["user_agent"] = config.user_agent
        if config.launch_args:
            payload["launch_args"] = config.launch_args

        try:
            client = await self._get_client()
            r = await client.post(f"{node_url}/api/profiles", json=payload)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise HTTPException(502, f"Node unreachable ({node_url}): {exc}")
        if r.status_code not in (200, 201):
            raise HTTPException(502, f"Failed to create profile on node: {r.text}")
        return r.json().get("id")

    async def profile_exists(self, node_url: str, profile_id: str, token: str = "") -> bool:
        try:
            client = await self._get_client()
            r = await client.get(f"{node_url}/api/profiles/{profile_id}")
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise HTTPException(502, f"Node unreachable ({node_url}): {exc}")
        return r.status_code != 404

    async def update_profile(self, node_url: str, profile_id: str, fields: dict, token: str = "") -> None:
        if not fields:
            return
        try:
            client = await self._get_client()
            r = await client.put(f"{node_url}/api/profiles/{profile_id}", json=fields)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise HTTPException(502, f"Node unreachable ({node_url}): {exc}")
        if r.status_code not in (200, 201):
            raise HTTPException(502, f"Failed to update profile on node: {r.text}")

    async def launch(self, node_url: str, profile_id: str, token: str = "") -> None:
        try:
            client = await self._get_client()
            r = await client.post(f"{node_url}/api/profiles/{profile_id}/launch")
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise HTTPException(502, f"Node unreachable ({node_url}): {exc}")
        if r.status_code not in (200, 201):
            raise HTTPException(502, f"Failed to launch browser: {r.text}")

    async def wait_ready(self, node_url: str, profile_id: str, timeout: float = 15, token: str = "") -> None:
        attempts = int(timeout / 0.5)
        client = await self._get_client()
        for _ in range(attempts):
            r = await client.get(f"{node_url}/api/profiles/{profile_id}/status")
            if r.status_code == 200 and r.json().get("status") == "running":
                return
            await asyncio.sleep(0.5)
        raise HTTPException(504, "Browser did not start in time")

    async def stop(self, node_url: str, profile_id: str, token: str = "") -> None:
        client = await self._get_client()
        await client.post(f"{node_url}/api/profiles/{profile_id}/stop", timeout=30)

    async def delete_profile(self, node_url: str, profile_id: str, token: str = "") -> None:
        client = await self._get_client()
        await client.delete(f"{node_url}/api/profiles/{profile_id}", timeout=5)

    def get_cdp_url(self, node_url: str, profile_id: str, token: str = "") -> str:
        host = node_url.replace("http://", "").replace("https://", "")
        return f"ws://{host}/api/profiles/{profile_id}/cdp"
