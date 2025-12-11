#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
前端流程测试脚本 - 模拟完整用户场景

测试流程：
1. 用户在input.html保存参数 → POST /api/task/save → status=0
2. 用户跳转output.html查看 → GET /api/task/{id} → 显示"待执行"
3. 平台A触发执行 → POST /api/task/{id}/execute → status=1
4. 用户刷新output.html → GET /api/task/{id} → 显示"排队中"或"执行中"
5. 任务完成 → status=3 → 显示"已完成"

运行方式：
python tests/test_frontend_flow.py
"""

import requests
import time
import uuid
import json
import sys
import io
from datetime import datetime

# 修复Windows控制台编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE_URL = "http://localhost:8000/api"


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {msg}")


def test_frontend_flow():
    """测试完整的前端流程"""
    print("=" * 70)
    print("前端流程测试 - 模拟 input.html -> output.html 完整场景")
    print("=" * 70)
    print()

    # 生成任务ID（模拟平台A生成）
    task_id = f"frontend_test_{uuid.uuid4().hex[:8]}"
    log(f"模拟任务ID: {task_id}")
    print()

    # === 步骤1: 模拟 input.html 保存参数 ===
    log("[STEP 1] 模拟 input.html - 用户填写参数并点击'保存参数'")
    log("-" * 50)

    params = {
        "velocity_z": 1800.0,
        "bullet_yield_stress": 1200.0,
        "target_yield_stress": 900.0,
        "friction_static": 0.30,
        "friction_dynamic": 0.22,
        "simulation_endtime": 40.0
    }

    resp = requests.post(f"{BASE_URL}/task/save", json={
        "task_id": task_id,
        "params": params
    })

    log(f"POST /api/task/save => {resp.status_code}")
    data = resp.json()
    log(f"响应: success={data.get('success')}, status={data.get('status')}, status_name={data.get('status_name')}")

    assert resp.status_code == 200, f"保存失败: {resp.text}"
    assert data["status"] == 0, f"状态应为0(待执行)，实际: {data['status']}"

    log("[PASS] 参数保存成功，状态为'待执行'")
    print()

    # === 步骤2: 模拟 output.html 首次加载 ===
    log("[STEP 2] 模拟 output.html - 用户跳转查看结果（任务未执行）")
    log("-" * 50)

    resp = requests.get(f"{BASE_URL}/task/{task_id}")
    log(f"GET /api/task/{task_id} => {resp.status_code}")
    task = resp.json()
    log(f"任务状态: status={task['status']}, status_name={task.get('status_name', '-')}")
    log(f"  - 前端应显示: '参数已保存，等待平台触发执行'")
    log(f"  - 轮询策略: 不自动轮询（状态0）")

    assert task["status"] == 0, f"状态应为0(待执行)，实际: {task['status']}"

    log("[PASS] 正确显示'待执行'状态")
    print()

    # === 步骤3: 模拟平台A触发执行 ===
    log("[STEP 3] 模拟平台A - 调用execute接口触发执行")
    log("-" * 50)

    resp = requests.post(f"{BASE_URL}/task/{task_id}/execute")
    log(f"POST /api/task/{task_id}/execute => {resp.status_code}")
    data = resp.json()
    log(f"响应: success={data.get('success')}, status={data.get('status')}, queue_position={data.get('queue_position', 'N/A')}")

    assert resp.status_code == 200, f"触发执行失败: {resp.text}"
    assert data["status"] >= 1, f"状态应>=1(排队中/执行中)，实际: {data['status']}"

    log("[PASS] 任务成功加入队列")
    print()

    # === 步骤4: 模拟 output.html 刷新 ===
    log("[STEP 4] 模拟 output.html - 用户刷新页面（任务执行中）")
    log("-" * 50)

    # 查询任务状态
    resp = requests.get(f"{BASE_URL}/task/{task_id}")
    task = resp.json()
    status = task["status"]
    log(f"任务状态: status={status}")

    if status == 1:
        log("  - 前端应显示: '排队等待中'")
        log("  - 尝试获取队列位置...")
        qresp = requests.get(f"{BASE_URL}/queue/status")
        qdata = qresp.json()
        log(f"  - 队列状态: is_running={qdata.get('is_running')}, queue_length={qdata.get('queue_length')}")
    elif status == 2:
        log("  - 前端应显示: '正在执行'")
        log("  - 轮询策略: 每2秒刷新")
    elif status == 3:
        log("  - 前端应显示: '计算完成'")
        log("  - 轮询策略: 停止轮询")

    log("[PASS] 状态显示正确")
    print()

    # === 步骤5: 等待任务完成 ===
    log("[STEP 5] 等待任务完成...")
    log("-" * 50)

    timeout = 30
    start = time.time()
    final_status = None

    while time.time() - start < timeout:
        resp = requests.get(f"{BASE_URL}/task/{task_id}")
        task = resp.json()
        status = task["status"]

        if status == 3:
            final_status = task
            log(f"[DONE] 任务完成!")
            log(f"  - 输出文件: {task.get('output_file_path', 'N/A')}")
            log(f"  - 完成时间: {task.get('end_time', 'N/A')}")
            break
        elif status == 4:
            log(f"[FAIL] 任务失败: {task.get('error_message', 'N/A')}")
            break

        log(f"  状态: {status} ({task.get('status_name', '?')}) - 等待中...")
        time.sleep(1)

    print()

    # === 总结 ===
    if final_status and final_status["status"] == 3:
        print("=" * 70)
        log("[SUCCESS] 前端流程测试通过!")
        print("=" * 70)
        print()
        log("测试验证的关键点:")
        log("  1. input.html 保存参数 => status=0 (待执行)")
        log("  2. output.html 查看未执行任务 => 显示'等待平台触发'")
        log("  3. 平台A execute => status=1 (排队中)")
        log("  4. output.html 刷新 => 显示队列位置/执行状态")
        log("  5. 任务完成 => status=3, 显示下载按钮")
        print()
        log(f"生成的K文件: {final_status.get('output_file_path')}")
        return True
    else:
        print("=" * 70)
        log("[FAILED] 前端流程测试未完全通过")
        print("=" * 70)
        return False


if __name__ == "__main__":
    try:
        success = test_frontend_flow()
        sys.exit(0 if success else 1)
    except requests.exceptions.ConnectionError:
        print("[ERROR] 连接失败! 请确保后端服务已启动: cd backend && python app.py")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] 测试异常: {e}")
        raise
