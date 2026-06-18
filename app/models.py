from __future__ import annotations
from pydantic import BaseModel, Field


class AcquireRequest(BaseModel):
    consumer_id: str
    owner: str
    ttl: int | None = None
    engine: str = "cloakbrowser"  # "cloakbrowser" or "browserless"
    proxy: str | None = None
    timezone: str | None = None
    locale: str | None = None
    platform: str | None = None
    user_agent: str | None = None
    screen_width: int | None = None
    screen_height: int | None = None


class AcquireResponse(BaseModel):
    session_id: str
    consumer_id: str
    profile_id: str
    cdp_url: str
    view_url: str
    node: str
    expires_at: str


class RenewRequest(BaseModel):
    session_id: str
    owner: str


class RenewResponse(BaseModel):
    ok: bool = True
    expires_at: str


class ReleaseRequest(BaseModel):
    session_id: str
    owner: str


class ResetRequest(BaseModel):
    consumer_id: str


class NodeHeartbeat(BaseModel):
    node_id: str
    url: str
    max_sessions: int
    current_sessions: int
    cpu_percent: float = 0
    memory_percent: float = 0
    disk_percent: float = 0
    engine: str = "cloakbrowser"
    token: str = ""


class NodeInfo(BaseModel):
    node_id: str
    url: str
    max_sessions: int
    current_sessions: int
    online: bool
    last_heartbeat: str
    cpu_percent: float = 0
    memory_percent: float = 0
    disk_percent: float = 0


class SessionInfo(BaseModel):
    session_id: str
    consumer_id: str
    profile_id: str
    owner: str
    node_id: str
    node_url: str
    status: str
    expires_at: str
    created_at: str
    ttl_remaining: int
    view_token: str = ""


class StatsResponse(BaseModel):
    running_sessions: int
    max_global_sessions: int
    nodes: list[NodeInfo]


class SyncRequest(BaseModel):
    profile_id: str
    master_url: str
    local_dir: str


# ── Global Defaults ───────────────────────────────────────────────────────────

class GlobalDefaults(BaseModel):
    proxy: str | None = None
    timezone: str | None = None
    locale: str | None = None
    platform: str = "windows"
    user_agent: str | None = None
    screen_width: int = 1920
    screen_height: int = 1080
    notes: str | None = None
    updated_at: str = ""


class GlobalDefaultsUpdate(BaseModel):
    proxy: str | None = None
    timezone: str | None = None
    locale: str | None = None
    platform: str | None = None
    user_agent: str | None = None
    screen_width: int | None = None
    screen_height: int | None = None
    notes: str | None = None
