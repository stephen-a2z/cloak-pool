from __future__ import annotations
import io
import shutil
import tarfile
from pathlib import Path
import httpx

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


async def pull_profile(master_url: str, profile_id: str, local_dir: Path) -> bool:
    """Download profile tar.gz from master and extract to local_dir. Returns False if no data on master."""
    url = f"{master_url}/internal/profiles/{profile_id}/download"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
    if r.status_code == 404:
        return False
    r.raise_for_status()
    # Clear local dir and extract
    if local_dir.exists():
        shutil.rmtree(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO(r.content)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        tar.extractall(local_dir, filter="data")
    return True


async def push_profile(master_url: str, profile_id: str, local_dir: Path) -> None:
    """Clean cache dirs, pack user-data-dir, upload to master."""
    if not local_dir.exists():
        return
    # Clean excluded directories before packing
    for item in local_dir.rglob("*"):
        if item.is_dir() and _should_exclude(str(item.relative_to(local_dir))):
            shutil.rmtree(item, ignore_errors=True)
    # Create tar.gz in memory
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=6) as tar:
        for item in local_dir.iterdir():
            tar.add(item, arcname=item.name)
    buf.seek(0)
    # Upload
    url = f"{master_url}/internal/profiles/{profile_id}/upload"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, files={"file": ("userdata.tar.gz", buf, "application/gzip")})
    r.raise_for_status()
