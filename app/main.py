from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File, WebSocket, Query
from fastapi.responses import FileResponse, HTMLResponse
from app.config import cfg
from app import database as db
from app.models import AcquireRequest, AcquireResponse, ReleaseRequest, RenewRequest, RenewResponse, ResetRequest, NodeHeartbeat, NodeInfo, SessionInfo, StatsResponse, GlobalDefaults, GlobalDefaultsUpdate
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
    import logging, socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        host_ip = s.getsockname()[0]
        s.close()
    except Exception:
        host_ip = "localhost"
    logging.getLogger("browser-pool").info(
        "\n"
        "╔══════════════════════════════════════════════════╗\n"
        "║  Browser Pool Master started                    ║\n"
        "║                                                 ║\n"
        f"║  Dashboard:  http://{host_ip}:9000            \n"
        f"║  API:        http://{host_ip}:9000/api/health \n"
        "║                                                 ║\n"
        "╚══════════════════════════════════════════════════╝"
    )
    yield
    task.cancel()
    for eng in pool.engines.values():
        if hasattr(eng, 'close'):
            await eng.close()
    await db.close_db()


app = FastAPI(title="Browser Pool Service", lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"ok": True, "role": cfg.ROLE}


@app.post("/api/nodes/heartbeat")
async def node_heartbeat(body: NodeHeartbeat):
    registry.register_or_heartbeat(body.node_id, body.url, body.max_sessions, body.current_sessions, body.cpu_percent, body.memory_percent, body.disk_percent, body.engine, body.token)
    return {"ok": True}


@app.get("/api/nodes", response_model=list[NodeInfo])
async def list_nodes():
    return [
        NodeInfo(
            node_id=n.node_id, url=n.url, max_sessions=n.max_sessions,
            current_sessions=n.current_sessions, online=n.online,
            last_heartbeat=datetime.fromtimestamp(n.last_heartbeat, tz=timezone.utc).isoformat(),
            cpu_percent=n.cpu_percent, memory_percent=n.memory_percent, disk_percent=n.disk_percent,
        )
        for n in registry.all_nodes()
    ]


# ── Pool API ──────────────────────────────────────────────────────────────────

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


# ── Node Profile Management ───────────────────────────────────────────────────

@app.get("/api/nodes/{node_id}/profiles")
async def get_node_profiles(node_id: str):
    """Get all profiles on a specific CBM node with their status."""
    node = next((n for n in registry.all_nodes() if n.node_id == node_id), None)
    if not node or not node.online:
        raise HTTPException(404, "Node not found or offline")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{node.url}/api/profiles")
            if r.status_code != 200:
                raise HTTPException(502, "Failed to fetch profiles from node")
            return r.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Node unreachable: {exc}")


@app.post("/api/nodes/{node_id}/profiles")
async def create_node_profile(node_id: str, body: dict):
    """Create a new profile on a specific CBM node using global defaults."""
    node = next((n for n in registry.all_nodes() if n.node_id == node_id), None)
    if not node or not node.online:
        raise HTTPException(404, "Node not found or offline")
    dbc = db.get_db()
    rows = await dbc.execute_fetchall("SELECT * FROM global_defaults WHERE id = 1")
    defaults = {k: v for k, v in dict(rows[0]).items() if k not in ("id", "updated_at", "notes") and v is not None} if rows else {}
    profile_data = {**defaults, **{k: v for k, v in body.items() if v}}
    profile_data.setdefault("name", "New Profile")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{node.url}/api/profiles", json=profile_data)
            if r.status_code not in (200, 201):
                try:
                    detail = r.json().get("detail", "Create failed")
                except Exception:
                    detail = r.text[:200]
                raise HTTPException(r.status_code, detail)
            return r.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Node unreachable: {exc}")


@app.post("/api/nodes/{node_id}/profiles/{profile_id}/launch")
async def launch_node_profile(node_id: str, profile_id: str):
    """Launch a profile on a specific node."""
    node = next((n for n in registry.all_nodes() if n.node_id == node_id), None)
    if not node or not node.online:
        raise HTTPException(404, "Node not found or offline")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{node.url}/api/profiles/{profile_id}/launch")
            if r.status_code not in (200, 201):
                try:
                    detail = r.json().get("detail", "Launch failed")
                except Exception:
                    detail = r.text[:200]
                raise HTTPException(r.status_code, detail)
            return r.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Node unreachable: {exc}")


@app.post("/api/nodes/{node_id}/profiles/{profile_id}/stop")
async def stop_node_profile(node_id: str, profile_id: str):
    """Stop a profile on a specific node."""
    node = next((n for n in registry.all_nodes() if n.node_id == node_id), None)
    if not node or not node.online:
        raise HTTPException(404, "Node not found or offline")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{node.url}/api/profiles/{profile_id}/stop")
            if r.status_code not in (200, 201):
                try:
                    detail = r.json().get("detail", "Stop failed")
                except Exception:
                    detail = r.text[:200]
                raise HTTPException(r.status_code, detail)
            return r.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Node unreachable: {exc}")


# ── Global Defaults ────────────────────────────────────────────────────────────

@app.get("/api/defaults", response_model=GlobalDefaults)
async def get_defaults():
    dbc = db.get_db()
    rows = await dbc.execute_fetchall("SELECT * FROM global_defaults WHERE id = 1")
    return GlobalDefaults(**dict(rows[0]))


@app.put("/api/defaults", response_model=GlobalDefaults)
async def update_defaults(req: GlobalDefaultsUpdate):
    dbc = db.get_db()
    fields = req.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "No fields to update")
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values())
    await dbc.execute(f"UPDATE global_defaults SET {set_clause} WHERE id = 1", values)
    await dbc.commit()
    rows = await dbc.execute_fetchall("SELECT * FROM global_defaults WHERE id = 1")
    return GlobalDefaults(**dict(rows[0]))


async def _get_defaults_dict() -> dict:
    dbc = db.get_db()
    rows = await dbc.execute_fetchall("SELECT * FROM global_defaults WHERE id = 1")
    row = dict(rows[0])
    row.pop("id", None)
    row.pop("updated_at", None)
    row.pop("notes", None)
    return {k: v for k, v in row.items() if v is not None}


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
    """正在被使用的 session（consumer 持有中）"""
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


@app.get("/api/sessions/running")
async def list_running_sessions():
    """活跃的 session（所有节点上实际正在运行的浏览器）"""
    async def fetch_node(node):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{node.url}/api/profiles")
                if r.status_code == 200:
                    return [(p, node) for p in r.json() if p.get("status") == "running"]
        except Exception:
            pass
        return []

    online_nodes = [n for n in registry.all_nodes() if n.online]
    node_results = await asyncio.gather(*(fetch_node(n) for n in online_nodes))
    results = []
    for items in node_results:
        for p, node in items:
            results.append({
                "profile_id": p["id"],
                "name": p.get("name", ""),
                "node_id": node.node_id,
                "node_url": node.url,
                "status": "running",
                "vnc_ws_port": p.get("vnc_ws_port"),
                "cdp_url": p.get("cdp_url"),
            })
    return results


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


# ── View: noVNC pages ─────────────────────────────────────────────────────────

def _vnc_page_response(ws_path: str):
    """Redirect to the built vnc.html with ws path as query parameter."""
    from urllib.parse import quote
    return HTMLResponse(
        status_code=200,
        content=f'<html><head><meta http-equiv="refresh" content="0;url=/vnc.html?ws={quote(ws_path)}"></head></html>',
    )


def _view_page_response(ws_path: str, mode: str = "vnc"):
    """Redirect to view.html with ws path and mode."""
    from urllib.parse import quote
    return HTMLResponse(
        status_code=200,
        content=f'<html><head><meta http-equiv="refresh" content="0;url=/view.html?ws={quote(ws_path)}&mode={mode}"></head></html>',
    )


@app.get("/view/{session_id}")
async def view_session(session_id: str, token: str = Query(...), mode: str = Query("vnc")):
    """View page for sessions (token-authenticated, shareable URL)."""
    dbc = db.get_db()
    rows = await dbc.execute_fetchall(
        "SELECT view_token, node_url, profile_id FROM sessions WHERE session_id = ? AND status = 'active'",
        (session_id,),
    )
    if not rows:
        raise HTTPException(404, "Session not found or not active")
    if rows[0][0] != token:
        raise HTTPException(403, "Invalid view token")
    return _view_page_response(f"/api/view/{session_id}/vnc?token={token}", mode)


@app.get("/view/browser/{node_id}/{profile_id}")
async def view_browser(node_id: str, profile_id: str, mode: str = Query("vnc")):
    """View page for any running browser (admin, no token needed)."""
    node = next((n for n in registry.all_nodes() if n.node_id == node_id), None)
    if not node:
        raise HTTPException(404, "Node not found")
    return _view_page_response(f"/api/view/browser/{node_id}/{profile_id}/vnc", mode)

@app.websocket("/api/view/{session_id}/vnc")
async def vnc_proxy(websocket: WebSocket, session_id: str, token: str = Query(...)):
    """VNC proxy for session view (token-authenticated)."""
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
    await _proxy_vnc(websocket, node_url, profile_id)


@app.websocket("/api/view/browser/{node_id}/{profile_id}/vnc")
async def vnc_proxy_browser(websocket: WebSocket, node_id: str, profile_id: str):
    """VNC proxy for direct browser view (admin, no token)."""
    node = next((n for n in registry.all_nodes() if n.node_id == node_id), None)
    if not node:
        await websocket.close(code=4004, reason="Node not found")
        return
    await _proxy_vnc(websocket, node.url, profile_id)


async def _proxy_vnc(websocket: WebSocket, node_url: str, profile_id: str):
    await websocket.accept(subprotocol="binary")
    import websockets
    target_ws = f"ws://{node_url.replace('http://', '')}/api/profiles/{profile_id}/vnc"
    try:
        async with websockets.connect(target_ws, subprotocols=["binary"], max_size=None, ping_interval=30, close_timeout=5) as vnc_ws:
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
            await asyncio.gather(*pending, return_exceptions=True)
    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ── CDP Screencast Proxy ──────────────────────────────────────────────────────

@app.websocket("/api/view/{session_id}/cdp")
async def cdp_proxy_session(websocket: WebSocket, session_id: str, token: str = Query(...)):
    """CDP proxy for session view (token-authenticated)."""
    dbc = db.get_db()
    rows = await dbc.execute_fetchall(
        "SELECT view_token, node_url, profile_id FROM sessions WHERE session_id = ? AND status = 'active'",
        (session_id,),
    )
    if not rows or rows[0][0] != token:
        await websocket.close(code=4403, reason="Forbidden")
        return
    await _proxy_cdp(websocket, rows[0][1], rows[0][2])


@app.websocket("/api/view/browser/{node_id}/{profile_id}/cdp")
async def cdp_proxy_browser(websocket: WebSocket, node_id: str, profile_id: str):
    """CDP proxy for direct browser view (admin, no token)."""
    node = next((n for n in registry.all_nodes() if n.node_id == node_id), None)
    if not node:
        await websocket.close(code=4004, reason="Node not found")
        return
    await _proxy_cdp(websocket, node.url, profile_id)


async def _proxy_cdp(websocket: WebSocket, node_url: str, profile_id: str):
    """Bi-directional CDP WebSocket proxy for screencast + input (page-level)."""
    await websocket.accept()
    import websockets

    # Get the first page target's devtools WS path
    node_host = node_url.replace("http://", "").replace("https://", "")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{node_url}/api/profiles/{profile_id}/cdp/json/list")
            if r.status_code != 200:
                await websocket.send_text('{"error":"Failed to get CDP targets"}')
                await websocket.close()
                return
            targets = r.json()
            page_targets = [t for t in targets if t.get("type") == "page"]
            if not page_targets:
                await websocket.send_text('{"error":"No page targets found"}')
                await websocket.close()
                return
            # Extract the devtools path from the rewritten webSocketDebuggerUrl
            ws_url = page_targets[0].get("webSocketDebuggerUrl", "")
            # URL is rewritten by CBM to be like ws://host/api/profiles/{id}/cdp/devtools/page/xxx
            # We need to connect through the CBM proxy
            if ws_url.startswith("ws://"):
                target_ws = ws_url
            else:
                # Fallback: build from target id
                target_id = page_targets[0].get("id", "")
                target_ws = f"ws://{node_host}/api/profiles/{profile_id}/cdp/devtools/page/{target_id}"
    except Exception as exc:
        await websocket.send_text(f'{{"error":"CDP discovery failed: {exc}"}}')
        await websocket.close()
        return

    try:
        async with websockets.connect(target_ws, max_size=None, ping_interval=30, close_timeout=5) as cdp_ws:
            async def client_to_cdp():
                try:
                    while True:
                        msg = await websocket.receive()
                        if msg.get("type") == "websocket.disconnect":
                            break
                        if "text" in msg and msg["text"]:
                            await cdp_ws.send(msg["text"])
                except Exception:
                    pass

            async def cdp_to_client():
                try:
                    async for msg in cdp_ws:
                        if isinstance(msg, str):
                            await websocket.send_text(msg)
                        else:
                            await websocket.send_bytes(msg)
                except Exception:
                    pass

            c2c = asyncio.create_task(client_to_cdp())
            c2f = asyncio.create_task(cdp_to_client())
            done, pending = await asyncio.wait([c2c, c2f], return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ── Log Streaming (SSE) ───────────────────────────────────────────────────────
import logging
import collections
from fastapi.responses import StreamingResponse

_log_buffer: collections.deque = collections.deque(maxlen=500)
_log_subscribers: list[asyncio.Queue] = []


class _SSELogHandler(logging.Handler):
    def emit(self, record):
        entry = self.format(record)
        _log_buffer.append(entry)
        for q in _log_subscribers[:]:
            try:
                q.put_nowait(entry)
            except asyncio.QueueFull:
                pass


def _setup_log_handler():
    handler = _SSELogHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"))
    root = logging.getLogger("browser-pool")
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # Also capture uvicorn access logs
    uv = logging.getLogger("uvicorn.access")
    uv.addHandler(handler)


_setup_log_handler()


@app.get("/api/logs/history")
async def get_log_history():
    """Get recent log buffer (last 500 lines)."""
    return list(_log_buffer)


@app.get("/api/logs/stream")
async def stream_logs():
    """SSE stream of real-time logs."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _log_subscribers.append(queue)

    async def event_generator():
        try:
            while True:
                entry = await queue.get()
                yield f"data: {entry}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _log_subscribers.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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
