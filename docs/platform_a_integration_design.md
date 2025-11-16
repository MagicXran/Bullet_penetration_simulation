# 平台A集成改造方案 - 详细设计文档

**版本**: 1.0
**日期**: 2025-11-11
**状态**: 已实现

---

## 1. 改造目标

将当前LS-DYNA K文件参数化系统（平台B）与现有平台A进行HTTP通信集成，实现以下功能：

1. **平台A → 平台B**: 通过URL参数传递task_id，跳转到输入/输出页面
2. **平台B → 平台A**: 通过REST API上报任务状态（task-insert和task-update）
3. **向后兼容**: 保持原有独立使用模式完全可用

---

## 2. 架构设计

### 2.1 通信模式

```
┌─────────────┐                      ┌─────────────┐
│   平台 A    │                      │   平台 B    │
│  (外部系统)  │                      │  (本系统)   │
└─────────────┘                      └─────────────┘
       │                                    │
       │  ① GET /input.html?task_id=xxx   │
       │─────────────────────────────────→│
       │       (浏览器URL跳转)              │
       │                                    │
       │  ② POST /task-insert/            │
       │←─────────────────────────────────│
       │       (平台B主动调用)              │
       │                                    │
       │  ③ POST /task-update/            │
       │←─────────────────────────────────│
       │    (平台B周期性调用)               │
       │                                    │
       │  ④ GET /output.html?task_id=xxx  │
       │─────────────────────────────────→│
       │       (浏览器URL跳转)              │
       │                                    │
```

### 2.2 数据流

1. **用户在平台A点击"创建仿真任务"**
   - 平台A生成task_id
   - 浏览器跳转到: `http://platformB.com/input.html?task_id=xxx`

2. **平台B输入页面加载**
   - 从URL获取task_id
   - 调用`GET /api/task/{task_id}`查询任务
   - 如果存在：展示已有参数
   - 如果不存在：显示空表单

3. **用户填写参数并提交**
   - 前端调用`POST /api/task/submit`
   - 后端执行：
     - 创建/更新任务记录（SQLite）
     - 立即调用平台A的`/task-insert/`接口（status=0）
     - 生成K文件（status=2运行中）
     - 完成后更新状态（status=3已完成）
   - 跳转到`output.html?task_id=xxx`

4. **平台B输出页面展示结果**
   - 轮询`GET /api/task/{task_id}`查询状态
   - 显示实时状态（等待中/运行中/已完成/失败）
   - 完成后提供K文件下载链接

5. **后台调度器周期性同步**
   - 每5秒扫描未同步任务
   - 调用平台A的`/task-update/`接口
   - 同步成功后标记`platform_a_synced=1`
   - 失败则重试（最多3次）

---

## 3. 数据库设计

### 3.1 任务表结构

```sql
CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,              -- 任务ID（由平台A传递）
    input_params TEXT NOT NULL,             -- 输入参数（JSON格式）
    output_file_path TEXT,                  -- 输出文件路径
    status INTEGER NOT NULL DEFAULT 0,      -- 任务状态 (0-5)
    submission_time TEXT,                   -- 提交时间
    start_time TEXT,                        -- 开始时间
    end_time TEXT,                          -- 结束时间
    error_message TEXT,                     -- 错误信息
    platform_a_synced INTEGER DEFAULT 0,    -- 是否已同步到平台A
    sync_retry_count INTEGER DEFAULT 0,     -- 同步重试次数
    created_at TEXT NOT NULL,               -- 创建时间
    updated_at TEXT NOT NULL                -- 更新时间
);

CREATE INDEX idx_status ON tasks(status);
CREATE INDEX idx_platform_a_synced ON tasks(platform_a_synced, status);
CREATE INDEX idx_created_at ON tasks(created_at DESC);
```

### 3.2 状态码定义

| 状态码 | 名称     | 说明                     |
|--------|----------|--------------------------|
| 0      | 待提交   | 任务已创建但未提交       |
| 1      | 排队中   | 任务已提交，等待执行     |
| 2      | 运行中   | K文件正在生成            |
| 3      | 已完成   | 任务成功完成             |
| 4      | 失败     | 任务执行失败             |
| 5      | 中止     | 任务被手动中止           |

---

## 4. 后端实现

### 4.1 模块划分

```
backend/
├── database.py                 # 数据库操作层（SQLite封装）
├── task_manager.py             # 任务管理核心逻辑
├── platform_sync.py            # 平台A通信客户端
├── task_sync_scheduler.py      # 后台调度器（APScheduler）
├── app.py                      # FastAPI主应用（新增API）
└── config.json                 # 配置文件（扩展平台A配置）
```

### 4.2 新增API接口

#### 4.2.1 查询任务详情

```http
GET /api/task/{task_id}

Response:
{
    "task_id": "string",
    "input_params": { /* 参数对象 */ },
    "output_file_path": "string",
    "status": 0-5,
    "status_name": "string",
    "submission_time": "ISO datetime",
    "start_time": "ISO datetime",
    "end_time": "ISO datetime",
    "error_message": "string",
    "platform_a_synced": boolean,
    "created_at": "ISO datetime",
    "updated_at": "ISO datetime"
}
```

#### 4.2.2 提交任务

```http
POST /api/task/submit

Request Body:
{
    "task_id": "string",
    "params": {
        "velocity_z": 1600.0,
        "bullet_yield_stress": 1000.0,
        "target_yield_stress": 800.0,
        "friction_static": 0.25,
        "friction_dynamic": 0.18,
        "simulation_endtime": 30.0
    }
}

Response:
{
    "success": true,
    "task_id": "string",
    "filename": "string",
    "file_path": "string",
    "message": "string",
    "warnings": [],
    "status": 3
}
```

### 4.3 配置文件扩展

在`backend/config.json`中添加：

```json
{
    "platform_a": {
        "enabled": true,
        "base_url": "http://platform-a.example.com",
        "task_insert_endpoint": "/simulApi/web-app/task-insert/",
        "task_update_endpoint": "/simulApi/web-app/task-update/",
        "timeout": 10,
        "sync_interval": 5
    }
}
```

### 4.4 平台A接口调用

#### 4.4.1 任务插入接口

```http
POST {base_url}/simulApi/web-app/task-insert/

Request:
{
    "task_id": "string",
    "submission_time": "2025-11-11T10:00:00",
    "task_status": 0
}

Response:
{
    "code": 0,
    "msg": "string"
}
```

#### 4.4.2 任务更新接口

```http
POST {base_url}/simulApi/web-app/task-update/

Request:
{
    "task_id": "string",
    "start_time": "2025-11-11T10:00:01",
    "end_time": "2025-11-11T10:00:05",
    "error_message": "string",
    "task_status": 3
}

Response:
{
    "code": 0,
    "msg": "string"
}
```

---

## 5. 前端实现

### 5.1 页面结构

```
frontend/
├── index.html          # 原有独立使用页面（保持不变）
├── input.html          # 平台A集成 - 输入页面（新增）
├── output.html         # 平台A集成 - 输出页面（新增）
├── app.js              # 原有JS逻辑（保持不变）
└── style.css           # 样式文件
```

### 5.2 输入页面逻辑 (input.html)

1. 从URL获取`task_id`参数
2. 调用`GET /api/task/{task_id}`查询任务
3. 如果任务存在：填充表单（可编辑）
4. 如果任务不存在：显示空表单
5. 用户填写完成后点击"提交计算"
6. 调用`POST /api/task/submit`提交任务
7. 提交成功后跳转到`output.html?task_id=xxx`

### 5.3 输出页面逻辑 (output.html)

1. 从URL获取`task_id`参数
2. 调用`GET /api/task/{task_id}`查询任务
3. 显示任务状态：
   - 待提交/排队中：显示等待动画
   - 运行中：显示进度动画
   - 已完成：显示下载按钮
   - 失败：显示错误信息
4. 轮询机制：每3秒查询一次状态，直到完成或失败
5. 完成后停止轮询，显示K文件下载链接

---

## 6. 部署配置

### 6.1 依赖安装

需要安装额外的Python库：

```bash
pip install requests apscheduler
```

### 6.2 配置步骤

1. **编辑`backend/config.json`**
   ```json
   {
       "platform_a": {
           "enabled": true,
           "base_url": "http://192.168.1.100:8080",
           "task_insert_endpoint": "/simulApi/web-app/task-insert/",
           "task_update_endpoint": "/simulApi/web-app/task-update/",
           "timeout": 10,
           "sync_interval": 5
       }
   }
   ```

2. **启动后端服务**
   ```bash
   cd backend
   python app.py
   ```

3. **平台A配置跳转URL**
   - 输入页面: `http://platformB.com:8000/input.html?task_id={task_id}`
   - 输出页面: `http://platformB.com:8000/output.html?task_id={task_id}`

### 6.3 禁用平台A集成（独立模式）

如果不需要与平台A集成，只需设置：

```json
{
    "platform_a": {
        "enabled": false
    }
}
```

此时：
- 调度器不会启动
- `input.html`和`output.html`仍可独立使用
- 原有`index.html`完全不受影响

---

## 7. 向后兼容性

### 7.1 保持原有功能

- `index.html`: 原有单页应用，完全不变
- `/api/generate`: 原有K文件生成接口，完全不变
- `/api/files`: 原有文件管理接口，完全不变
- 动画生成功能：完全不变

### 7.2 新增功能

- `input.html`: 平台A集成输入页面
- `output.html`: 平台A集成输出页面
- `/api/task/{task_id}`: 查询任务接口
- `/api/task/submit`: 提交任务接口
- 后台调度器：自动同步任务状态到平台A

---

## 8. 错误处理

### 8.1 网络错误

- 平台A不可达：记录日志，增加重试次数，超过3次后放弃
- 超时：默认10秒超时，可配置
- 返回非200状态码：记录错误信息到`error_message`字段

### 8.2 数据验证

- task_id格式验证：8-128字符，仅允许字母数字下划线连字符
- 参数范围验证：使用原有`ParameterValidator`
- 任务不存在：返回404错误，提示用户先创建任务

### 8.3 并发安全

- SQLite使用单连接模式，自动处理并发
- 调度器使用独立线程，与FastAPI请求处理隔离
- 数据库操作使用上下文管理器，确保事务完整性

---

## 9. 监控与日志

### 9.1 日志输出

- 应用启动/关闭事件
- 调度器启动/停止
- 每次同步操作（成功/失败）
- HTTP请求错误

### 9.2 调试信息

- 任务状态变更记录在数据库
- 同步重试次数记录
- 错误信息完整记录

---

## 10. 总结

### 10.1 关键设计原则

1. **第一性原理**: 一张表解决所有任务状态管理
2. **KISS原则**: 简单的重试机制，不搞复杂的消息队列
3. **SOLID原则**: 模块分离，单一职责（database/task_manager/platform_sync/scheduler）
4. **向后兼容**: 原有功能完全不变，新功能独立添加
5. **配置化**: 所有可变参数都在config.json中

### 10.2 文件清单

**新增后端文件**:
- `backend/database.py` (369行)
- `backend/task_manager.py` (237行)
- `backend/platform_sync.py` (189行)
- `backend/task_sync_scheduler.py` (180行)

**修改后端文件**:
- `backend/app.py` (新增150行代码)
- `backend/config.json` (新增7行配置)

**新增前端文件**:
- `frontend/input.html` (396行)
- `frontend/output.html` (457行)

**总代码量**: 约2000行（含注释和文档）

### 10.3 下一步工作

1. 单元测试编写
2. 集成测试（与实际平台A联调）
3. 性能测试（大量并发任务）
4. 监控仪表盘（可选）

---

**文档结束**
