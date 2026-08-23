#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MVP测试脚本 - 验证平台触发执行模式（方案2）

测试流程：
1. POST /api/task/save - 保存任务参数
2. POST /api/task/{id}/execute - 触发执行
3. GET /api/task/{id} - 查询状态
4. GET /api/queue/status - 查询队列

运行方式：
1. 启动后端服务: cd backend && python app.py
2. 运行测试: python tests/test_mvp_platform_execute.py
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

# 配置
BASE_URL = "http://localhost:8000/api"
VERBOSE = True


def log(msg):
    """打印日志"""
    if VERBOSE:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def test_save_task():
    """测试1: 保存任务参数"""
    task_id = f"mvp_test_{uuid.uuid4().hex[:8]}"
    log(f"=== 测试1: 保存任务 (task_id={task_id}) ===")

    payload = {
        "task_id": task_id,
        "params": {
            "velocity_z": 1600.0,
            "bullet_yield_stress": 1000.0,
            "target_yield_stress": 800.0,
            "friction_static": 0.25,
            "friction_dynamic": 0.18,
            "simulation_endtime": 30.0
        }
    }

    response = requests.post(f"{BASE_URL}/task/save", json=payload)
    log(f"响应状态: {response.status_code}")
    log(f"响应内容: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    assert response.status_code == 200, f"保存失败: {response.text}"
    data = response.json()
    assert data["success"] == True
    assert data["status"] == 0
    assert data["status_name"] == "待执行"

    log("[PASS] 测试1通过: 任务保存成功")
    return task_id


def test_save_duplicate(task_id):
    """测试2: 重复保存应返回409"""
    log(f"=== 测试2: 重复保存 (task_id={task_id}) ===")

    payload = {
        "task_id": task_id,
        "params": {
            "velocity_z": 2000.0,  # 尝试修改参数
            "bullet_yield_stress": 1000.0,
            "target_yield_stress": 800.0,
            "friction_static": 0.25,
            "friction_dynamic": 0.18,
            "simulation_endtime": 30.0
        }
    }

    response = requests.post(f"{BASE_URL}/task/save", json=payload)
    log(f"响应状态: {response.status_code}")
    log(f"响应内容: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    assert response.status_code == 409, f"应返回409冲突: {response.status_code}"
    data = response.json()
    assert data["error"] == "TASK_EXISTS"

    log("[PASS] 测试2通过: 重复保存正确返回409")


def test_execute_not_found():
    """测试3: 执行不存在的任务应返回404"""
    fake_task_id = f"not_exist_{uuid.uuid4().hex[:8]}"
    log(f"=== 测试3: 执行不存在的任务 (task_id={fake_task_id}) ===")

    response = requests.post(f"{BASE_URL}/task/{fake_task_id}/execute")
    log(f"响应状态: {response.status_code}")

    assert response.status_code == 404, f"应返回404: {response.status_code}"

    log("[PASS] 测试3通过: 不存在任务正确返回404")


def test_execute_task(task_id):
    """测试4: 触发任务执行"""
    log(f"=== 测试4: 触发执行 (task_id={task_id}) ===")

    response = requests.post(f"{BASE_URL}/task/{task_id}/execute")
    log(f"响应状态: {response.status_code}")
    log(f"响应内容: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    assert response.status_code == 200, f"触发执行失败: {response.text}"
    data = response.json()
    assert data["success"] == True
    assert data["status"] == 1
    assert data["status_name"] == "排队中"
    assert "queue_position" in data

    log("[PASS] 测试4通过: 任务成功加入队列")
    return data


def test_execute_idempotent(task_id):
    """测试5: 幂等性 - 重复触发应返回当前状态"""
    log(f"=== 测试5: 幂等性测试 (task_id={task_id}) ===")

    response = requests.post(f"{BASE_URL}/task/{task_id}/execute")
    log(f"响应状态: {response.status_code}")
    log(f"响应内容: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True
    # 状态可能是1(排队中)、2(执行中)或3(已完成)
    assert data["status"] in [1, 2, 3, 4], f"意外状态: {data['status']}"

    log("[PASS] 测试5通过: 幂等性验证成功")


def test_query_task(task_id):
    """测试6: 查询任务状态"""
    log(f"=== 测试6: 查询任务状态 (task_id={task_id}) ===")

    response = requests.get(f"{BASE_URL}/task/{task_id}")
    log(f"响应状态: {response.status_code}")
    log(f"响应内容: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == task_id
    assert "status" in data
    assert "status_name" in data

    log("[PASS] 测试6通过: 任务查询成功")
    return data


def test_queue_status():
    """测试7: 查询队列状态"""
    log(f"=== 测试7: 查询队列状态 ===")

    response = requests.get(f"{BASE_URL}/queue/status")
    log(f"响应状态: {response.status_code}")
    log(f"响应内容: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    assert response.status_code == 200
    data = response.json()
    assert "is_running" in data
    assert "queue_length" in data

    log("[PASS] 测试7通过: 队列状态查询成功")
    return data


def wait_for_completion(task_id, timeout=60):
    """等待任务完成"""
    log(f"=== 等待任务完成 (task_id={task_id}, timeout={timeout}s) ===")

    start_time = time.time()
    while time.time() - start_time < timeout:
        response = requests.get(f"{BASE_URL}/task/{task_id}")
        if response.status_code == 200:
            data = response.json()
            status = data.get("status")
            log(f"当前状态: {data.get('status_name')} ({status})")

            if status == 3:  # 已完成
                log(f"[PASS] 任务完成! 输出文件: {data.get('output_file_path')}")
                return data
            elif status == 4:  # 失败
                log(f"[FAIL] 任务失败: {data.get('error_message')}")
                return data
            elif status == 5:  # 中止
                log(f"[WARN] 任务中止")
                return data

        time.sleep(2)

    log(f"[TIMEOUT] 超时! 任务未在{timeout}秒内完成")
    return None


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("MVP测试 - 平台触发执行模式（方案2）")
    print("=" * 60)
    print()

    try:
        # 测试1: 保存任务
        task_id = test_save_task()
        print()

        # 测试2: 重复保存
        test_save_duplicate(task_id)
        print()

        # 测试3: 执行不存在的任务
        test_execute_not_found()
        print()

        # 测试4: 触发执行
        test_execute_task(task_id)
        print()

        # 测试5: 幂等性
        test_execute_idempotent(task_id)
        print()

        # 测试6: 查询任务
        test_query_task(task_id)
        print()

        # 测试7: 队列状态
        test_queue_status()
        print()

        # 等待任务完成
        result = wait_for_completion(task_id, timeout=60)
        print()

        if result and result.get("status") == 3:
            print("=" * 60)
            print("[SUCCESS] 所有MVP测试通过!")
            print("=" * 60)
            print(f"\n生成的K文件: {result.get('output_file_path')}")
        else:
            print("=" * 60)
            print("[WARN] 任务未成功完成，请检查后端日志")
            print("=" * 60)

    except AssertionError as e:
        print(f"\n[FAIL] 测试失败: {e}")
        return False
    except requests.exceptions.ConnectionError:
        print(f"\n[FAIL] 连接失败! 请确保后端服务已启动: cd backend && python app.py")
        return False
    except Exception as e:
        print(f"\n[FAIL] 测试异常: {e}")
        raise

    return True


if __name__ == "__main__":
    run_all_tests()
