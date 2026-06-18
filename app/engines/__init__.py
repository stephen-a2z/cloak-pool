"""Browser engine adapter interface.

Each adapter encapsulates communication with a specific browser engine
(CloakBrowser-Manager, Browserless, raw Chrome, etc.).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ProfileConfig:
    """Configuration for creating/updating a browser profile."""
    name: str
    fingerprint_seed: int | None = None
    proxy: str | None = None
    timezone: str | None = None
    locale: str | None = None
    platform: str = "windows"
    user_agent: str | None = None
    screen_width: int = 1920
    screen_height: int = 1080
    launch_args: list[str] | None = None


@dataclass
class SessionResult:
    """Result of launching a browser session on an engine."""
    profile_id: str          # Engine-assigned profile/session ID
    cdp_url: str             # Full CDP WebSocket URL for Playwright/Puppeteer


class BrowserEngine(Protocol):
    """Protocol that all browser engine adapters must implement."""

    async def create_profile(self, node_url: str, config: ProfileConfig) -> str:
        """Create a profile on the node. Returns the engine-assigned profile ID."""
        ...

    async def profile_exists(self, node_url: str, profile_id: str) -> bool:
        """Check if a profile exists on the node."""
        ...

    async def update_profile(self, node_url: str, profile_id: str, fields: dict) -> None:
        """Update an existing profile's configuration."""
        ...

    async def launch(self, node_url: str, profile_id: str) -> None:
        """Launch the browser for a profile."""
        ...

    async def wait_ready(self, node_url: str, profile_id: str, timeout: float = 15) -> None:
        """Wait until the browser is running and ready for CDP connections."""
        ...

    async def stop(self, node_url: str, profile_id: str) -> None:
        """Stop the browser for a profile."""
        ...

    async def delete_profile(self, node_url: str, profile_id: str) -> None:
        """Delete a profile from the node."""
        ...

    def get_cdp_url(self, node_url: str, profile_id: str) -> str:
        """Build the CDP WebSocket URL for connecting to this profile."""
        ...
