# LS-DYNA 子弹穿甲仿真系统 - 详细设计文档

**版本**: 3.0
**日期**: 2025-12-14
**状态**: 生产就绪

---

## 1. 系统概述

本系统是一个**LS-DYNA K文件参数化生成平台**，支持两种运行模式：
- **独立模式 (Standalone)**: 用户通过Web界面直接生成K文件
- **平台A集成模式 (Platform A)**: 与外部仿真管理平台集成，支持任务同步

### 1.1 技术栈

| 层级 | 技术选型 |
|------|----------|
| **前端** | HTML5 + CSS3 + JavaScript ES6 + Bootstrap 5 |
| **后端** | Python 3.11 + FastAPI + Pydantic |
| **数据库** | SQLite (单文件存储) |
| **定时任务** | APScheduler (BackgroundScheduler) |
| **热重载** | Uvicorn + watchfiles |

---

## 2. 日志信息解读

### 2.1 APScheduler 日志解析

```log
INFO:apscheduler.executors.default:Job "同步未同步任务到平台A
(trigger: interval[0:00:05], next run at: 2025-12-14 22:26:45 CST)"
executed successfully
```

**含义分解**：

| 组件 | 说明 |
|------|------|
| `apscheduler.executors.default` | APScheduler的默认执行器（线程池执行器） |
| `Job "同步未同步任务到平台A"` | 任务名称（在代码中定义） |
| `trigger: interval[0:00:05]` | 触发器类型：间隔触发器，每5秒执行一次 |
| `next run at: 2025-12-14 22:26:45 CST` | 下次执行时间 |
| `executed successfully` | 本次执行成功 |

**对应代码位置**: `backend/task_sync_scheduler.py:82-89`

```python
self.scheduler.add_job(
    func=self._sync_unsynced_tasks,  # 执行函数
    trigger=IntervalTrigger(seconds=5),  # 5秒间隔
    id='sync_tasks',
    name='同步未同步任务到平台A',  # 日志中显示的名称
    replace_existing=True
)
```

### 2.2 watchfiles 日志解析

```log
INFO:watchfiles.main:7 changes detected
```

**含义**：
- `watchfiles` 是 Uvicorn 的文件监控库
- 检测到7个文件变化（代码、配置等）
- 用于开发模式下的**热重载**（自动重启服务器）

**触发条件**：修改了 `backend/` 或 `frontend/` 目录下的任何文件

**注意**：生产环境应使用 `uvicorn app:app --host 0.0.0.0 --port 8000` 而非 `--reload`

---

## 3. 系统架构图

### 3.1 整体架构

```mermaid
flowchart TB
    subgraph 用户层
        User[用户浏览器]
    end

    subgraph 前端层
        IndexHtml[index.html<br/>独立模式]
        InputHtml[input.html<br/>平台A输入页]
        OutputHtml[output.html<br/>平台A输出页]
    end

    subgraph 后端层
        FastAPI[FastAPI Server<br/>:8000]
        KEngine[KFileEngine<br/>K文件生成引擎]
        TaskQueue[TaskQueue<br/>任务队列]
        TaskManager[TaskManager<br/>任务管理器]
        Scheduler[APScheduler<br/>定时任务调度器]
        SyncClient[PlatformASyncClient<br/>平台A同步客户端]
    end

    subgraph 数据层
        SQLite[(SQLite<br/>tasks.db)]
        Templates[模板文件<br/>templates/1.k]
        Generated[生成目录<br/>generated/]
    end

    subgraph 外部系统
        PlatformA[平台A<br/>外部仿真管理系统]
    end

    User --> IndexHtml
    User --> InputHtml
    User --> OutputHtml

    IndexHtml --> FastAPI
    InputHtml --> FastAPI
    OutputHtml --> FastAPI

    FastAPI --> KEngine
    FastAPI --> TaskQueue
    FastAPI --> TaskManager

    TaskQueue --> TaskManager
    TaskQueue --> KEngine

    Scheduler --> TaskManager
    Scheduler --> SyncClient

    TaskManager --> SQLite
    KEngine --> Templates
    KEngine --> Generated

    SyncClient --> PlatformA
```

### 3.2 模块职责说明

| 模块 | 文件 | 职责 |
|------|------|------|
| **FastAPI** | `app.py` | HTTP API接口，请求路由 |
| **KFileEngine** | `k_engine.py` | K文件参数替换和生成 |
| **TaskQueue** | `task_queue.py` | 任务排队和顺序执行 |
| **TaskManager** | `task_manager.py` | 任务CRUD和状态管理 |
| **Database** | `database.py` | SQLite数据访问层 |
| **Scheduler** | `task_sync_scheduler.py` | APScheduler定时任务 |
| **SyncClient** | `platform_sync.py` | 平台A HTTP通信 |

---

## 4. 前后端交互流程图

### 4.1 独立模式 (Standalone) 流程

```mermaid
sequenceDiagram
    autonumber
    participant User as 用户
    participant Index as index.html
    participant API as FastAPI
    participant Engine as KFileEngine
    participant DB as SQLite
    participant FS as 文件系统

    User->>Index: 1. 访问 localhost:8000
    Index->>API: 2. GET /api/parameters
    API-->>Index: 3. 返回参数定义

    User->>Index: 4. 填写参数并点击"生成K文件"
    Index->>API: 5. POST /api/generate

    Note over API: 验证参数
    API->>Engine: 6. 加载模板 templates/1.k
    Engine->>Engine: 7. 替换6个参数
    Engine->>FS: 8. 写入 generated/*.k

    API->>DB: 9. 创建任务记录<br/>source='standalone'
    DB-->>API: 10. 返回task_id

    API-->>Index: 11. 返回结果<br/>{success, filename, task_id}
    Index->>User: 12. 显示成功消息

    User->>Index: 13. 点击"下载"
    Index->>API: 14. GET /api/download/{filename}
    API->>FS: 15. 读取K文件
    FS-->>API: 16. 文件内容
    API-->>Index: 17. FileResponse
    Index->>User: 18. 浏览器下载文件
```

### 4.2 平台A集成模式 流程

```mermaid
sequenceDiagram
    autonumber
    participant PlatformA as 平台A
    participant User as 用户
    participant Input as input.html
    participant Output as output.html
    participant API as FastAPI
    participant Queue as TaskQueue
    participant Engine as KFileEngine
    participant DB as SQLite
    participant Scheduler as APScheduler
    participant Sync as SyncClient

    Note over PlatformA,User: === 阶段1: 用户填写参数 ===

    PlatformA->>User: 1. 跳转到 input.html?task_id=xxx
    User->>Input: 2. 访问输入页面
    Input->>API: 3. GET /api/task/{task_id}
    API->>DB: 4. 查询任务
    DB-->>API: 5. 任务不存在
    API-->>Input: 6. 404 (显示空表单)

    User->>Input: 7. 填写参数并点击"保存参数"
    Input->>API: 8. POST /api/task/save

    Note over API,DB: 创建任务记录
    API->>DB: 9. INSERT task<br/>source='platform_a'<br/>status=0
    DB-->>API: 10. 成功
    API-->>Input: 11. {success, status=0}

    Note over PlatformA,Sync: === 阶段2: 平台A触发执行 ===

    PlatformA->>API: 12. POST /api/task/{task_id}/execute
    API->>DB: 13. 查询任务状态
    DB-->>API: 14. status=0

    API->>Queue: 15. enqueue(task_id)
    Queue->>DB: 16. UPDATE status=1 (排队中)
    Queue-->>API: 17. {queue_position: 1}
    API-->>PlatformA: 18. {status=1, queue_position=1}

    Note over Queue,Engine: === 阶段3: 任务执行 ===

    Queue->>Queue: 19. Worker取出任务
    Queue->>DB: 20. UPDATE status=2 (执行中)
    Queue->>Engine: 21. 生成K文件
    Engine->>Engine: 22. 参数替换
    Engine-->>Queue: 23. 返回output_path
    Queue->>DB: 24. UPDATE status=3<br/>output_file_path=xxx

    Note over Scheduler,PlatformA: === 阶段4: 后台同步 ===

    loop 每5秒执行
        Scheduler->>DB: 25. 查询未同步任务<br/>WHERE source='platform_a'<br/>AND synced=0
        DB-->>Scheduler: 26. 返回任务列表

        alt 有未同步任务
            Scheduler->>Sync: 27. sync_task_status(task)
            Sync->>PlatformA: 28. POST /task-update/
            PlatformA-->>Sync: 29. {code: 0}
            Sync-->>Scheduler: 30. 同步成功
            Scheduler->>DB: 31. UPDATE synced=1
        end
    end

    Note over User,Output: === 阶段5: 用户查看结果 ===

    User->>Output: 32. 访问 output.html?task_id=xxx

    loop 轮询直到完成
        Output->>API: 33. GET /api/task/{task_id}
        API->>DB: 34. 查询任务
        DB-->>API: 35. 返回任务详情
        API-->>Output: 36. {status, output_file_path}
    end

    User->>Output: 37. 点击"下载K文件"
    Output->>API: 38. GET /api/download/{filename}
    API-->>Output: 39. FileResponse
    Output->>User: 40. 文件下载
```

---

## 5. 定时同步机制详解

### 5.1 同步流程图

```mermaid
flowchart TD
    Start([定时器触发<br/>每5秒]) --> Query[查询未同步任务<br/>source='platform_a'<br/>synced=0<br/>retry_count < 3]

    Query --> HasTask{有未同步任务?}

    HasTask -->|否| End([等待下次触发])

    HasTask -->|是| Loop[遍历任务列表]

    Loop --> GetTask[获取任务详情]

    GetTask --> CheckStatus{任务状态}

    CheckStatus -->|status=0| Insert[调用 task-insert API]
    CheckStatus -->|status>0| Update[调用 task-update API]

    Insert --> CallAPI[HTTP POST 到平台A]
    Update --> CallAPI

    CallAPI --> Success{调用成功?}

    Success -->|是| MarkSynced[标记 synced=1]
    MarkSynced --> NextTask[下一个任务]

    Success -->|否| IncrRetry[retry_count += 1]
    IncrRetry --> CheckRetry{重试次数 >= 3?}

    CheckRetry -->|是| LogError[记录错误日志<br/>放弃同步]
    CheckRetry -->|否| NextTask

    LogError --> NextTask

    NextTask --> MoreTask{还有任务?}
    MoreTask -->|是| Loop
    MoreTask -->|否| End
```

### 5.2 数据隔离机制

```mermaid
flowchart LR
    subgraph 任务来源
        Standalone[独立任务<br/>source='standalone']
        PlatformA[平台A任务<br/>source='platform_a']
    end

    subgraph 同步过滤器
        Filter["SQL WHERE条件:<br/>source = 'platform_a'<br/>AND synced = 0<br/>AND retry_count < 3"]
    end

    subgraph 同步行为
        Sync[同步到平台A]
        NoSync[不同步]
    end

    Standalone --> Filter
    PlatformA --> Filter

    Filter -->|匹配| Sync
    Filter -->|不匹配| NoSync

    style Standalone fill:#90EE90
    style PlatformA fill:#87CEEB
    style NoSync fill:#FFB6C1
```

**关键代码** (`backend/database.py:302-325`):

```python
def get_unsynced_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
    """获取未同步任务 - 只返回platform_a来源的任务"""
    cursor.execute("""
        SELECT * FROM tasks
        WHERE platform_a_synced = 0
          AND source = 'platform_a'  -- 关键过滤条件
          AND sync_retry_count < 3
        ORDER BY updated_at ASC
        LIMIT ?
    """, (limit,))
```

---

## 6. 任务状态机

### 6.1 状态流转图

```mermaid
stateDiagram-v2
    [*] --> 待执行: 用户保存参数

    待执行 --> 排队中: 平台A调用 execute
    待执行 --> 已完成: 独立模式直接生成

    排队中 --> 执行中: Worker取出任务

    执行中 --> 已完成: K文件生成成功
    执行中 --> 失败: 生成出错
    执行中 --> 失败: 超时 (>5分钟)

    失败 --> 排队中: 重试 (force=true)
    已完成 --> 排队中: 重试 (force=true)

    note right of 待执行: status=0
    note right of 排队中: status=1
    note right of 执行中: status=2
    note right of 已完成: status=3
    note right of 失败: status=4
```

### 6.2 状态码定义

| 状态码 | 名称 | 英文 | 说明 | 同步行为 |
|--------|------|------|------|----------|
| 0 | 待执行 | pending | 参数已保存，等待触发 | 调用 task-insert |
| 1 | 排队中 | queued | 已加入队列，等待执行 | 调用 task-update |
| 2 | 执行中 | running | K文件正在生成 | 调用 task-update |
| 3 | 已完成 | completed | 成功生成K文件 | 调用 task-update |
| 4 | 失败 | failed | 生成失败 | 调用 task-update |
| 5 | 已中止 | aborted | 手动中止（预留） | 调用 task-update |

---

## 7. 数据库设计

### 7.1 ER图

```mermaid
erDiagram
    TASKS {
        TEXT task_id PK "任务ID (主键)"
        TEXT source "来源: standalone/platform_a"
        TEXT input_params "输入参数 (JSON)"
        TEXT output_file_path "输出文件路径"
        INTEGER status "状态码 (0-5)"
        TEXT submission_time "提交时间"
        TEXT queued_at "入队时间"
        TEXT start_time "开始时间"
        TEXT end_time "结束时间"
        TEXT error_message "错误信息"
        INTEGER platform_a_synced "是否已同步"
        INTEGER sync_retry_count "同步重试次数"
        TEXT created_at "创建时间"
        TEXT updated_at "更新时间"
    }
```

### 7.2 索引设计

| 索引名 | 字段 | 用途 |
|--------|------|------|
| `idx_status` | `status` | 按状态查询任务 |
| `idx_platform_a_synced` | `platform_a_synced, status` | 查询未同步任务 |
| `idx_created_at` | `created_at DESC` | 按创建时间排序 |
| `idx_source` | `source` | 按来源过滤 |

---

## 8. API端点汇总

### 8.1 任务管理 API

| 方法 | 端点 | 说明 | 代码行 |
|------|------|------|--------|
| GET | `/api/task/{task_id}` | 查询任务详情 | app.py:557-587 |
| POST | `/api/task/save` | 保存任务参数 | app.py:592-680 |
| POST | `/api/task/{task_id}/execute` | 触发任务执行（幂等） | app.py:683-834 |
| GET | `/api/queue/status` | 查询队列状态 | app.py:837-855 |

### 8.2 K文件生成 API

| 方法 | 端点 | 说明 | 代码行 |
|------|------|------|--------|
| GET | `/api/parameters` | 获取参数定义 | app.py:295-315 |
| POST | `/api/validate` | 验证参数 | app.py:335-361 |
| POST | `/api/generate` | 生成K文件（独立模式） | app.py:364-473 |
| GET | `/api/files` | 列出已生成文件 | app.py:476-503 |
| GET | `/api/download/{filename}` | 下载K文件 | app.py:506-525 |

### 8.3 动画生成 API

| 方法 | 端点 | 说明 | 代码行 |
|------|------|------|--------|
| POST | `/api/animation/generate` | 创建动画任务 | app.py:972-1025 |
| GET | `/api/animation/status/{task_id}` | 查询动画状态 | app.py:1028-1063 |
| GET | `/api/animation/download/{task_id}` | 下载动画文件 | app.py:1101-1141 |

---

## 9. 关键代码路径

### 9.1 文件结构

```
Bullet_penetration_simulation/
├── backend/
│   ├── app.py                    # FastAPI主应用 (1200+行)
│   ├── database.py               # 数据库访问层 (400+行)
│   ├── task_manager.py           # 任务管理器 (250+行)
│   ├── task_queue.py             # 任务队列 (300+行)
│   ├── task_sync_scheduler.py    # APScheduler调度器 (200+行)
│   ├── platform_sync.py          # 平台A同步客户端 (220+行)
│   ├── k_engine.py               # K文件生成引擎 (350+行)
│   ├── parameter_config.py       # 参数配置定义 (150+行)
│   ├── column_detector.py        # 列位置检测器 (120+行)
│   ├── unit_converter.py         # 单位转换器 (100+行)
│   ├── animation_generator.py    # 动画生成器 (300+行)
│   ├── animation_config.py       # 动画配置 (80+行)
│   ├── config.json               # 系统配置
│   └── tasks.db                  # SQLite数据库
├── frontend/
│   ├── index.html                # 独立模式页面
│   ├── input.html                # 平台A输入页面
│   ├── output.html               # 平台A输出页面
│   ├── app.js                    # 前端JavaScript逻辑
│   └── style.css                 # 样式文件
├── templates/
│   └── 1.k                       # K文件模板 (275687行, 21MB)
├── generated/                    # 生成的K文件目录
└── docs/                         # 文档目录
```

### 9.2 核心数据流

```mermaid
flowchart LR
    subgraph 输入
        UserParams[用户参数<br/>物理单位]
    end

    subgraph 转换
        UnitConv[UnitConverter<br/>单位转换]
        KValues[K文件值<br/>内部单位]
    end

    subgraph 生成
        Template[模板 1.k<br/>275687行]
        ColDetect[ColumnDetector<br/>列位置检测]
        Replace[参数替换<br/>固定列宽]
        Output[输出K文件<br/>UTF-8无BOM]
    end

    UserParams --> UnitConv
    UnitConv --> KValues
    KValues --> Replace
    Template --> ColDetect
    ColDetect --> Replace
    Replace --> Output
```

---

## 10. 配置说明

### 10.1 config.json 完整配置

```json
{
  "platform_a": {
    "enabled": true,
    "mode": "hybrid",
    "base_url": "http://platform-a.example.com",
    "task_insert_endpoint": "/simulApi/web-app/task-insert/",
    "task_update_endpoint": "/simulApi/web-app/task-update/",
    "timeout": 10,
    "sync_interval": 5,
    "max_retry": 3
  },
  "lsprepost_executable": "E:\\ansys22r2\\ANSYS Inc\\v222\\ansys\\bin\\winx64\\lsprepost48\\lsprepost4.8_x64.exe",
  "animation_output_dir": "D:\\Simulations\\animations",
  "default_resolution": [1920, 1080],
  "default_format": "gif"
}
```

### 10.2 运行模式配置

| 模式 | enabled | mode | 说明 |
|------|---------|------|------|
| 完全禁用 | `false` | - | 调度器不启动，纯独立模式 |
| 独立模式 | `true` | `standalone` | 调度器启动但不同步 |
| 混合模式 | `true` | `hybrid` | 两种任务共存，平台A任务同步 |
| 纯平台A | `true` | `platform_a_only` | 只接受平台A任务 |

---

## 11. 性能指标

### 11.1 响应时间

| 操作 | 预期时间 | 说明 |
|------|----------|------|
| 参数验证 | < 50ms | 纯内存计算 |
| K文件生成 | 2-3秒 | 读写21MB文件 |
| 任务查询 | < 10ms | SQLite索引查询 |
| 同步请求 | < 1秒 | HTTP请求（含网络延迟） |

### 11.2 并发能力

| 组件 | 限制 | 原因 |
|------|------|------|
| FastAPI | 无限制 | 异步IO |
| TaskQueue | 1并发 | 顺序执行，避免文件冲突 |
| APScheduler | 1线程 | 单线程执行器 |
| SQLite | 有限 | WAL模式可提高并发 |

---

## 12. 已知问题与建议

### 12.1 当前限制

| 问题 | 影响 | 建议 |
|------|------|------|
| 线程超时是假超时 | 超时后线程仍在运行 | 改用subprocess |
| 同步重试次数硬编码 | 不够灵活 | 移到config.json |
| SQLite并发写入 | 高并发时锁等待 | 考虑PostgreSQL |

### 12.2 优化建议

1. **启用WAL模式**: 提高SQLite并发读写性能
2. **添加连接池**: 避免频繁创建数据库连接
3. **任务超时保护**: 使用subprocess替代线程
4. **监控仪表盘**: 添加Prometheus指标

---

## 13. 文档索引

| 文档 | 内容 |
|------|------|
| [api_contract.md](api_contract.md) | 平台A集成API契约 |
| [integration_guide.md](integration_guide.md) | 平台A联调指南 |
| [standalone_mode_guide.md](standalone_mode_guide.md) | 独立模式配置 |
| [unit_system.md](unit_system.md) | 单位转换系统 |
| [parameter_guide.md](parameter_guide.md) | 6个参数详细说明 |
| [visualization_solution.md](visualization_solution.md) | 动画生成技术方案 |
| [animation_user_guide.md](animation_user_guide.md) | 动画功能用户指南 |
| [platform_a_integration_design.md](platform_a_integration_design.md) | 平台A集成设计文档 |

---

**文档版本**: 3.0
**最后更新**: 2025-12-14
**维护者**: Claude Code
