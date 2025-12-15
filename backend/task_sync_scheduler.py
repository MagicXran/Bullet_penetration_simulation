#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
后台任务调度器

负责周期性同步任务状态到平台A
使用APScheduler实现简单可靠的调度机制
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from task_manager import TaskManager
from platform_sync import PlatformSyncClient


logger = logging.getLogger(__name__)

# 抑制APScheduler执行器的垃圾日志（每5秒执行一次即使无任务也输出INFO）
# 只保留WARNING及以上级别，避免日志污染
logging.getLogger('apscheduler.executors.default').setLevel(logging.WARNING)
logging.getLogger('apscheduler.scheduler').setLevel(logging.WARNING)


class TaskSyncScheduler:
    """任务同步调度器"""

    def __init__(self, config_path: str = "backend/config.json"):
        """
        初始化调度器

        Args:
            config_path: 配置文件路径
        """
        self.config = self._load_config(config_path)
        self.platform_a_enabled = self.config.get('enabled', False)

        if not self.platform_a_enabled:
            logger.info("平台A集成已禁用（config.platform_a.enabled=false）")
            self.scheduler = None
            self.sync_client = None
            return

        # 初始化组件
        self.task_manager = TaskManager()
        self.sync_client = PlatformSyncClient(self.config)

        # 创建调度器
        self.scheduler = BackgroundScheduler()
        self.sync_interval = self.config.get('sync_interval', 5)

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """
        加载配置文件

        Args:
            config_path: 配置文件路径

        Returns:
            平台A配置字典
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                full_config = json.load(f)
                return full_config.get('platform_a', {})
        except FileNotFoundError:
            logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
            return {'enabled': False}
        except json.JSONDecodeError as e:
            logger.error(f"配置文件格式错误: {e}")
            return {'enabled': False}

    def start(self):
        """启动调度器"""
        if not self.platform_a_enabled:
            logger.info("平台A集成未启用，跳过调度器启动")
            return

        if self.scheduler is None:
            logger.error("调度器未初始化")
            return

        # 添加同步任务
        self.scheduler.add_job(
            func=self._sync_unsynced_tasks,
            trigger=IntervalTrigger(seconds=self.sync_interval),
            id='sync_tasks',
            name='同步未同步任务到平台A',
            replace_existing=True
        )

        # 启动调度器
        self.scheduler.start()
        logger.info(f"任务同步调度器已启动，同步间隔: {self.sync_interval}秒")

    def shutdown(self):
        """关闭调度器"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("任务同步调度器已关闭")

    def _sync_unsynced_tasks(self):
        """
        同步未同步的任务到平台A

        这是调度器的核心方法，每隔sync_interval秒执行一次
        """
        try:
            # 获取所有未同步的任务
            unsynced_tasks = self.task_manager.get_unsynced_tasks(limit=100)

            if not unsynced_tasks:
                logger.debug("没有需要同步的任务")
                return

            logger.info(f"发现 {len(unsynced_tasks)} 个未同步任务，开始同步")

            for task in unsynced_tasks:
                task_id = task['task_id']

                try:
                    # 调用同步客户端
                    success, error_msg = self.sync_client.sync_task_status(task)

                    if success:
                        # 同步成功，标记为已同步
                        self.task_manager.mark_synced(task_id)
                        logger.info(f"任务 {task_id} 同步成功")
                    else:
                        # 同步失败，增加重试次数
                        retry_count = self.task_manager.increment_sync_retry(task_id)
                        logger.warning(
                            f"任务 {task_id} 同步失败（重试次数: {retry_count}/3）: {error_msg}"
                        )

                        if retry_count >= 3:
                            logger.error(
                                f"任务 {task_id} 同步失败次数超过3次，已放弃同步。"
                                f"请检查平台A连接或手动处理。"
                            )

                except Exception as e:
                    logger.error(f"同步任务 {task_id} 时发生异常: {str(e)}", exc_info=True)
                    self.task_manager.increment_sync_retry(task_id)

        except Exception as e:
            logger.error(f"同步任务过程中发生异常: {str(e)}", exc_info=True)

    def get_scheduler_status(self) -> Dict[str, Any]:
        """
        获取调度器状态

        Returns:
            状态信息字典
        """
        if not self.platform_a_enabled:
            return {
                'enabled': False,
                'message': '平台A集成未启用'
            }

        if self.scheduler is None:
            return {
                'enabled': True,
                'running': False,
                'message': '调度器未初始化'
            }

        jobs = self.scheduler.get_jobs()
        return {
            'enabled': True,
            'running': self.scheduler.running,
            'sync_interval': self.sync_interval,
            'jobs_count': len(jobs),
            'jobs': [
                {
                    'id': job.id,
                    'name': job.name,
                    'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None
                }
                for job in jobs
            ]
        }
