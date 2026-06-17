from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, UploadFile, File, WebSocket, Query
from fastapi.responses import FileResponse, HTMLResponse
from app.config import cfg
from app import database as db
from app.models import AcquireRequest, AcquireResponse, ReleaseRequest, RenewRequest, RenewResponse, ResetRequest, NodeHeartbeat, NodeInfo, SessionInfo, StatsResponse
from app.nodes import NodeRegistry
from app.pool import PoolManager
from app.ttl_watcher import TTLWatcher
from app import storage

registry = NodeRegistry()
pool = PoolManager(registry)
watcher = TTLWatcher(pool)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    task = asyncio.create_task(watcher.run())
    yield
    task.cancel()
    await db.close_db()


app = FastAPI(title="Browser Pool Service", lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"ok": True, "role": cfg.ROLE}


@app.post("/api/nodes/heartbeat")
async def node_heartbeat(body: NodeHeartbeat):
    registry.register_or_heartbeat(body.node_id, body.url, body.max_sessions, body.current_sessions)
    return {"ok": True}


@app.get("/api/nodes", response_model=list[NodeInfo])
async def list_nodes():
    return [
        NodeInfo(
            node_id=n.node_id, url=n.url, max_sessions=n.max_sessions,
            current_sessions=n.current_sessions, online=n.online,
            last_heartbeat=datetime.fromtimestamp(n.last_heartbeat, tz=timezone.utc).isoformat(),
        )
        for n in registry.all_nodes()
    ]


# ── Internal: Profile data storage (used by workers) ──────────────────────────

@app.post("/api/pool/acquire", response_model=AcquireResponse)
async def acquire(req: AcquireRequest):
    return await pool.acquire(req)


@app.post("/api/pool/release")
async def release(req: ReleaseRequest):
    await pool.release(req.session_id, req.owner)
    return {"ok": True}


@app.post("/api/pool/renew", response_model=RenewResponse)
async def renew(req: RenewRequest):
    expires_at = await pool.renew(req.session_id, req.owner)
    return RenewResponse(expires_at=expires_at)


@app.post("/api/pool/reset")
async def reset(req: ResetRequest):
    await pool.reset(req.consumer_id)
    return {"ok": True}


# ── Internal: Profile data storage (used by workers) ──────────────────────────

@app.get("/internal/profiles/{profile_id}/download")
async def download_profile(profile_id: str):
    path = storage.get_profile_path(profile_id)
    if not path:
        raise HTTPException(404, "Profile data not found")
    return FileResponse(path, media_type="application/gzip", filename="userdata.tar.gz")


@app.post("/internal/profiles/{profile_id}/upload")
async def upload_profile(profile_id: str, file: UploadFile = File(...)):
    data = await file.read()
    storage.save_profile(profile_id, data)
    return {"ok": True}


# ── Dashboard APIs ────────────────────────────────────────────────────────────

@app.get("/api/sessions", response_model=list[SessionInfo])
async def list_sessions():
    dbc = db.get_db()
    rows = await dbc.execute_fetchall("SELECT * FROM sessions WHERE status = 'active'")
    now = datetime.now(timezone.utc)
    result = []
    for r in rows:
        row = dict(r)
        expires = datetime.fromisoformat(row["expires_at"]).replace(tzinfo=timezone.utc) if "+" not in row["expires_at"] else datetime.fromisoformat(row["expires_at"])
        ttl_remaining = max(0, int((expires - now).total_seconds()))
        result.append(SessionInfo(
            session_id=row["session_id"], consumer_id=row["consumer_id"],
            profile_id=row["profile_id"], owner=row["owner"],
            node_id=row["node_id"], node_url=row["node_url"],
            status=row["status"], expires_at=row["expires_at"],
            created_at=row["created_at"], ttl_remaining=ttl_remaining,
            view_token=row["view_token"],
        ))
    return result


@app.get("/api/sessions/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str):
    dbc = db.get_db()
    rows = await dbc.execute_fetchall("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
    if not rows:
        raise HTTPException(404, "Session not found")
    row = dict(rows[0])
    now = datetime.now(timezone.utc)
    expires = datetime.fromisoformat(row["expires_at"]).replace(tzinfo=timezone.utc) if "+" not in row["expires_at"] else datetime.fromisoformat(row["expires_at"])
    ttl_remaining = max(0, int((expires - now).total_seconds()))
    return SessionInfo(
        session_id=row["session_id"], consumer_id=row["consumer_id"],
        profile_id=row["profile_id"], owner=row["owner"],
        node_id=row["node_id"], node_url=row["node_url"],
        status=row["status"], expires_at=row["expires_at"],
        created_at=row["created_at"], ttl_remaining=ttl_remaining,
        view_token=row["view_token"],
    )


@app.post("/api/sessions/{session_id}/stop")
async def admin_stop_session(session_id: str):
    dbc = db.get_db()
    rows = await dbc.execute_fetchall("SELECT owner FROM sessions WHERE session_id = ? AND status = 'active'", (session_id,))
    if not rows:
        raise HTTPException(404, "Session not found or not active")
    await pool.release(session_id, rows[0][0])
    return {"ok": True}


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    dbc = db.get_db()
    rows = await dbc.execute_fetchall("SELECT COUNT(*) FROM sessions WHERE status = 'active'")
    running = rows[0][0]
    nodes = [
        NodeInfo(
            node_id=n.node_id, url=n.url, max_sessions=n.max_sessions,
            current_sessions=n.current_sessions, online=n.online,
            last_heartbeat=datetime.fromtimestamp(n.last_heartbeat, tz=timezone.utc).isoformat(),
        )
        for n in registry.all_nodes()
    ]
    return StatsResponse(running_sessions=running, max_global_sessions=cfg.MAX_GLOBAL_SESSIONS, nodes=nodes)


@app.get("/api/mappings")
async def list_mappings():
    dbc = db.get_db()
    rows = await dbc.execute_fetchall("SELECT consumer_id, profile_id, created_at FROM consumer_profiles")
    return [{"consumer_id": r[0], "profile_id": r[1], "created_at": r[2]} for r in rows]


# ── View: noVNC page with token auth ─────────────────────────────────────────

@app.get("/view/{session_id}")
async def view_session(session_id: str, token: str = Query(...)):
    dbc = db.get_db()
    rows = await dbc.execute_fetchall(
        "SELECT view_token, node_url, profile_id FROM sessions WHERE session_id = ? AND status = 'active'",
        (session_id,),
    )
    if not rows:
        raise HTTPException(404, "Session not found or not active")
    if rows[0][0] != token:
        raise HTTPException(403, "Invalid view token")
    node_url = rows[0][1]
    profile_id = rows[0][2]
    # Return minimal noVNC HTML page
    vnc_ws_url = f"/api/view/{session_id}/vnc?token={token}"
    html = f"""<!DOCTYPE html>
<html><head><title>Browser View - {session_id[:8]}</title>
<style>body{{margin:0;overflow:hidden}}#screen{{width:100vw;height:100vh}}</style>
</head><body>
<div id="screen"></div>
<script src="https://cdn.jsdelivr.net/npm/@novnc/novnc@1.4.0/lib/rfb.js" type="module"></script>
<script type="module">
import RFB from 'https://cdn.jsdelivr.net/npm/@novnc/novnc@1.4.0/lib/rfb.js';
const wsUrl = (location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + '{vnc_ws_url}';
const rfb = new RFB(document.getElementById('screen'), wsUrl);
rfb.scaleViewport = true;
rfb.resizeSession = true;
</script></body></html>"""
    return HTMLResponse(html)


@app.websocket("/api/view/{session_id}/vnc")
async def vnc_proxy(websocket: WebSocket, session_id: str, token: str = Query(...)):
    dbc = db.get_db()
    rows = await dbc.execute_fetchall(
        "SELECT view_token, node_url, profile_id FROM sessions WHERE session_id = ? AND status = 'active'",
        (session_id,),
    )
    if not rows or rows[0][0] != token:
        await websocket.close(code=4403, reason="Forbidden")
        return

    node_url = rows[0][1]
    profile_id = rows[0][2]
    await websocket.accept(subprotocol="binary")

    # Proxy to node's VNC WebSocket
    import websockets
    target_ws = f"ws://{node_url.replace('http://', '')}/api/profiles/{profile_id}/vnc"
    try:
        async with websockets.connect(target_ws, subprotocols=["binary"], max_size=None, ping_interval=None) as vnc_ws:
            async def client_to_vnc():
                try:
                    while True:
                        msg = await websocket.receive()
                        if msg.get("type") == "websocket.disconnect":
                            break
                        if "bytes" in msg and msg["bytes"]:
                            await vnc_ws.send(msg["bytes"])
                except Exception:
                    pass

            async def vnc_to_client():
                try:
                    async for msg in vnc_ws:
                        if isinstance(msg, bytes):
                            await websocket.send_bytes(msg)
                        else:
                            await websocket.send_text(msg)
                except Exception:
                    pass

            c2v = asyncio.create_task(client_to_vnc())
            v2c = asyncio.create_task(vnc_to_client())
            done, pending = await asyncio.wait([c2v, v2c], return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ── Static Frontend (React SPA) ──────────────────────────────────────────────
from pathlib import Path
from fastapi.staticfiles import StaticFiles

FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("internal/") or full_path.startswith("view/"):
            raise HTTPException(404, "Not found")
        file_path = FRONTEND_DIR / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIR / "index.html")
