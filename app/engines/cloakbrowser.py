"""CloakBrowser-Manager engine adapter."""
from __future__ import annotations
import asyncio
import httpx
from fastapi import HTTPException
from app.engines import BrowserEngine, ProfileConfig


class CloakBrowserEngine:
    """Adapter for CloakBrowser-Manager API."""

    def __init__(self, timeout: float = 15):
        self._timeout = timeout

    async def create_profile(self, node_url: str, config: ProfileConfig) -> str:
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

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(f"{node_url}/api/profiles", json=payload)
            if r.status_code not in (200, 201):
                raise HTTPException(502, f"Failed to create profile on node: {r.text}")
            return r.json().get("id")

    async def profile_exists(self, node_url: str, profile_id: str) -> bool:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(f"{node_url}/api/profiles/{profile_id}")
            return r.status_code != 404

    async def update_profile(self, node_url: str, profile_id: str, fields: dict) -> None:
        if not fields:
            return
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.put(f"{node_url}/api/profiles/{profile_id}", json=fields)
            if r.status_code not in (200, 201):
                raise HTTPException(502, f"Failed to update profile on node: {r.text}")

    async def launch(self, node_url: str, profile_id: str) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(f"{node_url}/api/profiles/{profile_id}/launch")
            if r.status_code not in (200, 201):
                raise HTTPException(502, f"Failed to launch browser: {r.text}")

    async def wait_ready(self, node_url: str, profile_id: str, timeout: float = 15) -> None:
        attempts = int(timeout / 0.5)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for _ in range(attempts):
                r = await client.get(f"{node_url}/api/profiles/{profile_id}/status")
                if r.status_code == 200 and r.json().get("status") == "running":
                    return
                await asyncio.sleep(0.5)
        raise HTTPException(504, "Browser did not start in time")

    async def stop(self, node_url: str, profile_id: str) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(f"{node_url}/api/profiles/{profile_id}/stop")

    async def delete_profile(self, node_url: str, profile_id: str) -> None:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.delete(f"{node_url}/api/profiles/{profile_id}")

    def get_cdp_url(self, node_url: str, profile_id: str) -> str:
        host = node_url.replace("http://", "").replace("https://", "")
        return f"ws://{host}/api/profiles/{profile_id}/cdp"
