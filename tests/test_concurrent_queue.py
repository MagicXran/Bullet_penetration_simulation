#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
并发测试脚本 - 验证串行队列

同时提交3个任务，验证它们按顺序执行
"""

import requests
import time
import uuid
import json
import sys
import io
import threading
from datetime import datetime

# 修复Windows控制台编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE_URL = "http://localhost:8000/api"


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {msg}")


def create_and_execute_task(task_num):
    """创建并执行任务"""
    task_id = f"concurrent_test_{task_num}_{uuid.uuid4().hex[:6]}"

    # 保存任务
    payload = {
        "task_id": task_id,
        "params": {
            "velocity_z": 1600.0 + task_num * 100,
            "bullet_yield_stress": 1000.0,
            "target_yield_stress": 800.0,
            "friction_static": 0.25,
            "friction_dynamic": 0.18,
            "simulation_endtime": 30.0
        }
    }

    resp = requests.post(f"{BASE_URL}/task/save", json=payload)
    if resp.status_code != 200:
        log(f"任务{task_num} 保存失败: {resp.status_code}")
        return None

    log(f"任务{task_num} ({task_id[:20]}...) 保存成功")

    # 触发执行
    resp = requests.post(f"{BASE_URL}/task/{task_id}/execute")
    data = resp.json()
    log(f"任务{task_num} 触发执行: status={data.get('status')}, position={data.get('queue_position', 'N/A')}")

    return task_id


def wait_all_complete(task_ids, timeout=120):
    """等待所有任务完成"""
    start_time = time.time()
    completed = []

    while len(completed) < len(task_ids) and time.time() - start_time < timeout:
        for task_id in task_ids:
            if task_id in completed:
                continue

            resp = requests.get(f"{BASE_URL}/task/{task_id}")
            if resp.status_code == 200:
                data = resp.json()
                status = data.get('status')
                if status == 3:  # 完成
                    completed.append(task_id)
                    end_time = data.get('end_time', '')
                    log(f"[DONE] {task_id[:20]}... 完成于 {end_time[-12:]}")
                elif status == 4:  # 失败
                    completed.append(task_id)
                    log(f"[FAIL] {task_id[:20]}... 失败: {data.get('error_message')}")

        if len(completed) < len(task_ids):
            time.sleep(0.5)

    return completed


def main():
    print("=" * 60)
    print("并发测试 - 串行队列验证")
    print("=" * 60)
    print()

    # 同时提交3个任务
    log("=== 同时提交3个任务 ===")
    threads = []
    task_ids = []
    results = [None, None, None]

    def save_result(i):
        results[i] = create_and_execute_task(i + 1)

    # 启动3个线程同时提交
    for i in range(3):
        t = threading.Thread(target=save_result, args=(i,))
        threads.append(t)

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    task_ids = [r for r in results if r]
    print()

    if len(task_ids) < 3:
        log("[FAIL] 部分任务创建失败")
        return

    # 查看队列状态
    log("=== 队列状态 ===")
    resp = requests.get(f"{BASE_URL}/queue/status")
    data = resp.json()
    log(f"正在执行: {data.get('is_running')}")
    log(f"队列长度: {data.get('queue_length')}")
    if data.get('running_task'):
        log(f"当前任务: {data['running_task'].get('task_id', 'N/A')[:20]}...")
    print()

    # 等待所有任务完成
    log("=== 等待所有任务完成 ===")
    completed = wait_all_complete(task_ids, timeout=60)
    print()

    # 验证结果
    log("=== 验证执行顺序 ===")
    execution_times = []
    for task_id in task_ids:
        resp = requests.get(f"{BASE_URL}/task/{task_id}")
        data = resp.json()
        start = data.get('start_time', '')
        end = data.get('end_time', '')
        execution_times.append({
            'task_id': task_id[:20],
            'start': start,
            'end': end
        })
        log(f"{task_id[:20]}... | 开始: {start[-12:]} | 结束: {end[-12:]}")

    print()

    # 检查是否串行执行（每个任务的开始时间 >= 前一个任务的结束时间）
    serial = True
    for i in range(1, len(execution_times)):
        prev_end = execution_times[i-1]['end']
        curr_start = execution_times[i]['start']
        if curr_start < prev_end:
            serial = False
            log(f"[WARN] 任务{i+1}在任务{i}结束前就开始了")

    if len(completed) == len(task_ids):
        print("=" * 60)
        if serial:
            log("[PASS] 所有任务完成，串行执行验证通过!")
        else:
            log("[WARN] 所有任务完成，但可能存在并发执行")
        print("=" * 60)
    else:
        print("=" * 60)
        log(f"[FAIL] 只有 {len(completed)}/{len(task_ids)} 个任务完成")
        print("=" * 60)


if __name__ == "__main__":
    main()
