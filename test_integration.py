#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
平台A集成 - 综合集成测试

测试内容：
1. 数据库操作
2. 任务管理逻辑
3. 平台A通信（Mock）
4. API接口
5. 后台调度器
"""

import sys
import os
import time
import json
import sqlite3
from datetime import datetime
from unittest.mock import patch, MagicMock

# 添加backend到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import requests_mock
import requests

# 导入模块
from database import Database
from task_manager import TaskManager
from platform_sync import PlatformSyncClient
from task_sync_scheduler import TaskSyncScheduler


class TestColors:
    """测试输出颜色"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_test_header(title):
    """打印测试标题"""
    print(f"\n{TestColors.HEADER}{TestColors.BOLD}{'='*60}{TestColors.ENDC}")
    print(f"{TestColors.HEADER}{TestColors.BOLD}{title}{TestColors.ENDC}")
    print(f"{TestColors.HEADER}{TestColors.BOLD}{'='*60}{TestColors.ENDC}")


def print_success(msg):
    """打印成功信息"""
    print(f"{TestColors.OKGREEN}[PASS] {msg}{TestColors.ENDC}")


def print_fail(msg):
    """打印失败信息"""
    print(f"{TestColors.FAIL}[FAIL] {msg}{TestColors.ENDC}")


def print_info(msg):
    """打印信息"""
    print(f"{TestColors.OKCYAN}[INFO] {msg}{TestColors.ENDC}")


# ==================== 测试1：数据库操作 ====================

def test_database():
    """测试数据库操作"""
    print_test_header("测试1：数据库操作")

    # 使用测试数据库
    test_db_path = "backend/test_tasks.db"

    # 删除旧的测试数据库
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    try:
        db = Database(test_db_path)
        print_success("数据库初始化成功")

        # 测试创建任务
        task_id = "test_task_001"
        params = {
            "velocity_z": 1600.0,
            "bullet_yield_stress": 1000.0
        }

        result = db.create_task(task_id, params)
        assert result == True, "创建任务失败"
        print_success(f"创建任务成功: {task_id}")

        # 测试查询任务
        task = db.get_task(task_id)
        assert task is not None, "查询任务失败"
        assert task['task_id'] == task_id, "任务ID不匹配"
        assert task['input_params']['velocity_z'] == 1600.0, "参数不匹配"
        print_success(f"查询任务成功: {json.dumps(task['input_params'], ensure_ascii=False)}")

        # 测试更新任务状态
        result = db.update_task_status(
            task_id,
            status=2,
            start_time=datetime.now().isoformat()
        )
        assert result == True, "更新任务状态失败"
        print_success("更新任务状态成功 (status=2)")

        # 测试完成任务
        result = db.update_task_status(
            task_id,
            status=3,
            end_time=datetime.now().isoformat(),
            output_file_path="/path/to/output.k"
        )
        assert result == True, "完成任务失败"
        print_success("标记任务完成成功 (status=3)")

        # 验证最终状态
        task = db.get_task(task_id)
        assert task['status'] == 3, "最终状态不正确"
        assert task['output_file_path'] == "/path/to/output.k", "输出路径不正确"
        print_success(f"最终状态验证成功: status={task['status']}, output={task['output_file_path']}")

        # 测试未同步任务查询
        unsynced = db.get_unsynced_tasks()
        assert len(unsynced) == 1, "未同步任务数量不正确"
        print_success(f"未同步任务查询成功: {len(unsynced)} 个任务")

        # 测试标记已同步
        result = db.mark_as_synced(task_id)
        assert result == True, "标记已同步失败"
        print_success("标记已同步成功")

        unsynced = db.get_unsynced_tasks()
        assert len(unsynced) == 0, "同步后仍有未同步任务"
        print_success("同步验证成功: 无未同步任务")

        print_info("[OK] 数据库测试全部通过")
        return True

    except AssertionError as e:
        print_fail(f"断言失败: {e}")
        return False
    except Exception as e:
        print_fail(f"异常: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== 测试2：任务管理器 ====================

def test_task_manager():
    """测试任务管理器"""
    print_test_header("测试2：任务管理器")

    test_db_path = "backend/test_tasks.db"

    # 删除旧数据库
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    try:
        tm = TaskManager(test_db_path)
        print_success("任务管理器初始化成功")

        # 测试创建或获取任务
        task_id = "task_mgr_test_001"
        params = {
            "velocity_z": 2000.0,
            "bullet_yield_stress": 1200.0,
            "target_yield_stress": 900.0,
            "friction_static": 0.3,
            "friction_dynamic": 0.2,
            "simulation_endtime": 25.0
        }

        task = tm.create_or_get_task(task_id, params)
        assert task is not None, "创建任务失败"
        assert task['task_id'] == task_id, "任务ID不匹配"
        print_success(f"创建任务成功: {task_id}")

        # 测试提交任务
        task = tm.submit_task(task_id, params)
        assert task['submission_time'] is not None, "提交时间未设置"
        print_success(f"提交任务成功: submission_time={task['submission_time']}")

        # 测试开始任务
        result = tm.start_task(task_id)
        assert result == True, "开始任务失败"
        task = tm.get_task(task_id)
        assert task['status'] == TaskManager.STATUS_RUNNING, "状态未更新为运行中"
        assert task['start_time'] is not None, "开始时间未设置"
        print_success(f"开始任务成功: status={task['status']}, start_time={task['start_time']}")

        # 测试完成任务
        output_path = "generated/test_output.k"
        result = tm.complete_task(task_id, output_path)
        assert result == True, "完成任务失败"
        task = tm.get_task(task_id)
        assert task['status'] == TaskManager.STATUS_COMPLETED, "状态未更新为已完成"
        assert task['output_file_path'] == output_path, "输出路径不正确"
        print_success(f"完成任务成功: status={task['status']}, output={task['output_file_path']}")

        # 测试失败任务
        fail_task_id = "task_fail_test"
        tm.create_or_get_task(fail_task_id, params)
        tm.fail_task(fail_task_id, "测试错误信息")
        task = tm.get_task(fail_task_id)
        assert task['status'] == TaskManager.STATUS_FAILED, "失败状态不正确"
        assert task['error_message'] == "测试错误信息", "错误信息不正确"
        print_success(f"失败任务测试成功: error={task['error_message']}")

        # 测试task_id验证
        assert TaskManager.validate_task_id("valid_task_123") == True, "有效task_id验证失败"
        assert TaskManager.validate_task_id("invalid@task") == False, "无效task_id验证通过（不应该）"
        assert TaskManager.validate_task_id("short") == False, "短task_id验证通过（不应该）"
        print_success("task_id格式验证通过")

        print_info("[OK] 任务管理器测试全部通过")
        return True

    except AssertionError as e:
        print_fail(f"断言失败: {e}")
        return False
    except Exception as e:
        print_fail(f"异常: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== 测试3：平台A通信（Mock）====================

def test_platform_sync_with_mock():
    """测试平台A通信（使用Mock）"""
    print_test_header("测试3：平台A通信（Mock）")

    try:
        # 配置Mock平台A
        config = {
            'base_url': 'http://mock-platform-a.com',
            'task_insert_endpoint': '/simulApi/web-app/task-insert/',
            'task_update_endpoint': '/simulApi/web-app/task-update/',
            'timeout': 5
        }

        sync_client = PlatformSyncClient(config)
        print_success("平台A同步客户端初始化成功")

        with requests_mock.Mocker() as m:
            # Mock task-insert接口
            insert_url = f"{config['base_url']}{config['task_insert_endpoint']}"
            m.post(insert_url, json={'code': 0, 'msg': '插入成功'})

            # Mock task-update接口
            update_url = f"{config['base_url']}{config['task_update_endpoint']}"
            m.post(update_url, json={'code': 0, 'msg': '更新成功'})

            # 测试插入任务
            success, error = sync_client.insert_task(
                task_id="mock_test_001",
                submission_time=datetime.now().isoformat(),
                task_status=0
            )
            assert success == True, f"插入任务失败: {error}"
            assert error is None, "不应该有错误信息"
            print_success("Mock平台A task-insert调用成功")

            # 验证请求内容
            last_request = m.last_request
            request_data = last_request.json()
            assert request_data['task_id'] == "mock_test_001", "task_id不匹配"
            assert request_data['task_status'] == 0, "status不匹配"
            print_success(f"请求参数验证成功: {json.dumps(request_data, ensure_ascii=False)}")

            # 测试更新任务
            success, error = sync_client.update_task(
                task_id="mock_test_001",
                task_status=3,
                start_time=datetime.now().isoformat(),
                end_time=datetime.now().isoformat(),
                error_message=""
            )
            assert success == True, f"更新任务失败: {error}"
            print_success("Mock平台A task-update调用成功")

            # 测试错误响应
            m.post(insert_url, json={'code': 1, 'msg': '模拟错误'})
            success, error = sync_client.insert_task(
                task_id="error_test",
                submission_time=datetime.now().isoformat(),
                task_status=0
            )
            assert success == False, "应该返回失败"
            assert "模拟错误" in error, "错误信息不正确"
            print_success(f"错误处理测试成功: {error}")

        print_info("[OK] 平台A通信测试全部通过")
        return True

    except AssertionError as e:
        print_fail(f"断言失败: {e}")
        return False
    except Exception as e:
        print_fail(f"异常: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== 测试4：完整流程 ====================

def test_end_to_end_workflow():
    """测试端到端工作流程"""
    print_test_header("测试4：端到端工作流程")

    test_db_path = "backend/test_tasks.db"

    # 删除旧数据库
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    try:
        # 1. 初始化组件
        tm = TaskManager(test_db_path)
        print_success("1. 任务管理器初始化")

        config = {
            'base_url': 'http://mock-platform-a.com',
            'task_insert_endpoint': '/simulApi/web-app/task-insert/',
            'task_update_endpoint': '/simulApi/web-app/task-update/',
            'timeout': 5
        }
        sync_client = PlatformSyncClient(config)
        print_success("2. 平台A客户端初始化")

        with requests_mock.Mocker() as m:
            # Mock平台A接口
            insert_url = f"{config['base_url']}{config['task_insert_endpoint']}"
            update_url = f"{config['base_url']}{config['task_update_endpoint']}"
            m.post(insert_url, json={'code': 0, 'msg': 'OK'})
            m.post(update_url, json={'code': 0, 'msg': 'OK'})

            # 2. 模拟平台A跳转到input.html（用户填写参数）
            task_id = "e2e_test_task_001"
            params = {
                "velocity_z": 1800.0,
                "bullet_yield_stress": 1100.0,
                "target_yield_stress": 850.0,
                "friction_static": 0.28,
                "friction_dynamic": 0.19,
                "simulation_endtime": 32.0
            }
            print_info(f"3. 模拟平台A跳转: /input.html?task_id={task_id}")

            # 3. 用户提交任务
            task = tm.submit_task(task_id, params)
            print_success(f"4. 用户提交任务成功: submission_time={task['submission_time']}")

            # 4. 调用平台A的task-insert
            success, error = sync_client.insert_task(
                task_id=task_id,
                submission_time=task['submission_time'],
                task_status=0
            )
            assert success, f"task-insert失败: {error}"
            print_success("5. 平台A task-insert调用成功")

            # 5. 开始生成K文件
            tm.start_task(task_id)
            print_success("6. K文件生成开始 (status=2)")

            # 6. 同步运行中状态到平台A
            task = tm.get_task(task_id)
            success, error = sync_client.update_task(
                task_id=task_id,
                task_status=2,
                start_time=task['start_time'],
                end_time="",
                error_message=""
            )
            assert success, f"task-update失败: {error}"
            print_success("7. 同步运行中状态到平台A")

            # 7. 模拟K文件生成完成
            tm.complete_task(task_id, "generated/e2e_test.k")
            print_success("8. K文件生成完成 (status=3)")

            # 8. 同步完成状态到平台A
            task = tm.get_task(task_id)
            success, error = sync_client.update_task(
                task_id=task_id,
                task_status=3,
                start_time=task['start_time'],
                end_time=task['end_time'],
                error_message=""
            )
            assert success, f"task-update失败: {error}"
            print_success("9. 同步完成状态到平台A")

            # 9. 标记已同步
            tm.mark_synced(task_id)
            print_success("10. 标记任务已同步")

            # 10. 验证最终状态
            task = tm.get_task(task_id)
            assert task['status'] == 3, "最终状态不正确"
            assert task['platform_a_synced'] == True, "同步标志未设置"
            assert task['output_file_path'] == "generated/e2e_test.k", "输出路径不正确"
            print_success("11. 最终状态验证成功")

            # 11. 模拟output.html查询结果
            print_info(f"12. 模拟用户访问: /output.html?task_id={task_id}")
            print_info(f"    - 状态: {TaskManager.get_status_name(task['status'])}")
            print_info(f"    - 输出文件: {task['output_file_path']}")
            print_info(f"    - 完成时间: {task['end_time']}")

        print_info("[OK] 端到端流程测试全部通过")
        return True

    except AssertionError as e:
        print_fail(f"断言失败: {e}")
        return False
    except Exception as e:
        print_fail(f"异常: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== 测试5：调度器 ====================

def test_scheduler():
    """测试后台调度器"""
    print_test_header("测试5：后台调度器")

    # 使用默认数据库路径（与scheduler内部一致）
    test_db_path = "backend/tasks.db"
    test_config_path = "backend/test_config.json"

    # 删除旧数据库
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    try:
        # 创建测试配置文件
        test_config = {
            "platform_a": {
                "enabled": True,
                "base_url": "http://mock-platform-a.com",
                "task_insert_endpoint": "/simulApi/web-app/task-insert/",
                "task_update_endpoint": "/simulApi/web-app/task-update/",
                "timeout": 5,
                "sync_interval": 2
            }
        }

        with open(test_config_path, 'w', encoding='utf-8') as f:
            json.dump(test_config, f, ensure_ascii=False, indent=2)
        print_success("测试配置文件创建成功")

        # 创建未同步任务
        tm = TaskManager(test_db_path)
        task_id = "scheduler_test_001"
        params = {"velocity_z": 1500.0, "bullet_yield_stress": 900.0}

        tm.submit_task(task_id, params)
        tm.start_task(task_id)
        tm.complete_task(task_id, "generated/scheduler_test.k")
        print_success(f"创建测试任务: {task_id}")

        # 验证任务未同步
        unsynced = tm.get_unsynced_tasks()
        assert len(unsynced) == 1, "应该有1个未同步任务"
        print_success(f"未同步任务数: {len(unsynced)}")

        # 初始化调度器（不启动）
        scheduler = TaskSyncScheduler(test_config_path)
        print_success("调度器初始化成功")

        # Mock sync_client的sync_task_status方法
        with patch.object(scheduler.sync_client, 'sync_task_status', return_value=(True, None)):
            # 手动调用同步方法（使用mock的sync_client）
            print_info("手动触发同步任务（模拟调度器执行）...")
            scheduler._sync_unsynced_tasks()

            # 验证任务已同步
            unsynced = tm.get_unsynced_tasks()
            assert len(unsynced) == 0, f"同步失败，仍有{len(unsynced)}个未同步任务"
            print_success("调度器成功同步任务")

        # 测试调度器启动和状态
        scheduler.start()
        print_success("调度器启动成功")

        # 获取调度器状态
        status = scheduler.get_scheduler_status()
        assert status['enabled'] == True, "调度器应该是启用状态"
        assert status['running'] == True, "调度器应该是运行状态"
        print_success(f"调度器状态: {json.dumps(status, ensure_ascii=False, indent=2)}")

        # 关闭调度器
        scheduler.shutdown()
        print_success("调度器关闭成功")

        # 清理测试文件
        if os.path.exists(test_config_path):
            os.remove(test_config_path)

        print_info("[OK] 调度器测试全部通过")
        return True

    except AssertionError as e:
        print_fail(f"断言失败: {e}")
        return False
    except Exception as e:
        print_fail(f"异常: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== 测试6：双模式隔离 ====================

def test_dual_mode():
    """测试双模式隔离：独立任务不会被同步到平台A"""
    print_test_header("测试6：双模式隔离")

    test_db_path = "backend/tasks.db"
    test_config_path = "backend/test_config.json"

    # 删除旧数据库
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    try:
        # 创建测试配置
        test_config = {
            "platform_a": {
                "enabled": True,
                "mode": "hybrid",
                "base_url": "http://mock-platform-a.com",
                "task_insert_endpoint": "/simulApi/web-app/task-insert/",
                "task_update_endpoint": "/simulApi/web-app/task-update/",
                "timeout": 5,
                "sync_interval": 2
            }
        }

        with open(test_config_path, 'w', encoding='utf-8') as f:
            json.dump(test_config, f, ensure_ascii=False, indent=2)
        print_success("测试配置文件创建成功")

        tm = TaskManager(test_db_path)

        # 创建1个独立任务和2个平台A任务
        standalone_task_id = "standalone_test_001"
        platform_task_id_1 = "platform_a_test_001"
        platform_task_id_2 = "platform_a_test_002"

        params = {"velocity_z": 1500.0, "bullet_yield_stress": 900.0}

        # 提交独立任务
        tm.submit_task(standalone_task_id, params, source='standalone')
        tm.start_task(standalone_task_id)
        tm.complete_task(standalone_task_id, "generated/standalone_test.k")
        print_success(f"创建独立任务: {standalone_task_id}")

        # 提交平台A任务
        tm.submit_task(platform_task_id_1, params, source='platform_a')
        tm.start_task(platform_task_id_1)
        tm.complete_task(platform_task_id_1, "generated/platform_a_test_1.k")
        print_success(f"创建平台A任务: {platform_task_id_1}")

        tm.submit_task(platform_task_id_2, params, source='platform_a')
        tm.start_task(platform_task_id_2)
        tm.complete_task(platform_task_id_2, "generated/platform_a_test_2.k")
        print_success(f"创建平台A任务: {platform_task_id_2}")

        # 验证数据库中有3个任务
        all_tasks = tm.db.get_all_tasks(limit=10)
        assert len(all_tasks) >= 3, f"应该有至少3个任务，实际有{len(all_tasks)}个"
        print_success(f"数据库中共有 {len(all_tasks)} 个任务")

        # 验证未同步任务只有2个（仅平台A任务）
        unsynced = tm.get_unsynced_tasks()
        assert len(unsynced) == 2, f"应该有2个未同步的平台A任务，实际有{len(unsynced)}个"
        print_success(f"未同步任务数: {len(unsynced)} (仅平台A任务)")

        # 验证未同步任务不包含独立任务
        unsynced_ids = [task['task_id'] for task in unsynced]
        assert standalone_task_id not in unsynced_ids, "独立任务不应该出现在未同步列表中"
        assert platform_task_id_1 in unsynced_ids, "平台A任务1应该在未同步列表中"
        assert platform_task_id_2 in unsynced_ids, "平台A任务2应该在未同步列表中"
        print_success("独立任务已被正确过滤，不会被同步")

        # 验证source字段
        standalone_task = tm.get_task(standalone_task_id)
        assert standalone_task['source'] == 'standalone', "独立任务source字段应为standalone"
        print_success(f"独立任务source验证: {standalone_task['source']}")

        platform_task = tm.get_task(platform_task_id_1)
        assert platform_task['source'] == 'platform_a', "平台A任务source字段应为platform_a"
        print_success(f"平台A任务source验证: {platform_task['source']}")

        # 使用mock测试调度器同步
        scheduler = TaskSyncScheduler(test_config_path)

        with patch.object(scheduler.sync_client, 'sync_task_status', return_value=(True, None)):
            print_info("手动触发调度器同步（模拟）...")
            scheduler._sync_unsynced_tasks()

            # 验证同步后，独立任务仍然存在且未被标记为已同步
            standalone_task_after = tm.get_task(standalone_task_id)
            assert standalone_task_after is not None, "独立任务应该仍然存在"
            assert standalone_task_after['platform_a_synced'] == 0, "独立任务不应该被标记为已同步"
            print_success("独立任务在同步后保持未同步状态（正确）")

            # 验证平台A任务已被标记为同步
            unsynced_after = tm.get_unsynced_tasks()
            assert len(unsynced_after) == 0, "所有平台A任务应该已被同步"
            print_success("平台A任务全部同步成功")

        # 清理测试配置文件
        if os.path.exists(test_config_path):
            os.remove(test_config_path)

        print_info("[OK] 双模式隔离测试全部通过")
        return True

    except AssertionError as e:
        print_fail(f"测试失败: {e}")
        return False
    except Exception as e:
        print_fail(f"异常: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== 主测试函数 ====================

def run_all_tests():
    """运行所有测试"""
    print(f"\n{TestColors.BOLD}{TestColors.HEADER}")
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║       平台A集成 - 综合集成测试                            ║")
    print("║       Bullet Penetration Simulation System                ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    print(f"{TestColors.ENDC}")

    results = {}

    # 执行测试
    results['database'] = test_database()
    results['task_manager'] = test_task_manager()
    results['platform_sync'] = test_platform_sync_with_mock()
    results['end_to_end'] = test_end_to_end_workflow()
    results['scheduler'] = test_scheduler()
    results['dual_mode'] = test_dual_mode()

    # 汇总结果
    print_test_header("测试结果汇总")

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    failed = total - passed

    for test_name, result in results.items():
        status = f"{TestColors.OKGREEN}[PASS]{TestColors.ENDC}" if result else f"{TestColors.FAIL}[FAIL]{TestColors.ENDC}"
        print(f"{test_name.ljust(20)}: {status}")

    print(f"\n{TestColors.BOLD}Total: {total} | Passed: {TestColors.OKGREEN}{passed}{TestColors.ENDC} | Failed: {TestColors.FAIL}{failed}{TestColors.ENDC}")

    if failed == 0:
        print(f"\n{TestColors.OKGREEN}{TestColors.BOLD}>>> All tests passed! System is working correctly.{TestColors.ENDC}")
        return 0
    else:
        print(f"\n{TestColors.FAIL}{TestColors.BOLD}>>> {failed} tests failed. Please check logs.{TestColors.ENDC}")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()

    # 清理测试数据库
    test_db_path = "backend/test_tasks.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
        print(f"\n{TestColors.OKCYAN}已清理测试数据库: {test_db_path}{TestColors.ENDC}")

    sys.exit(exit_code)
