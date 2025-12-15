# 平台A集成联调指南

## 1. 架构概览

```
┌──────────────┐      ┌──────────────────┐      ┌──────────────┐
│   平台A      │      │  仿真App (本系统)  │      │    用户      │
│  (调度方)    │      │   localhost:8000  │      │  (浏览器)    │
└──────┬───────┘      └────────┬─────────┘      └──────┬───────┘
       │                       │                        │
       │  1. 生成task_id       │                        │
       │  2. 跳转到input.html  │                        │
       │─────────────────────→│←───────────────────────│
       │                       │   3. 用户填写参数       │
       │                       │   4. POST /task/save   │
       │                       │←──────────────────────│
       │                       │   5. 返回status=0      │
       │  6. 触发执行          │                        │
       │  POST /task/{id}/execute                       │
       │─────────────────────→│                        │
       │                       │   7. 执行任务          │
       │  8. 轮询状态          │                        │
       │  GET /task/{id}       │                        │
       │─────────────────────→│                        │
       │                       │   9. 返回status=3      │
       │  10. 获取结果         │                        │
       │─────────────────────→│                        │
```

## 2. API 详细说明

### 2.1 保存任务参数（前端调用）

用户在 `input.html?task_id=xxx` 页面填写参数后点击"保存参数"。

```http
POST /api/task/save
Content-Type: application/json

{
    "task_id": "platform_a_task_001",
    "params": {
        "velocity_z": 1600.0,
        "bullet_yield_stress": 1000.0,
        "target_yield_stress": 800.0,
        "friction_static": 0.25,
        "friction_dynamic": 0.18,
        "simulation_endtime": 30.0
    }
}
```

**响应 (200 OK)**:
```json
{
    "success": true,
    "task_id": "platform_a_task_001",
    "status": 0,
    "status_name": "待执行",
    "message": "任务已保存，等待执行"
}
```

**响应 (409 Conflict)** - 任务已存在:
```json
{
    "error": "TASK_EXISTS",
    "message": "任务已存在",
    "current_status": 1,
    "current_status_name": "排队中"
}
```

### 2.2 触发执行（平台A调用）

**这是平台A的核心集成点！**

```http
POST /api/task/{task_id}/execute
Content-Type: application/json

{}
```

**响应 (200 OK)**:
```json
{
    "success": true,
    "task_id": "platform_a_task_001",
    "status": 1,
    "status_name": "排队中",
    "queue_position": 1,
    "estimated_wait_seconds": 10
}
```

**响应 (404 Not Found)** - 任务不存在:
```json
{
    "detail": "任务不存在: xxx"
}
```

**幂等性说明**:
- 多次调用 execute 不会重复入队
- 如果任务已在执行中或已完成，返回当前状态

### 2.3 查询任务状态（平台A轮询）

```http
GET /api/task/{task_id}
```

**响应 (200 OK)**:
```json
{
    "task_id": "platform_a_task_001",
    "source": "platform_a",
    "status": 3,
    "status_name": "已完成",
    "input_params": {
        "velocity_z": 1600.0,
        "bullet_yield_stress": 1000.0,
        "target_yield_stress": 800.0,
        "friction_static": 0.25,
        "friction_dynamic": 0.18,
        "simulation_endtime": 30.0
    },
    "output_file_path": "D:\\...\\tasks\\{task_id}\\bullet_sim_xxx.k",
    "start_time": "2025-12-02T15:54:55.123456",
    "end_time": "2025-12-02T15:54:55.577092",
    "error_message": null
}
```

### 2.4 查询队列状态（可选）

```http
GET /api/queue/status
```

**响应**:
```json
{
    "is_running": true,
    "running_task": {
        "task_id": "xxx",
        "started_at": "2025-12-02T15:54:55.123456",
        "elapsed_seconds": 2.5
    },
    "queue_length": 2,
    "queued_tasks": [
        {"task_id": "yyy", "position": 1},
        {"task_id": "zzz", "position": 2}
    ]
}
```

### 2.5 下载K文件

```http
GET /api/download/{filename}
```

从 `output_file_path` 提取文件名，例如：
- `output_file_path`: `D:\...\tasks\{task_id}\bullet_sim_xxx.k`
- 下载URL: `GET /api/download/bullet_sim_xxx.k`

## 3. 联调检查清单

### 3.1 准备工作

- [ ] 确认App后端服务地址和端口（默认 `localhost:8000`）
- [ ] 确认网络连通性（平台A能访问App）
- [ ] 确认跨域配置（如需要）

### 3.2 联调测试步骤

#### Step 1: 验证服务可用
```bash
curl http://localhost:8000/api/queue/status
```
期望返回: `{"is_running": false, "queue_length": 0, ...}`

#### Step 2: 模拟保存任务
```bash
curl -X POST http://localhost:8000/api/task/save \
  -H "Content-Type: application/json" \
  -d '{"task_id":"test_001","params":{"velocity_z":1600,"bullet_yield_stress":1000,"target_yield_stress":800,"friction_static":0.25,"friction_dynamic":0.18,"simulation_endtime":30}}'
```
期望返回: `{"success": true, "status": 0, ...}`

#### Step 3: 触发执行
```bash
curl -X POST http://localhost:8000/api/task/test_001/execute
```
期望返回: `{"success": true, "status": 1, "queue_position": 1, ...}`

#### Step 4: 轮询状态
```bash
curl http://localhost:8000/api/task/test_001
```
轮询直到 `status=3`

#### Step 5: 下载结果
从响应中获取 `output_file_path`，提取文件名后下载。

## 4. 状态机说明

```
     用户保存参数
          │
          ▼
    ┌─────────────┐
    │  status=0   │  待执行（等待平台A触发）
    │   待执行    │
    └──────┬──────┘
           │ 平台A调用 POST /task/{id}/execute
           ▼
    ┌─────────────┐
    │  status=1   │  排队中（队列非空时）
    │   排队中    │
    └──────┬──────┘
           │ Worker取出任务
           ▼
    ┌─────────────┐
    │  status=2   │  执行中
    │   执行中    │
    └──────┬──────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐ ┌─────────┐
│status=3 │ │status=4 │
│ 已完成  │ │ 已失败  │
└─────────┘ └─────────┘
```

## 5. 错误处理建议

| 场景 | HTTP状态码 | 建议处理 |
|------|-----------|---------|
| 任务不存在 | 404 | 检查task_id是否正确 |
| 重复保存 | 409 | 忽略，使用现有任务 |
| 任务失败 | status=4 | 读取error_message，可选重新触发 |
| 网络超时 | - | 重试，幂等接口安全重试 |

## 6. 联调问题排查

### 问题1: 任务一直是status=0
- 检查平台A是否调用了 `/api/task/{id}/execute`
- 检查请求是否成功返回

### 问题2: 任务一直是status=1
- 查看队列状态: `GET /api/queue/status`
- 检查是否有其他任务正在执行

### 问题3: 任务失败 status=4
- 查看 `error_message` 字段
- 检查后端日志

### 问题4: 下载失败
- 确认 `output_file_path` 存在
- 确认文件名提取正确

## 7. 示例代码（平台A参考）

### Python 示例
```python
import requests
import time

BASE_URL = "http://app-server:8000/api"

def trigger_and_wait(task_id, timeout=60):
    """触发任务并等待完成"""

    # 1. 触发执行
    resp = requests.post(f"{BASE_URL}/task/{task_id}/execute")
    if resp.status_code != 200:
        raise Exception(f"触发失败: {resp.text}")

    # 2. 轮询等待
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(f"{BASE_URL}/task/{task_id}")
        task = resp.json()

        if task["status"] == 3:  # 完成
            return task["output_file_path"]
        elif task["status"] == 4:  # 失败
            raise Exception(f"任务失败: {task['error_message']}")

        time.sleep(2)

    raise TimeoutError("任务超时")
```

### JavaScript 示例
```javascript
async function triggerAndWait(taskId, timeout = 60000) {
    const BASE_URL = 'http://app-server:8000/api';

    // 1. 触发执行
    await fetch(`${BASE_URL}/task/${taskId}/execute`, { method: 'POST' });

    // 2. 轮询等待
    const startTime = Date.now();
    while (Date.now() - startTime < timeout) {
        const resp = await fetch(`${BASE_URL}/task/${taskId}`);
        const task = await resp.json();

        if (task.status === 3) return task.output_file_path;
        if (task.status === 4) throw new Error(task.error_message);

        await new Promise(r => setTimeout(r, 2000));
    }

    throw new Error('任务超时');
}
```

---

**联调联系方式**: [填写负责人联系方式]

**最后更新**: 2025-12-02
