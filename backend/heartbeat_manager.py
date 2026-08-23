#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
心跳管理器 - 管理平台任务的心跳线程

功能：
1. 为每个平台任务启动独立的心跳线程
2. 每30秒发送一次心跳，counter从1递增到30000循环
3. 任务完成/失败时自动停止心跳
4. 应用关闭时清理所有心跳线程

基于 app_platform_interface.md v1.5.0 设计
"""

import threading
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)


class HeartbeatThread(threading.Thread):
    """
    单个任务的心跳线程

    每隔 interval 秒发送一次心跳，counter 从1递增到30000循环
    """

    MAX_COUNTER = 30000

    def __init__(
        self,
        task_id: str,
        send_heartbeat_func: Callable[[str, int, int], tuple],
        get_task_status_func: Callable[[str], Optional[int]],
        interval: int = 30
    ):
        """
        初始化心跳线程

        Args:
            task_id: 任务ID
            send_heartbeat_func: 发送心跳的函数，签名: (task_id, counter, status) -> (success, error)
            get_task_status_func: 获取任务状态的函数，签名: (task_id) -> status
            interval: 心跳间隔（秒），默认30秒
        """
        super().__init__(daemon=True)
        self.task_id = task_id
        self.send_heartbeat = send_heartbeat_func
        self.get_task_status = get_task_status_func
        self.interval = interval
        self.counter = 0
        self._stop_event = threading.Event()
        self.name = f"Heartbeat-{task_id[:8]}"

    def run(self):
        """线程主循环"""
        logger.info(f"[{self.task_id}] 心跳线程启动，间隔 {self.interval} 秒")

        while not self._stop_event.is_set():
            # 等待间隔时间，同时检查停止信号
            if self._stop_event.wait(timeout=self.interval):
                break

            # 递增计数器（1-30000循环）
            self.counter = (self.counter % self.MAX_COUNTER) + 1

            try:
                # 获取当前任务状态
                status = self.get_task_status(self.task_id)

                if status is None:
                    logger.warning(f"[{self.task_id}] 任务不存在，停止心跳")
                    break

                # 检查是否是终态（完成/失败/中止）
                if status in (3, 4, 5):  # COMPLETED, FAILED, ABORTED
                    logger.info(f"[{self.task_id}] 任务已结束(status={status})，停止心跳")
                    break

                # 发送心跳
                success, error = self.send_heartbeat(self.task_id, self.counter, status)

                if success:
                    logger.debug(f"[{self.task_id}] 心跳发送成功 (counter={self.counter})")
                else:
                    logger.warning(f"[{self.task_id}] 心跳发送失败: {error}")

            except Exception as e:
                logger.error(f"[{self.task_id}] 心跳发送异常: {e}", exc_info=True)

        logger.info(f"[{self.task_id}] 心跳线程已停止")

    def stop(self):
        """停止心跳线程"""
        logger.debug(f"[{self.task_id}] 请求停止心跳线程")
        self._stop_event.set()


class HeartbeatManager:
    """
    心跳管理器 - 单例模式

    管理所有平台任务的心跳线程
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        notifier=None,
        db=None,
        interval: int = 30
    ):
        """
        初始化心跳管理器

        Args:
            notifier: PlatformNotifier实例
            db: Database实例（用于获取任务状态）
            interval: 心跳间隔（秒），默认30秒
        """
        if self._initialized:
            return

        self._heartbeats: Dict[str, HeartbeatThread] = {}
        self._heartbeats_lock = threading.Lock()
        self.notifier = notifier
        self.db = db
        self.interval = interval
        self._initialized = True

        logger.info(f"心跳管理器初始化完成，间隔 {interval} 秒")

    def set_dependencies(self, notifier, db):
        """
        设置依赖（延迟注入）

        Args:
            notifier: PlatformNotifier实例
            db: Database实例
        """
        self.notifier = notifier
        self.db = db
        logger.debug("心跳管理器依赖已设置")

    def start_heartbeat(self, task_id: str) -> bool:
        """
        为任务启动心跳

        Args:
            task_id: 任务ID

        Returns:
            是否成功启动
        """
        with self._heartbeats_lock:
            # 检查是否已存在
            if task_id in self._heartbeats:
                logger.debug(f"[{task_id}] 心跳线程已存在，跳过")
                return True

            # 检查依赖
            if self.notifier is None or self.db is None:
                logger.error(f"[{task_id}] 心跳管理器依赖未设置，无法启动心跳")
                return False

            # 创建并启动心跳线程
            thread = HeartbeatThread(
                task_id=task_id,
                send_heartbeat_func=self.notifier.send_heartbeat,
                get_task_status_func=self._get_task_status,
                interval=self.interval
            )
            thread.start()

            self._heartbeats[task_id] = thread
            logger.info(f"[{task_id}] 心跳线程已启动")
            return True

    def stop_heartbeat(self, task_id: str) -> bool:
        """
        停止任务的心跳

        Args:
            task_id: 任务ID

        Returns:
            是否成功停止
        """
        with self._heartbeats_lock:
            if task_id not in self._heartbeats:
                logger.debug(f"[{task_id}] 心跳线程不存在，无需停止")
                return True

            thread = self._heartbeats.pop(task_id)
            thread.stop()
            logger.info(f"[{task_id}] 心跳线程已停止")
            return True

    def stop_all(self):
        """停止所有心跳线程"""
        with self._heartbeats_lock:
            count = len(self._heartbeats)
            if count == 0:
                logger.debug("没有活跃的心跳线程")
                return

            logger.info(f"正在停止 {count} 个心跳线程...")
            for task_id, thread in list(self._heartbeats.items()):
                thread.stop()
            self._heartbeats.clear()
            logger.info("所有心跳线程已停止")

    def get_active_count(self) -> int:
        """获取活跃的心跳线程数量"""
        with self._heartbeats_lock:
            return len(self._heartbeats)

    def is_heartbeat_running(self, task_id: str) -> bool:
        """检查任务的心跳是否正在运行"""
        with self._heartbeats_lock:
            if task_id not in self._heartbeats:
                return False
            return self._heartbeats[task_id].is_alive()

    def _get_task_status(self, task_id: str) -> Optional[int]:
        """获取任务状态（包装器）"""
        if self.db is None:
            return None
        task = self.db.get_task(task_id)
        return task.get('status') if task else None


# 全局单例
_heartbeat_manager: Optional[HeartbeatManager] = None


def get_heartbeat_manager() -> HeartbeatManager:
    """获取心跳管理器单例"""
    global _heartbeat_manager
    if _heartbeat_manager is None:
        _heartbeat_manager = HeartbeatManager()
    return _heartbeat_manager


def init_heartbeat_manager(notifier, db, interval: int = 30) -> HeartbeatManager:
    """
    初始化心跳管理器

    Args:
        notifier: PlatformNotifier实例
        db: Database实例
        interval: 心跳间隔（秒）

    Returns:
        HeartbeatManager实例
    """
    manager = get_heartbeat_manager()
    manager.set_dependencies(notifier, db)
    manager.interval = interval
    return manager


def shutdown_heartbeat_manager():
    """关闭心跳管理器"""
    global _heartbeat_manager
    if _heartbeat_manager is not None:
        _heartbeat_manager.stop_all()
        logger.info("心跳管理器已关闭")
