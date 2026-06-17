# Browser Pool Service — Implementation Plan

## Problem Statement

构建一个 Browser Pool 调度服务，让多个独立的 Playwright worker 能够通过统一 API 获取 CDP 浏览器实例。服务保证：每个 consumer 绑定唯一 profile（含固定指纹和 user-data-dir），同一时刻只有一个 consumer 占用一个 profile，全局并发受限，且支持多机部署。

## Architecture

```
Consumer (Playwright Worker)
    │
    │ POST master:9000/api/pool/acquire
    │ {consumer_id, owner, ttl, proxy?, timezone?, ...}
    ▼
Browser Pool Service (master, Python + FastAPI :9000)
    ├── 映射表: consumer_id → profile_id (1:1 永久绑定, SQLite)
    ├── fingerprint_seed = hash(consumer_id)
    ├── Profile 存储: user-data-dir 压缩包 (master 文件系统)
    ├── 调度: 互斥锁 + 双层并发限制 + 亲和优先
    ├── 节点管理: worker 心跳注册
    ├── Web 仪表盘: React + Tailwind + noVNC
    └── 查看 token: session 级别一次性 token
         │
    ┌────┴────┐
    ▼         ▼
 Node A      Node B       (CloakBrowser-Manager :8080, ROLE=worker)
    │
    ▼
Consumer 直连 CDP: ws://node-x:8080/api/profiles/{id}/cdp
```

## Key Design Decisions

| 项目 | 决策 |
|------|------|
| 服务形态 | cloakhub 独立服务 `browser-pool/`，调用 CloakBrowser-Manager API |
| 技术栈 | Python + FastAPI |
| Consumer ↔ Profile | 1:1 永久绑定，consumer_id 为 key |
| fingerprint_seed | hash(consumer_id) 确定性派生 |
| 首次创建 | acquire 时传入可选配置 |
| 后续 acquire | 配置参数覆盖更新，seed 和 user-data-dir 不变 |
| 数据存储 | master 节点存 user-data-dir 压缩包 |
| 同步方式 | acquire 全量拉取（不跳过），release 清理 cache 后全量覆盖 |
| 并发限制 | 每节点上限 M + 全局上限 N |
| 调度策略 | 亲和优先（上次用该 profile 的节点），回退最空闲 |
| 节点发现 | Worker 主动心跳注册（每10s） |
| Master 高可用 | 固定 master（环境变量 ROLE） |
| CDP 访问 | Consumer 直连节点 |
| 生命周期 | 固定 TTL + 可续约 + 可提前 release |
| TTL 过期 | 自动 stop + 同步 + 释放 |
| user-data-dir 控制 | 启动参数 --disk-cache-size=1048576 + release 时清理 Cache/Code Cache/GPUCache 等后打包 |
| 查看权限 | session 级别 token，acquire 时自动返回 view_url |

## API Endpoints

### Pool API (master :9000)

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/pool/acquire | 获取浏览器实例 |
| POST | /api/pool/renew | 延长 TTL |
| POST | /api/pool/release | 释放浏览器实例 |
| POST | /api/pool/reset | 解绑 consumer，删除 profile |
| POST | /api/nodes/heartbeat | Worker 节点心跳注册 |
| GET | /api/nodes | 节点列表 |
| GET | /api/sessions | 所有活跃 session |
| GET | /api/sessions/{session_id} | 单个 session 详情 |
| POST | /api/sessions/{session_id}/stop | 管理员手动 release |
| GET | /api/stats | 全局统计 |
| GET | /api/mappings | consumer ↔ profile 映射 |
| GET | /view/{session_id}?token=xxx | 直达实时画面 |
| WS | /api/view/{session_id}/vnc?token=xxx | VNC WebSocket 代理 |

### Internal API (worker :9001)

| Method | Path | Description |
|--------|------|-------------|
| POST | /internal/sync/pull | 从 master 拉取 profile 数据 |
| POST | /internal/sync/push | 推送 profile 数据到 master |

### Master Internal (供 worker 调用)

| Method | Path | Description |
|--------|------|-------------|
| GET | /internal/profiles/{profile_id}/download | 下载 user-data-dir 压缩包 |
| POST | /internal/profiles/{profile_id}/upload | 上传 user-data-dir 压缩包 |

## Acquire Response

```json
{
  "session_id": "xxx",
  "consumer_id": "uuid",
  "profile_id": "yyy",
  "cdp_url": "ws://node-a:8080/api/profiles/yyy/cdp",
  "view_url": "http://master:9000/view/xxx?token=zzz",
  "node": "node-a",
  "expires_at": "2026-06-17T00:30:00Z"
}
```

## Acquire Flow

```
1. mapping.get_or_create_profile(consumer_id) → (profile_id, is_new)
2. Check profile not already locked (no active session) → 409
3. Check global concurrency < MAX_GLOBAL → 429
4. nodes.select_node(profile_id) → node (affinity-first) → 503
5. If is_new: POST node CloakBrowser-Manager /api/profiles (create)
6. If not new + has config params: PUT node /api/profiles/{id} (update)
7. If master has profile data: worker pull from master
8. POST node /api/profiles/{id}/launch (with --disk-cache-size=1048576)
9. Wait until browser ready (poll status, max 15s)
10. Generate session_id + view_token
11. Record session in DB
12. Return AcquireResponse
```

## Release Flow

```
1. Verify owner
2. POST node /api/profiles/{id}/stop
3. Worker push user-data-dir to master (exclude cache dirs)
4. Update session status=released
5. Decrement node sessions count
6. Update affinity
```

## TTL Expiry

Background task every 5s scans for expired sessions and auto-releases them.

---

## Task Breakdown

### Task 1: 项目脚手架 + 数据模型

创建 `browser-pool/` 项目结构：
- `pyproject.toml` + `requirements.txt`
- `app/__init__.py`, `app/main.py`, `app/config.py`, `app/models.py`, `app/database.py`
- Config: ROLE, MASTER_URL, MAX_GLOBAL_SESSIONS, MAX_NODE_SESSIONS, NODE_ADVERTISE_URL, PROFILE_STORAGE_DIR, TTL_DEFAULT, TTL_MAX, WORKER_PORT
- DB tables: consumer_profiles, sessions
- Health endpoint: GET /api/health

### Task 2: Consumer ↔ Profile 映射 + fingerprint_seed 派生

- `app/mapping.py`: get_or_create_profile, derive_fingerprint_seed, reset_consumer
- fingerprint_seed = int.from_bytes(sha256(consumer_id)[:4], 'big') % 2^31
- 持久化在 SQLite

### Task 3: 节点注册与健康管理

- `app/nodes.py`: NodeRegistry class
- 心跳注册、超时下线(30s)、亲和调度、容量管理
- Routes: POST /api/nodes/heartbeat, GET /api/nodes

### Task 4: Profile 数据存储与同步（master 端）

- `app/storage.py`: save/download/delete profile tar.gz
- Routes: GET/POST /internal/profiles/{id}/download|upload
- 存储路径: PROFILE_STORAGE_DIR/{profile_id}/userdata.tar.gz

### Task 5: Profile 数据同步（worker 端）

- `app/sync.py`: pull_profile, push_profile
- Exclude dirs: Cache, Code Cache, GPUCache, Service Worker/CacheStorage, BrowserMetrics, crashpad
- Worker routes: POST /internal/sync/pull, POST /internal/sync/push

### Task 6: 核心调度 — Acquire 流程

- `app/pool.py`: PoolManager.acquire()
- 完整 acquire 链路（映射→锁→限流→选节点→创建/更新profile→拉取数据→启动→等待就绪→返回）
- Route: POST /api/pool/acquire

### Task 7: Release + Renew + Reset

- POST /api/pool/release: stop → push data → release lock
- POST /api/pool/renew: extend TTL
- POST /api/pool/reset: release if active → delete profile → delete mapping

### Task 8: TTL 过期自动清理

- `app/ttl_watcher.py`: background task, 5s interval
- Auto-release expired sessions
- Orphan handling for unreachable nodes

### Task 9: Worker 端集成

- Worker FastAPI process (port 9001)
- Heartbeat loop (10s) to master
- Sync endpoints (pull/push)
- Reads current_sessions from local CloakBrowser-Manager /api/status

### Task 10: Web 仪表盘 — 后端 API

- Dashboard data APIs: /api/sessions, /api/stats, /api/mappings
- Admin actions: POST /api/sessions/{id}/stop
- View auth: GET /view/{session_id}?token=xxx
- VNC proxy: WS /api/view/{session_id}/vnc?token=xxx

### Task 11: Web 仪表盘 — React 前端

- Vite + React + Tailwind
- Dashboard: stats + sessions table + nodes list
- noVNC viewer (embedded + standalone /view/ page)
- 3s polling for live data

### Task 12: Docker Compose + 端到端测试

- docker-compose.yml: master + node-1 + node-2
- Dockerfile for browser-pool service
- E2E test: acquire → use → release → re-acquire (verify state) → concurrency limit → TTL expiry → reset → view URL
