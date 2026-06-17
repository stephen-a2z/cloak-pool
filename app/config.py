from __future__ import annotations
import os


class Config:
    ROLE: str = os.environ.get("ROLE", "master")  # master | worker
    MASTER_URL: str = os.environ.get("MASTER_URL", "http://localhost:9000")
    NODE_ADVERTISE_URL: str = os.environ.get("NODE_ADVERTISE_URL", "http://localhost:8080")
    NODE_ID: str = os.environ.get("NODE_ID", "node-1")
    WORKER_PORT: int = int(os.environ.get("WORKER_PORT", "9001"))
    MAX_GLOBAL_SESSIONS: int = int(os.environ.get("MAX_GLOBAL_SESSIONS", "10"))
    MAX_NODE_SESSIONS: int = int(os.environ.get("MAX_NODE_SESSIONS", "5"))
    PROFILE_STORAGE_DIR: str = os.environ.get("PROFILE_STORAGE_DIR", "/data/profiles")
    TTL_DEFAULT: int = int(os.environ.get("TTL_DEFAULT", "1800"))  # 30 min
    TTL_MAX: int = int(os.environ.get("TTL_MAX", "7200"))  # 2 hours
    DB_PATH: str = os.environ.get("DB_PATH", "/data/browser-pool.db")


cfg = Config()
