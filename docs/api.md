# Browser Pool Service API 文档

> Master 服务默认监听 `http://localhost:9000`

---

## 1. Pool 调度 API

### POST /api/pool/acquire

获取浏览器实例。自动完成 consumer→profile 绑定、节点选择、profile 创建/更新、数据同步、浏览器启动。

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| consumer_id | string | ✅ | Consumer 唯一标识 |
| owner | string | ✅ | 持有者标识（用于 release/renew 权限验证） |
| ttl | int | ❌ | Session 有效期（秒），默认 1800，最大 7200 |
| proxy | string | ❌ | 代理地址 |
| timezone | string | ❌ | 时区 |
| locale | string | ❌ | 语言区域 |
| platform | string | ❌ | 平台：windows/macos/linux |
| user_agent | string | ❌ | 自定义 UA |
| screen_width | int | ❌ | 屏幕宽度 |
| screen_height | int | ❌ | 屏幕高度 |

**响应 200：**
```json
{
  "session_id": "uuid",
  "consumer_id": "my-worker",
  "profile_id": "uuid",
  "cdp_url": "ws://node-1:8080/api/profiles/uuid/cdp",
  "view_url": "http://master:9000/view/session-id?token=xxx",
  "node": "node-1",
  "expires_at": "2026-06-17T01:00:00+00:00"
}
```

**错误：**
- `409` Profile is already in use by an active session
- `429` Global session limit reached
- `503` No available nodes
- `502` Node communication error
- `504` Browser did not start in time

---

### POST /api/pool/release

释放浏览器实例。停止浏览器 → 同步 user-data-dir → 释放锁。

**请求体：**
```json
{
  "session_id": "uuid",
  "owner": "worker-1"
}
```

**响应 200：** `{"ok": true}`

**错误：**
- `404` Session not found or already released
- `403` Not the session owner

---

### POST /api/pool/renew

延长 Session TTL。

**请求体：**
```json
{
  "session_id": "uuid",
  "owner": "worker-1"
}
```

**响应 200：**
```json
{
  "expires_at": "2026-06-17T01:30:00+00:00"
}
```

---

### POST /api/pool/reset

解绑 consumer，删除关联的 profile 数据。如有活跃 session 先自动 release。

**请求体：**
```json
{
  "consumer_id": "my-worker"
}
```

**响应 200：** `{"ok": true}`

---

## 2. 节点管理 API

### POST /api/nodes/heartbeat

Worker 节点心跳注册。每 10 秒调用一次。

**请求体：**
```json
{
  "node_id": "node-1",
  "url": "http://192.168.1.2:8080",
  "max_sessions": 5,
  "current_sessions": 2,
  "cpu_percent": 45.2,
  "memory_percent": 62.1,
  "disk_percent": 35.0
}
```

**响应 200：** `{"ok": true}`

---

### GET /api/nodes

获取所有注册节点列表。

**响应 200：**
```json
[
  {
    "node_id": "node-1",
    "url": "http://192.168.1.2:8080",
    "max_sessions": 5,
    "current_sessions": 2,
    "online": true,
    "last_heartbeat": "2026-06-17T10:00:00+00:00",
    "cpu_percent": 45.2,
    "memory_percent": 62.1,
    "disk_percent": 35.0
  }
]
```

---

### GET /api/nodes/{node_id}/profiles

获取指定节点上的所有 profile（代理转发到 CloakBrowser-Manager）。

**响应 200：** CloakBrowser-Manager `/api/profiles` 返回格式

---

### POST /api/nodes/{node_id}/profiles

在指定节点上创建 profile。未传的字段自动从全局默认值填充。

**请求体：** 与 CloakBrowser-Manager ProfileCreate 一致：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | ✅ | Profile 名称 |
| fingerprint_seed | int | ❌ | 指纹种子（不传则随机） |
| proxy | string | ❌ | 代理地址 |
| timezone | string | ❌ | 时区 |
| locale | string | ❌ | 语言区域 |
| platform | string | ❌ | 平台：windows/macos/linux |
| user_agent | string | ❌ | 自定义 UA |
| screen_width | int | ❌ | 屏幕宽度 |
| screen_height | int | ❌ | 屏幕高度 |
| gpu_vendor | string | ❌ | GPU 厂商 |
| gpu_renderer | string | ❌ | GPU 渲染器 |
| hardware_concurrency | int | ❌ | CPU 核心数 |
| humanize | bool | ❌ | 人性化行为模拟 |
| human_preset | string | ❌ | 人性化预设：default/careful |
| headless | bool | ❌ | 无头模式 |
| geoip | bool | ❌ | GeoIP 定位 |
| clipboard_sync | bool | ❌ | 剪贴板同步 |
| auto_launch | bool | ❌ | 自动启动 |
| color_scheme | string | ❌ | 颜色方案：light/dark/no-preference |
| launch_args | string[] | ❌ | 浏览器启动参数 |
| notes | string | ❌ | 备注 |
| tags | object[] | ❌ | 标签列表 `[{"tag": "work", "color": "#6366f1"}]` |

**响应 201：** CloakBrowser-Manager ProfileResponse

---

### POST /api/nodes/{node_id}/profiles/{profile_id}/launch

在节点上启动指定 profile 的浏览器。

**响应 200：** CloakBrowser-Manager LaunchResponse

---

### POST /api/nodes/{node_id}/profiles/{profile_id}/stop

在节点上停止指定 profile 的浏览器。

**响应 200：** `{"ok": true}`

---

## 3. 全局默认值 API

### GET /api/defaults

获取全局默认配置。Acquire 时未传的字段从此配置填充。

**响应 200：**
```json
{
  "proxy": null,
  "timezone": "Asia/Shanghai",
  "locale": "zh-CN",
  "platform": "windows",
  "user_agent": null,
  "screen_width": 1920,
  "screen_height": 1080,
  "notes": null,
  "updated_at": "2026-06-17T10:00:00"
}
```

---

### PUT /api/defaults

更新全局默认配置（仅传需要修改的字段）。

**请求体：**
```json
{
  "proxy": "http://user:pass@host:port",
  "timezone": "America/New_York"
}
```

**响应 200：** 更新后的完整默认值

---

## 4. 仪表盘 API

### GET /api/sessions

获取所有活跃 session 列表（含 TTL 剩余）。

**响应 200：**
```json
[
  {
    "session_id": "uuid",
    "consumer_id": "my-worker",
    "profile_id": "uuid",
    "owner": "worker-1",
    "node_id": "node-1",
    "node_url": "http://192.168.1.2:8080",
    "view_token": "xxx",
    "status": "active",
    "expires_at": "2026-06-17T01:00:00",
    "ttl_remaining": 1234
  }
]
```

---

### GET /api/sessions/running

获取所有运行中的浏览器实例（跨所有节点聚合）。

**响应 200：**
```json
[
  {
    "profile_id": "uuid",
    "name": "Profile Name",
    "node_id": "node-1",
    "status": "running"
  }
]
```

---

### GET /api/stats

全局统计信息。

**响应 200：**
```json
{
  "running_sessions": 3,
  "max_global_sessions": 10,
  "nodes": [...]
}
```

---

### GET /api/mappings

所有 consumer ↔ profile 映射关系。

---

### POST /api/sessions/{session_id}/stop

管理员强制停止指定 session。

**响应 200：** `{"ok": true}`

---

## 5. 实时查看

### GET /view/{session_id}?token=xxx

通过浏览器实时查看运行中的浏览器实例（noVNC 页面）。Token 随 session 释放自动失效。

### GET /view/browser/{node_id}/{profile_id}

管理员直接查看节点上运行的浏览器（无需 token）。

### WS /api/view/{session_id}/vnc?token=xxx

VNC WebSocket 代理（session 级别，需 token）。

### WS /api/view/browser/{node_id}/{profile_id}/vnc

VNC WebSocket 代理（管理员，无 token）。

---

## 6. 内部 API（Worker ↔ Master）

### GET /internal/profiles/{profile_id}/download

下载 profile 的 user-data-dir 压缩包。

### POST /internal/profiles/{profile_id}/upload

上传 profile 的 user-data-dir 压缩包。

### POST /internal/sync/pull (Worker 端 :9001)

Worker 从 master 拉取 profile 数据。

**请求体：**
```json
{
  "profile_id": "uuid",
  "master_url": "http://master:9000",
  "local_dir": "/shared-profiles/uuid"
}
```

### POST /internal/sync/push (Worker 端 :9001)

Worker 将 profile 数据推送回 master。

**请求体：**
```json
{
  "profile_id": "uuid",
  "master_url": "http://master:9000",
  "local_dir": "/shared-profiles/uuid"
}
```
