from __future__ import annotations
import io
import shutil
import tarfile
from pathlib import Path

import httpx

from app.config import cfg

EXCLUDE_DIRS = {"Cache", "Code Cache", "GPUCache", "BrowserMetrics", "crashpad"}
EXCLUDE_PREFIXES = ("Service Worker",)


def _should_exclude(name: str) -> bool:
    parts = Path(name).parts
    for part in parts:
        if part in EXCLUDE_DIRS:
            return True
        for prefix in EXCLUDE_PREFIXES:
            if part.startswith(prefix):
                return True
    return False


def _cleanup_cache_dirs(local_dir: Path) -> None:
    for item in local_dir.rglob("*"):
        if item.is_dir() and _should_exclude(str(item.relative_to(local_dir))):
            shutil.rmtree(item, ignore_errors=True)


# ── NFS mode ──────────────────────────────────────────────────────────────────

def _nfs_path() -> Path:
    return Path(cfg.NFS_PROFILES_DIR)


async def _pull_nfs(profile_id: str, local_dir: Path) -> bool:
    src = _nfs_path() / f"{profile_id}.tar.gz"
    if not src.exists():
        return False
    if local_dir.exists():
        shutil.rmtree(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(src, "r:gz") as tar:
        tar.extractall(local_dir, filter="data")
    return True


async def _push_nfs(profile_id: str, local_dir: Path) -> None:
    if not local_dir.exists():
        return
    _cleanup_cache_dirs(local_dir)
    dest = _nfs_path() / f"{profile_id}.tar.gz"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest, "w:gz", compresslevel=6) as tar:
        for item in local_dir.iterdir():
            tar.add(item, arcname=item.name)


# ── HTTP mode ─────────────────────────────────────────────────────────────────

async def _pull_http(master_url: str, profile_id: str, local_dir: Path) -> bool:
    url = f"{master_url}/internal/profiles/{profile_id}/download"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
    if r.status_code == 404:
        return False
    r.raise_for_status()
    if local_dir.exists():
        shutil.rmtree(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO(r.content)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        tar.extractall(local_dir, filter="data")
    return True


async def _push_http(master_url: str, profile_id: str, local_dir: Path) -> None:
    if not local_dir.exists():
        return
    _cleanup_cache_dirs(local_dir)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=True) as tmp:
        with tarfile.open(tmp.name, "w:gz", compresslevel=6) as tar:
            for item in local_dir.iterdir():
                tar.add(item, arcname=item.name)
        tmp.seek(0)
        url = f"{master_url}/internal/profiles/{profile_id}/upload"
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, files={"file": ("userdata.tar.gz", tmp, "application/gzip")})
        r.raise_for_status()


# ── Public API (auto-selects mode based on config) ────────────────────────────

async def pull_profile(master_url: str, profile_id: str, local_dir: Path) -> bool:
    if cfg.NFS_PROFILES_DIR:
        return await _pull_nfs(profile_id, local_dir)
    return await _pull_http(master_url, profile_id, local_dir)


async def push_profile(master_url: str, profile_id: str, local_dir: Path) -> None:
    if cfg.NFS_PROFILES_DIR:
        await _push_nfs(profile_id, local_dir)
    else:
        await _push_http(master_url, profile_id, local_dir)
