# Database Schema

Browser Pool Service 使用 SQLite 数据库，路径由 `DB_PATH` 环境变量指定。

## 表结构

### profiles

管理共享的浏览器 profile 模板配置。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `profile_id` | TEXT PK | - | Profile 唯一 ID (UUID) |
| `name` | TEXT NOT NULL | - | 名称 |
| `fingerprint_seed` | INTEGER | NULL | 浏览器指纹种子 |
| `proxy` | TEXT | NULL | 代理地址 `http://user:pass@host:port` |
| `timezone` | TEXT | NULL | 时区，如 `America/New_York` |
| `locale` | TEXT | NULL | 语言区域，如 `en-US` |
| `platform` | TEXT | `windows` | 平台：`windows` / `macos` / `linux` |
| `user_agent` | TEXT | NULL | 自定义 User Agent |
| `screen_width` | INTEGER | `1920` | 屏幕宽度 |
| `screen_height` | INTEGER | `1080` | 屏幕高度 |
| `notes` | TEXT | NULL | 备注 |
| `created_at` | TEXT | `datetime('now')` | 创建时间 |
| `updated_at` | TEXT | `datetime('now')` | 更新时间 |

### consumer_profiles

Consumer 与 Profile 的 1:1 永久绑定关系。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `consumer_id` | TEXT PK | - | Consumer 唯一标识（由调用方传入） |
| `profile_id` | TEXT NOT NULL | - | 绑定的 Profile ID |
| `created_at` | TEXT | `datetime('now')` | 绑定时间 |

**规则：**
- 一个 consumer_id 永远对应同一个 profile_id
- `fingerprint_seed` 由 `hash(consumer_id)` 确定性派生
- `reset` 操作删除绑定，下次 acquire 创建新 profile

### sessions

活跃和历史的浏览器使用会话记录。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `session_id` | TEXT PK | - | Session 唯一 ID (UUID) |
| `consumer_id` | TEXT NOT NULL | - | 对应的 Consumer |
| `profile_id` | TEXT NOT NULL | - | 使用的 Profile |
| `owner` | TEXT NOT NULL | - | 持有者标识（用于 release/renew 权限验证） |
| `node_id` | TEXT NOT NULL | - | 运行在哪个节点 |
| `node_url` | TEXT NOT NULL | - | 节点 CBM 地址，如 `http://192.168.1.2:8080` |
| `view_token` | TEXT NOT NULL | - | VNC 查看 token（随 session 生成） |
| `status` | TEXT | `active` | 状态：`active` / `released` / `orphaned` |
| `expires_at` | TEXT NOT NULL | - | 过期时间 (ISO8601 UTC) |
| `created_at` | TEXT | `datetime('now')` | 创建时间 |

**状态流转：**
```
acquire → active
release/TTL 过期 → released
release 失败（节点不可达）→ orphaned
```

## 关系图

```
consumer_profiles         profiles                sessions
┌──────────────┐      ┌──────────────┐      ┌──────────────────┐
│ consumer_id ─┼──┐   │ profile_id   │   ┌──│ session_id       │
│ profile_id ──┼──┼──→│ name         │   │  │ consumer_id      │
│ created_at   │  │   │ fingerprint  │   │  │ profile_id ──────┼──→ profiles
└──────────────┘  │   │ proxy        │   │  │ owner            │
                  │   │ timezone     │   │  │ node_id          │
                  │   │ ...          │   │  │ node_url         │
                  │   └──────────────┘   │  │ view_token       │
                  │                      │  │ status           │
                  └──────────────────────┼──│ expires_at       │
                    (consumer → profile) │  │ created_at       │
                                         │  └──────────────────┘
                                         │
                                    (active session 
                                     = 浏览器正在运行)
```

## 内存状态（非持久化）

### NodeRegistry（master 进程内存）

| 字段 | 类型 | 说明 |
|------|------|------|
| `node_id` | str | 节点标识 |
| `url` | str | CBM 地址 |
| `max_sessions` | int | 节点最大并发 |
| `current_sessions` | int | 当前运行数 |
| `last_heartbeat` | float | 上次心跳时间戳 |
| `affinity` | dict[profile_id, timestamp] | 亲和记录：哪个 profile 最后在此节点使用 |

**节点超时：** 30 秒无心跳视为下线。

## 文件存储

### NFS Volume（`NFS_PROFILES_DIR`）

```
/nfs/profiles/
├── {profile_id_1}.tar.gz    # profile 1 的 user-data-dir 压缩包
├── {profile_id_2}.tar.gz    # profile 2 的 user-data-dir 压缩包
└── ...
```

**内容：** 每个 tar.gz 解压后是 Chromium 的 user-data-dir 目录（排除 Cache、Code Cache、GPUCache 等）。

**同步时机：**
- Acquire: 从 NFS 解压到 shared-volume
- Release: 从 shared-volume 打包覆盖写入 NFS

### Shared Volume（`LOCAL_PROFILES_DIR`）

```
/shared-profiles/
├── {profile_id_1}/          # 解压后的 user-data-dir（CBM 运行时读写）
│   ├── Default/
│   │   ├── Cookies
│   │   ├── Local Storage/
│   │   └── ...
│   └── ...
└── {profile_id_2}/
```

**CBM 挂载在 `/data/profiles`，看到同一份数据。**
