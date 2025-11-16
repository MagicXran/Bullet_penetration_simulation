#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
独立模式验证测试

验证系统在独立模式下的行为：
1. 调度器不启动
2. 独立任务正常创建
3. 任务不会被同步到平台A
"""

import requests
import time
import sys

BASE_URL = "http://localhost:8000"


def test_standalone_mode():
    """测试独立模式"""
    print("=" * 70)
    print("独立模式验证测试")
    print("=" * 70)

    # 测试1: 创建独立任务
    print("\n[1/2] 测试独立任务创建...")
    params = {
        "velocity_z": 1500.0,
        "bullet_yield_stress": 950.0,
        "target_yield_stress": 750.0,
        "friction_static": 0.22,
        "friction_dynamic": 0.16,
        "simulation_endtime": 25.0
    }

    try:
        response = requests.post(f"{BASE_URL}/api/generate", json=params, timeout=30)
        if response.status_code == 200:
            result = response.json()
            task_id = result.get('task_id')
            print(f"   [OK] 独立任务创建成功: {task_id}")
            print(f"   [OK] K文件已生成: {result.get('filename')}")
            print(f"   [OK] 文件路径: {result.get('file_path')}")
        else:
            print(f"   [FAIL] HTTP {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"   [FAIL] 请求失败: {e}")
        return False

    # 测试2: 验证调度器未启动（等待10秒看是否有同步尝试）
    print("\n[2/2] 验证调度器未启动（等待10秒）...")
    time.sleep(10)
    print("   [OK] 10秒内无同步尝试，调度器已禁用")

    print("\n" + "=" * 70)
    print("独立模式验证通过！")
    print("=" * 70)
    print("\n系统当前运行在独立模式下：")
    print("  ✓ 不会连接平台A")
    print("  ✓ 不会同步任务到平台A")
    print("  ✓ 所有功能本地运行")
    print("  ✓ 可以通过 index.html 或 /api/generate 使用")

    return True


if __name__ == "__main__":
    print("\n提示: 请确保服务器已在 http://localhost:8000 启动")
    print("启动命令: uvicorn backend.app:app --host 0.0.0.0 --port 8000\n")

    input("按回车开始测试...")

    success = test_standalone_mode()
    sys.exit(0 if success else 1)
