#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
运行时集成测试 - Runtime Integration Test

测试真实的FastAPI服务器，验证双模式架构在实际运行中的表现
"""

import subprocess
import time
import sys
import os
import requests
import sqlite3
from pathlib import Path

# 添加backend到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))


class RuntimeTester:
    """运行时测试器"""

    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.server_process = None
        self.db_path = "backend/tasks.db"

    def start_server(self):
        """启动FastAPI服务器"""
        print("\n[1/8] 启动FastAPI服务器...")

        # 启动服务器进程
        self.server_process = subprocess.Popen(
            [
                sys.executable,
                "-m", "uvicorn",
                "backend.app:app",
                "--host", "0.0.0.0",
                "--port", "8000"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(__file__)
        )

        # 等待服务器启动
        max_attempts = 30
        for i in range(max_attempts):
            try:
                response = requests.get(f"{self.base_url}/docs")
                if response.status_code == 200:
                    print(f"   [OK] 服务器已启动 (耗时 {i+1} 秒)")
                    return True
            except requests.exceptions.ConnectionError:
                pass

            time.sleep(1)
            print(f"   等待服务器启动... ({i+1}/{max_attempts})")

        print("   [FAIL] 服务器启动超时")
        return False

    def stop_server(self):
        """停止FastAPI服务器"""
        print("\n[8/8] 停止服务器...")
        if self.server_process:
            self.server_process.terminate()
            self.server_process.wait(timeout=5)
            print("   [OK] 服务器已停止")

    def test_standalone_mode(self):
        """测试独立模式 - /api/generate"""
        print("\n[2/8] 测试独立模式API (/api/generate)...")

        params = {
            "velocity_z": 1500.0,
            "bullet_yield_stress": 950.0,
            "target_yield_stress": 750.0,
            "friction_static": 0.22,
            "friction_dynamic": 0.16,
            "simulation_endtime": 25.0
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=params,
                timeout=30
            )

            if response.status_code != 200:
                print(f"   [FAIL] HTTP {response.status_code}: {response.text}")
                return None

            result = response.json()
            task_id = result.get('task_id')

            # 验证task_id格式
            if not task_id or not task_id.startswith('standalone_'):
                print(f"   [FAIL] task_id格式错误: {task_id}")
                return None

            print(f"   [OK] 独立任务创建成功: {task_id}")
            return task_id

        except Exception as e:
            print(f"   [FAIL] 请求失败: {e}")
            return None

    def test_platform_a_mode(self):
        """测试平台A模式 - /api/task/submit"""
        print("\n[3/8] 测试平台A模式API (/api/task/submit)...")

        task_id = "platform_a_runtime_test_001"
        params = {
            "velocity_z": 1600.0,
            "bullet_yield_stress": 1000.0,
            "target_yield_stress": 800.0,
            "friction_static": 0.25,
            "friction_dynamic": 0.18,
            "simulation_endtime": 30.0
        }

        payload = {
            "task_id": task_id,
            "params": params
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/task/submit",
                json=payload,
                timeout=30
            )

            if response.status_code != 200:
                print(f"   [FAIL] HTTP {response.status_code}: {response.text}")
                return None

            result = response.json()
            print(f"   [OK] 平台A任务创建成功: {task_id}")
            return task_id

        except Exception as e:
            print(f"   [FAIL] 请求失败: {e}")
            return None

    def test_task_query(self, task_id):
        """测试任务查询 - /api/task/{task_id}"""
        print(f"\n[4/8] 测试任务查询API (/api/task/{task_id})...")

        try:
            response = requests.get(
                f"{self.base_url}/api/task/{task_id}",
                timeout=10
            )

            if response.status_code != 200:
                print(f"   [FAIL] HTTP {response.status_code}: {response.text}")
                return None

            task = response.json()
            print(f"   [OK] 任务查询成功")
            print(f"      - 状态: {task.get('status_name')}")
            print(f"      - 来源: {task.get('source')}")

            return task

        except Exception as e:
            print(f"   [FAIL] 请求失败: {e}")
            return None

    def verify_database_isolation(self, standalone_id, platform_id):
        """验证数据库双模式隔离"""
        print("\n[5/8] 验证数据库双模式隔离...")

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 查询独立任务
            cursor.execute("SELECT task_id, source FROM tasks WHERE task_id = ?", (standalone_id,))
            standalone_task = cursor.fetchone()

            # 查询平台A任务
            cursor.execute("SELECT task_id, source FROM tasks WHERE task_id = ?", (platform_id,))
            platform_task = cursor.fetchone()

            # 查询未同步任务（应该只包含平台A任务）
            cursor.execute("""
                SELECT task_id FROM tasks
                WHERE platform_a_synced = 0
                  AND source = 'platform_a'
            """)
            unsynced_tasks = [row[0] for row in cursor.fetchall()]

            conn.close()

            # 验证source字段
            if not standalone_task or standalone_task[1] != 'standalone':
                print(f"   [FAIL] 独立任务source字段错误: {standalone_task}")
                return False

            if not platform_task or platform_task[1] != 'platform_a':
                print(f"   [FAIL] 平台A任务source字段错误: {platform_task}")
                return False

            # 验证隔离逻辑
            if standalone_id in unsynced_tasks:
                print(f"   [FAIL] 独立任务出现在未同步列表中")
                return False

            if platform_id not in unsynced_tasks:
                print(f"   [FAIL] 平台A任务未出现在未同步列表中")
                return False

            print(f"   [OK] 数据库隔离验证成功")
            print(f"      - 独立任务source: {standalone_task[1]}")
            print(f"      - 平台A任务source: {platform_task[1]}")
            print(f"      - 未同步任务数: {len(unsynced_tasks)}")
            print(f"      - 独立任务未被同步: True")

            return True

        except Exception as e:
            print(f"   [FAIL] 数据库验证失败: {e}")
            return False

    def test_scheduler_filtering(self):
        """测试调度器过滤逻辑"""
        print("\n[6/8] 测试调度器过滤逻辑...")

        try:
            from database import Database

            db = Database(self.db_path)
            unsynced = db.get_unsynced_tasks(limit=100)

            # 检查所有未同步任务的source字段
            standalone_count = 0
            platform_a_count = 0

            for task in unsynced:
                if task['source'] == 'standalone':
                    standalone_count += 1
                elif task['source'] == 'platform_a':
                    platform_a_count += 1

            if standalone_count > 0:
                print(f"   [FAIL] 发现 {standalone_count} 个独立任务在未同步列表中")
                return False

            print(f"   [OK] 调度器过滤正确")
            print(f"      - 独立任务: {standalone_count} (应该为0)")
            print(f"      - 平台A任务: {platform_a_count}")

            return True

        except Exception as e:
            print(f"   [FAIL] 调度器测试失败: {e}")
            return False

    def test_file_generation(self):
        """测试K文件生成"""
        print("\n[7/8] 测试K文件生成...")

        try:
            # 检查生成的K文件
            generated_dir = Path("generated")
            if not generated_dir.exists():
                print(f"   [FAIL] generated目录不存在")
                return False

            k_files = list(generated_dir.glob("*.k"))
            print(f"   [OK] 找到 {len(k_files)} 个K文件")

            if k_files:
                latest_file = max(k_files, key=lambda p: p.stat().st_mtime)
                print(f"      - 最新文件: {latest_file.name}")
                print(f"      - 文件大小: {latest_file.stat().st_size} bytes")

            return True

        except Exception as e:
            print(f"   [FAIL] 文件检查失败: {e}")
            return False

    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 70)
        print("运行时集成测试 - Runtime Integration Test")
        print("=" * 70)

        results = {}
        standalone_id = None
        platform_id = None

        try:
            # 启动服务器
            if not self.start_server():
                print("\n[FAIL] 服务器启动失败，终止测试")
                return False

            # 测试独立模式
            standalone_id = self.test_standalone_mode()
            results['standalone_mode'] = standalone_id is not None

            # 测试平台A模式
            platform_id = self.test_platform_a_mode()
            results['platform_a_mode'] = platform_id is not None

            # 测试任务查询
            if platform_id:
                task = self.test_task_query(platform_id)
                results['task_query'] = task is not None

            # 验证数据库隔离
            if standalone_id and platform_id:
                results['database_isolation'] = self.verify_database_isolation(
                    standalone_id, platform_id
                )

            # 测试调度器过滤
            results['scheduler_filtering'] = self.test_scheduler_filtering()

            # 测试文件生成
            results['file_generation'] = self.test_file_generation()

        finally:
            # 停止服务器
            self.stop_server()

        # 打印汇总结果
        print("\n" + "=" * 70)
        print("测试结果汇总")
        print("=" * 70)

        total = len(results)
        passed = sum(1 for v in results.values() if v)

        for test_name, result in results.items():
            status = "[PASS]" if result else "[FAIL]"
            print(f"{status} {test_name}")

        print("-" * 70)
        print(f"通过率: {passed}/{total} ({100*passed/total:.0f}%)")

        if passed == total:
            print("\n[SUCCESS] 所有运行时测试通过！ ")
            print("双模式架构在实际运行中工作正常。")
            return True
        else:
            print(f"\n[WARNING] {total-passed} 个测试失败，请检查错误信息")
            return False


if __name__ == "__main__":
    tester = RuntimeTester()
    success = tester.run_all_tests()

    sys.exit(0 if success else 1)
