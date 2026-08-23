# App与平台交互接口说明

> 版本: 1.5.0
> 更新日期: 2025-12-26

---

## 接口总览

| 方向 | 接口 | 说明 |
|------|------|------|
| App → 平台 | `POST /api/tasks/{task_id}` | 提交参数+注册回调 |
| App → 平台 | `POST /api/tasks/{task_id}/heartbeat` | 心跳上报 |
| 平台 → App | `POST {callback_url}` | 触发执行 |

---

## 编码规范

### code 状态码

| code | 含义 | 说明 |
|------|------|------|
| 2000 | 成功 | 操作成功 |
| 4001 | 并发已满 | 许可证不足，无法执行 |
| 4003 | 参数错误 | 请求参数不合法 |
| 5000 | 服务器错误 | 内部异常 |

### status 任务状态

| status | 名称 | 含义 |
|--------|------|------|
| 0 | 任务就绪 | 任务已创建，等待执行 |
| 1 | 执行中 | App正在执行任务 |
| 2 | 已完成 | 任务成功完成（终态） |
| 3 | 已失败 | 任务失败（终态） |

> **终态说明**：status=2 和 status=3 是终态，不可再转换

---

## 接口详情

### 1. 提交参数（App → 平台）

```http
POST /api/tasks/{task_id}
Content-Type: application/json
```

**请求**
```json
{
    "datas": { 
    	"task_id": "xxx",
        "status": 0,
    	"message": "任务就绪"
    },
    "callback_url": "http://192.168.1.100:8080/api/execute"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| datas | object | 是 | 仿真参数 |
| callback_url | string | 是 | App回调地址 |

**响应 - 执行成功**
```json
{
    "code": 2000,
    "message": "xxx"
}
```

---

### 2. 心跳上报（App → 平台）

```http
POST /api/tasks/{task_id}/heartbeat
Content-Type: application/json
```

**请求**
```json
{
    "datas": { 
        "counter": 1,
    	"task_id": "xxx",
        "status": 0,
    	"message": "任务就绪"
    },
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| counter | int | 是 | 心跳计数器，1→30000循环 |

**响应**
```json
{
    "code": 2000,
    "message": "OK",
    "received_at": "2025-12-25T10:06:15Z"
}
```

> **心跳规则**：每30秒发送一次，counter从1递增到30000，然后重新从1开始

---

### 3. 标记完成/失败（App → 平台）

```http
POST /api/tasks/{task_id}
Content-Type: application/json
```

**完成**/**失败**

```json
 "datas": { 
    	"task_id": "xxx",
        "status": 2/3,
    	"message": "任务ok/fail"
    },
```



**响应**
```json
{
    "code": 2000,
    "message": "OK"
}
```

---

### 4. 触发执行（平台 → App）

```http
POST {callback_url}
Content-Type: application/json
```

**请求**
```json
{
   "task_id": "xxx",
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| task_id | string | 任务ID |

**响应 - 接受**
```json
{
    "code": 2000,
    "message": "任务已开始执行"
}
```

**响应 - 拒绝**
```json
{
    "code": 4001,
    "message": "商业软件许可证已满(2/2)，无法执行"
}
```

> 拒绝 → 任务直接标记失败，不重试

---

## 实现状态

> 更新日期: 2026-01-09

### 已实现的功能

| 模块 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 平台通知器 | `backend/platform_notifier.py` | ✅ | 注册任务、发送心跳、完成通知 |
| 心跳管理器 | `backend/heartbeat_manager.py` | ✅ | 每30秒心跳，counter 1-30000循环 |
| 回调端点 | `backend/app.py` | ✅ | `POST /api/platform/callback` |
| 数据库扩展 | `backend/database.py` | ✅ | platform_api_url, callback_url, heartbeat_counter |
| 前端适配 | `frontend/app.js` | ✅ | URL参数 `?task_id=xxx` 检测 |
| 配置文件 | `backend/config.json` | ✅ | platform_integration 配置块 |

### 状态映射（内部 → 对外）

| 内部状态 | 值 | 对外状态 | 值 |
|---------|---|---------|---|
| PENDING | 0 | 任务就绪 | 0 |
| QUEUED | 1 | 任务就绪 | 0 |
| GENERATING | 2 | 执行中 | 1 |
| COMPUTING | 6 | 执行中 | 1 |
| POSTPROCESSING | 7 | 执行中 | 1 |
| COMPLETED | 3 | 已完成 | 2 |
| FAILED | 4 | 已失败 | 3 |
| ABORTED | 5 | 已失败 | 3 |

### 配置示例

```json
{
  "platform_integration": {
    "enabled": false,
    "platform_api_url": "http://platform.company.com/api",
    "callback_base_url": "http://192.168.1.100:8000",
    "callback_endpoint": "/api/platform/callback",
    "max_concurrent_tasks": 2,
    "heartbeat_interval_seconds": 30,
    "request_timeout_seconds": 10
  }
}
```

### 使用说明

**独立模式**（默认）：
- `enabled: false`
- 用户访问 `index.html`，填写参数，提交后自动执行

**平台模式**：
- `enabled: true`
- 修改 `platform_api_url` 为实际平台地址
- 修改 `callback_base_url` 为App可访问地址
- 平台跳转 `index.html?task_id=xxx`
- 用户填写参数，提交后等待平台回调触发执行
