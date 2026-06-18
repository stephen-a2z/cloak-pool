"""Browserless engine adapter (open-source, stateless sessions)."""
from __future__ import annotations
import httpx
from fastapi import HTTPException
from app.engines import BrowserEngine, ProfileConfig


class BrowserlessEngine:
    """Adapter for Browserless open-source (ghcr.io/browserless/chromium)."""

    def __init__(self, timeout: float = 10):
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
        # Browserless is stateless - no profile to create.
        # Just verify the node is reachable.
        try:
            client = await self._get_client()
            params = {"token": token} if token else {}
            r = await client.get(f"{node_url}/json/version", params=params)
            if r.status_code != 200:
                raise HTTPException(502, f"Browserless node unreachable: {r.status_code}")
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise HTTPException(502, f"Browserless node unreachable ({node_url}): {exc}")
        # Return a virtual profile_id for internal tracking
        import uuid
        return str(uuid.uuid4())

    async def profile_exists(self, node_url: str, profile_id: str, token: str = "") -> bool:
        return True  # Always "exists" - stateless

    async def update_profile(self, node_url: str, profile_id: str, fields: dict, token: str = "") -> None:
        pass  # No-op for stateless engine

    async def launch(self, node_url: str, profile_id: str, token: str = "") -> None:
        # Browserless launches on CDP connect - nothing to do here
        pass

    async def wait_ready(self, node_url: str, profile_id: str, timeout: float = 15, token: str = "") -> None:
        # Always ready - browser starts on connect
        pass

    async def stop(self, node_url: str, profile_id: str, token: str = "") -> None:
        # Consumer disconnects CDP → browser auto-closes
        pass

    async def delete_profile(self, node_url: str, profile_id: str, token: str = "") -> None:
        pass  # No-op

    def get_cdp_url(self, node_url: str, profile_id: str, token: str = "") -> str:
        host = node_url.replace("http://", "").replace("https://", "")
        url = f"ws://{host}"
        if token:
            url += f"?token={token}"
        return url
