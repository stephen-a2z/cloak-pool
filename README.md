# Browser Pool Service

CDP 浏览器池调度服务。为多个 Playwright worker 提供统一的浏览器实例分配，支持 consumer 绑定 profile、跨节点 user-data-dir 同步、并发限制和实时查看。

## 架构

```
Consumer (Playwright Worker)
    │
    │ POST master:9000/api/pool/acquire {consumer_id, owner, ttl, proxy?...}
    ▼
Browser Pool Service (master :9000)
    ├── consumer_id → profile_id 映射 (1:1 永久绑定)
    ├── fingerprint_seed = hash(consumer_id) 确定性派生
    ├── user-data-dir 压缩包集中存储
    ├── 双层并发限制 (每节点 M + 全局 N)
    ├── 亲和调度 (优先上次使用该 profile 的节点)
    └── Web 仪表盘 + noVNC 实时查看
         │
    ┌────┴────┐
    ▼         ▼
 Node A      Node B    (CloakBrowser-Manager :8080)
```

Consumer 直连节点 CDP：`ws://node-x:8080/api/profiles/{id}/cdp`

## 快速开始

### Docker Compose

```bash
docker compose up --build
```

启动后：
- Master 仪表盘：http://localhost:9000
- Node 1 CloakBrowser-Manager：http://localhost:8080
- Node 2 CloakBrowser-Manager：http://localhost:8082

### 本地开发

```bash
# Master
cd browser-pool
pip install -r requirements.txt
ROLE=master DB_PATH=./data/pool.db PROFILE_STORAGE_DIR=./data/profiles \
  uvicorn app.main:app --port 9000

# Worker (另一个终端)
ROLE=worker MASTER_URL=http://localhost:9000 NODE_ID=local \
  NODE_ADVERTISE_URL=http://localhost:8080 \
  uvicorn app.worker:worker_app --port 9001

# 前端开发
cd frontend && npm install && npm run dev
```

## API

### Pool 调度

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/pool/acquire` | 获取浏览器实例 |
| POST | `/api/pool/release` | 释放浏览器实例 |
| POST | `/api/pool/renew` | 延长 TTL |
| POST | `/api/pool/reset` | 解绑 consumer，删除 profile |

### 节点管理

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/nodes/heartbeat` | Worker 心跳注册 |
| GET | `/api/nodes` | 节点列表 |

### 仪表盘

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/sessions` | 活跃 session 列表 |
| GET | `/api/stats` | 全局统计 |
| GET | `/api/mappings` | consumer ↔ profile 映射 |
| POST | `/api/sessions/{id}/stop` | 管理员强制停止 |
| GET | `/view/{session_id}?token=xxx` | 实时查看浏览器画面 |

## 使用示例

### Acquire → 使用 → Release

```python
import httpx
from playwright.async_api import async_playwright

# 1. Acquire
r = httpx.post("http://master:9000/api/pool/acquire", json={
    "consumer_id": "my-worker-uuid",
    "owner": "worker-1",
    "ttl": 1800,
    "proxy": "http://user:pass@proxy:8080",
    "timezone": "America/New_York",
})
data = r.json()
# {
#   "session_id": "xxx",
#   "consumer_id": "my-worker-uuid",
#   "profile_id": "yyy",
#   "cdp_url": "ws://node-1:8080/api/profiles/yyy/cdp",
#   "view_url": "http://master:9000/view/xxx?token=zzz",
#   "node": "node-1",
#   "expires_at": "2026-06-17T01:00:00+00:00"
# }

# 2. 连接 CDP 执行任务
async with async_playwright() as pw:
    browser = await pw.chromium.connect_over_cdp(
        data["cdp_url"].replace("ws://", "http://")
    )
    page = browser.contexts[0].pages[0]
    await page.goto("https://example.com")
    # ... 执行自动化任务 ...

# 3. Release (浏览器停止 + user-data-dir 同步回 master)
httpx.post("http://master:9000/api/pool/release", json={
    "session_id": data["session_id"],
    "owner": "worker-1",
})
```

### 分享实时画面

Acquire 返回的 `view_url` 可以直接分享给他人，无需额外认证：

```
http://master:9000/view/xxx?token=zzz
```

Token 随 session 释放自动失效。

## 核心特性

- **Consumer 绑定 Profile** — 同一 consumer_id 永远使用同一份浏览器数据（cookies、localStorage），保持登录态
- **确定性指纹** — fingerprint_seed 由 consumer_id 派生，跨节点指纹一致
- **跨节点数据同步** — acquire 时从 master 全量拉取 user-data-dir，release 时全量推回
- **双层并发限制** — 每节点上限 + 全局上限，防止资源耗尽
- **亲和调度** — 优先在上次使用该 profile 的节点启动，减少数据传输
- **TTL 自动回收** — 超时未 release 的 session 自动释放，防止僵尸浏览器
- **Cache 控制** — 启动参数限制 cache 大小 + release 时清理，保持 user-data-dir 精简（30-60MB）
- **实时查看** — 通过 noVNC 在浏览器中查看运行中的浏览器实例

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ROLE` | master | `master` 或 `worker` |
| `MASTER_URL` | http://localhost:9000 | Master 地址 |
| `NODE_ID` | node-1 | 节点标识 |
| `NODE_ADVERTISE_URL` | http://localhost:8080 | 节点 CloakBrowser-Manager 地址 |
| `MAX_GLOBAL_SESSIONS` | 10 | 全局最大并发 |
| `MAX_NODE_SESSIONS` | 5 | 每节点最大并发 |
| `PROFILE_STORAGE_DIR` | /data/profiles | Profile 数据存储目录 |
| `DB_PATH` | /data/browser-pool.db | SQLite 数据库路径 |
| `TTL_DEFAULT` | 1800 | 默认 TTL (秒) |
| `TTL_MAX` | 7200 | 最大 TTL (秒) |
| `WORKER_PORT` | 9001 | Worker 监听端口 |

## 测试

```bash
# 单元测试
pip install pytest pytest-asyncio
pytest tests/test_ttl_watcher.py -v

# E2E 测试 (需要 docker compose up)
pytest tests/test_e2e.py -v
```

## 技术栈

- **Backend**: Python + FastAPI
- **Frontend**: React + Tailwind CSS + Vite
- **Database**: SQLite (aiosqlite)
- **Browser Engine**: CloakBrowser-Manager (外部服务)
- **VNC Viewer**: noVNC
