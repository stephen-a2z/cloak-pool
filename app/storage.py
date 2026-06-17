from __future__ import annotations
from pathlib import Path
from app.config import cfg


def _profile_dir(profile_id: str) -> Path:
    return Path(cfg.PROFILE_STORAGE_DIR) / profile_id


def profile_exists(profile_id: str) -> bool:
    return (_profile_dir(profile_id) / "userdata.tar.gz").exists()


def get_profile_path(profile_id: str) -> Path | None:
    p = _profile_dir(profile_id) / "userdata.tar.gz"
    return p if p.exists() else None


def save_profile(profile_id: str, data: bytes) -> None:
    d = _profile_dir(profile_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "userdata.tar.gz").write_bytes(data)


def delete_profile_data(profile_id: str) -> None:
    import shutil
    d = _profile_dir(profile_id)
    if d.exists():
        shutil.rmtree(d)
