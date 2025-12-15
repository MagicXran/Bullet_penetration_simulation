# 平台A集成API契约

> 版本: 1.0.1
> 更新日期: 2025-12-03
> 服务基础地址: `http://{APP_HOST}:8000`

---

## 集成API（共2个）

### 1. 触发任务执行

**平台A调用此接口触发任务执行**

```
POST /api/task/{task_id}/execute
```

#### 请求

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| task_id | string | 是 | 任务ID（路径参数），8-128字符 |
| force | boolean | 否 | 强制重新执行已完成/失败任务，默认false |

```http
POST /api/task/550e8400-e29b-41d4-a716-446655440000/execute
Content-Type: application/json

{}
```

#### 响应

**成功 (200)**
```json
{
    "success": true,
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": 1,
    "status_name": "排队中",
    "message": "任务已加入执行队列",
    "queue_position": 1,
    "estimated_wait_seconds": 10
}
```

**幂等响应** - 任务已完成时 (200)
```json
{
    "success": true,
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": 3,
    "status_name": "已完成",
    "message": "任务已完成",
    "output_file_path": "D:\\...\\tasks\\{task_id}\\bullet_sim_xxx.k",
    "completed_at": "2025-12-02T15:54:55.577092"
}
```

**错误 (404)** - 任务不存在
```json
{
    "detail": {
        "success": false,
        "error": "TASK_NOT_FOUND",
        "message": "任务不存在，请先调用 /api/task/save 保存参数"
    }
}
```

---

### 2. 查询任务状态

**轮询此接口获取任务执行结果**

```
GET /api/task/{task_id}
```

#### 请求

```http
GET /api/task/550e8400-e29b-41d4-a716-446655440000
```

#### 响应

**成功 (200)**
```json
{
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
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
    "created_at": "2025-12-02T15:54:49.123456",
    "start_time": "2025-12-02T15:54:55.123456",
    "end_time": "2025-12-02T15:54:55.577092",
    "error_message": null
}
```

**错误 (404)**
```json
{
    "detail": "任务不存在: xxx"
}
```

---

## 状态码定义

| status | status_name | 说明 | 平台A行为 |
|--------|-------------|------|----------|
| 0 | 待执行 | 参数已保存 | 可调用 execute |
| 1 | 排队中 | 已加入队列 | 轮询等待 |
| 2 | 执行中 | 正在生成 | 轮询等待 |
| 3 | 已完成 | K文件已生成 | **获取 output_file_path** |
| 4 | 已失败 | 执行出错 | 读取 error_message |
| 5 | 已中止 | 任务终止 | 不可恢复 |

---

## 仿真参数

| 参数名 | 类型 | 单位 | 范围 | 说明 |
|--------|------|------|------|------|
| velocity_z | float | m/s | 500-3000 | 弹丸初速度 |
| bullet_yield_stress | float | MPa | 500-2000 | 弹丸屈服强度 |
| target_yield_stress | float | MPa | 200-1200 | 靶板屈服强度 |
| friction_static | float | - | 0.0-0.8 | 静摩擦系数 |
| friction_dynamic | float | - | 0.0-0.6 | 动摩擦系数（≤静摩擦） |
| simulation_endtime | float | µs | 10-100 | 仿真终止时间 |

---

## 集成流程

```
平台A                              仿真App                           用户
  │                                   │                               │
  │ 1. 生成task_id                    │                               │
  │ 2. 跳转 input.html?task_id=xxx    │                               │
  │──────────────────────────────────→│←──────────────────────────────│
  │                                   │ 3. 用户填写参数                 │
  │                                   │ 4. POST /api/task/save         │
  │                                   │←──────────────────────────────│
  │                                   │    返回 status=0              │
  │                                   │                               │
  │ 5. POST /api/task/{id}/execute    │                               │
  │──────────────────────────────────→│                               │
  │    返回 status=1                  │                               │
  │                                   │                               │
  │ 6. GET /api/task/{id} (轮询)      │                               │
  │──────────────────────────────────→│                               │
  │    返回 status=3, output_file_path│                               │
  │                                   │                               │
  │ 7. 读取 output_file_path 获取文件  │                               │
  │                                   │                               │
```

---

## 幂等性说明

`POST /execute` 接口**幂等安全**，可放心重试：

| 当前状态 | 调用execute后 |
|---------|---------------|
| status=0 | → status=1 (入队) |
| status=1 | 返回队列位置 |
| status=2 | 返回执行进度 |
| status=3 | 返回结果（不重复执行） |
| status=4 | 返回错误信息 |

---

## 示例代码

```python
import requests
import time

APP = "http://app-server:8000/api"

def execute_and_wait(task_id, timeout=300):
    """触发执行并等待完成"""

    # 1. 触发
    requests.post(f"{APP}/task/{task_id}/execute")

    # 2. 轮询
    start = time.time()
    while time.time() - start < timeout:
        task = requests.get(f"{APP}/task/{task_id}").json()

        if task["status"] == 3:
            return task["output_file_path"]
        if task["status"] == 4:
            raise Exception(task["error_message"])

        time.sleep(2)

    raise TimeoutError("超时")
```

---

## 联调检查清单

- [ ] `POST /api/task/{id}/execute` 返回 status=1
- [ ] `GET /api/task/{id}` 返回完整任务信息
- [ ] status=3 时能获取 output_file_path
- [ ] 重复调用 execute 不会重复入队
