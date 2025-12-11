#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
任务执行队列 - 串行执行引擎

设计原则：
1. 单Worker线程，保证串行执行
2. 内存队列 + 数据库持久化，重启可恢复
3. 线程安全的状态查询
4. 全局超时保护（默认5分钟）

MVP版本：核心功能验证
"""

import queue
import threading
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)


class TaskQueue:
    """串行任务执行队列"""

    # 全局超时配置（秒）
    EXECUTION_TIMEOUT = 300  # 5分钟

    def __init__(self, task_manager, k_engine_factory):
        """
        初始化任务队列

        Args:
            task_manager: TaskManager 实例
            k_engine_factory: 返回 KFileEngine 实例的工厂函数
        """
        self.tm = task_manager
        self.k_engine_factory = k_engine_factory

        # 内存队列（FIFO）
        self._queue: queue.Queue = queue.Queue()

        # 当前执行任务
        self._running_task: Optional[str] = None
        self._running_since: Optional[datetime] = None

        # 线程安全锁
        self._lock = threading.Lock()

        # Worker线程
        self._worker_thread: Optional[threading.Thread] = None
        self._shutdown = threading.Event()

        # 输出目录
        self._output_dir = Path(__file__).parent.parent / "generated"
        self._output_dir.mkdir(exist_ok=True)

    def start(self):
        """启动队列服务"""
        # 1. 从数据库恢复未完成的任务
        self._recover_from_database()

        # 2. 启动Worker线程
        self._shutdown.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="TaskQueueWorker",
            daemon=True
        )
        self._worker_thread.start()
        logger.info("[TaskQueue] 启动成功")

    def shutdown(self):
        """关闭队列服务"""
        self._shutdown.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10)
        logger.info("[TaskQueue] 已关闭")

    def enqueue(self, task_id: str) -> Dict[str, Any]:
        """
        将任务加入队列

        Args:
            task_id: 任务ID

        Returns:
            {
                "success": True,
                "queue_position": int,
                "estimated_wait_seconds": float
            }
        """
        with self._lock:
            # 更新数据库状态为排队中
            self.tm.queue_task(task_id)

            # 加入内存队列
            self._queue.put(task_id)

            position = self._queue.qsize()
            estimated_wait = position * 10  # 假设每个任务10秒

            logger.info(f"[TaskQueue] 任务 {task_id} 加入队列，位置: {position}")

            return {
                "success": True,
                "queue_position": position,
                "estimated_wait_seconds": estimated_wait
            }

    def get_status(self) -> Dict[str, Any]:
        """获取队列状态（线程安全）"""
        with self._lock:
            running_info = None
            if self._running_task:
                elapsed = (datetime.now() - self._running_since).total_seconds()
                running_info = {
                    "task_id": self._running_task,
                    "started_at": self._running_since.isoformat(),
                    "elapsed_seconds": round(elapsed, 2)
                }

            # 获取队列中的任务列表
            queued_list = list(self._queue.queue)

            return {
                "is_running": self._running_task is not None,
                "running_task": running_info,
                "queue_length": len(queued_list),
                "queued_tasks": [
                    {"task_id": tid, "position": i + 1}
                    for i, tid in enumerate(queued_list)
                ]
            }

    def get_task_position(self, task_id: str) -> Optional[int]:
        """
        查询任务在队列中的位置（1-based）

        Args:
            task_id: 任务ID

        Returns:
            队列位置，不在队列返回None
        """
        with self._lock:
            # 检查是否正在执行
            if self._running_task == task_id:
                return 0  # 0表示正在执行

            queued_list = list(self._queue.queue)
            try:
                return queued_list.index(task_id) + 1
            except ValueError:
                return None

    def _recover_from_database(self):
        """从数据库恢复未完成的任务"""
        try:
            # 获取排队中的任务（status=1）
            queued_tasks = self.tm.db.get_tasks_by_status(1) if hasattr(self.tm.db, 'get_tasks_by_status') else []
            for task in sorted(queued_tasks, key=lambda t: t.get('queued_at') or t.get('updated_at', '')):
                self._queue.put(task['task_id'])
                logger.info(f"[TaskQueue] 恢复排队任务: {task['task_id']}")

            # 恢复执行中但未完成的任务（status=2，可能上次崩溃）
            running_tasks = self.tm.db.get_tasks_by_status(2) if hasattr(self.tm.db, 'get_tasks_by_status') else []
            for task in running_tasks:
                # 重置为排队中，重新执行
                self.tm.db.update_task_status(task['task_id'], status=1)
                self._queue.put(task['task_id'])
                logger.warning(f"[TaskQueue] 恢复中断任务: {task['task_id']}")

        except Exception as e:
            logger.warning(f"[TaskQueue] 恢复任务失败（可能是新数据库）: {e}")

    def _worker_loop(self):
        """Worker线程主循环"""
        logger.info("[TaskQueue] Worker 启动")

        while not self._shutdown.is_set():
            try:
                # 阻塞等待任务，超时1秒
                task_id = self._queue.get(timeout=1)
            except queue.Empty:
                continue

            # 记录当前执行任务
            with self._lock:
                self._running_task = task_id
                self._running_since = datetime.now()

            logger.info(f"[TaskQueue] 开始执行: {task_id}")

            try:
                self._execute_task(task_id)
                logger.info(f"[TaskQueue] 执行完成: {task_id}")
            except Exception as e:
                logger.error(f"[TaskQueue] 执行失败 {task_id}: {e}")
                self.tm.fail_task(task_id, str(e))
            finally:
                # 清除当前执行任务
                with self._lock:
                    self._running_task = None
                    self._running_since = None
                self._queue.task_done()

        logger.info("[TaskQueue] Worker 停止")

    def _execute_task(self, task_id: str):
        """
        执行单个任务（带超时保护）

        Args:
            task_id: 任务ID
        """
        # 1. 更新状态为执行中
        self.tm.start_task(task_id)

        # 2. 获取任务参数
        task = self.tm.get_task(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        params = task.get('input_params', {})

        # 3. 使用线程执行，带超时检测
        result = {"success": False, "error": None, "output_path": None}

        def run_task():
            try:
                # 获取K文件引擎
                engine = self.k_engine_factory()

                # 替换参数
                engine.replace_multiple_parameters(params)

                # 生成输出文件路径
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                summary = engine.get_parameter_summary()
                filename = f"bullet_sim_{task_id[:16]}_{timestamp}_{summary}.k"
                output_path = self._output_dir / filename

                # 生成K文件
                engine.generate(str(output_path), metadata={
                    "task_id": task_id,
                    "source": "task_queue",
                    "generated_at": datetime.now().isoformat()
                })

                result["success"] = True
                result["output_path"] = str(output_path)

            except Exception as e:
                result["error"] = str(e)
                logger.exception(f"[TaskQueue] 任务执行异常: {task_id}")

        # 4. 启动执行线程
        exec_thread = threading.Thread(
            target=run_task,
            name=f"TaskExec-{task_id[:8]}"
        )
        exec_thread.start()
        exec_thread.join(timeout=self.EXECUTION_TIMEOUT)

        # 5. 检查超时
        if exec_thread.is_alive():
            error_msg = f"执行超时（>{self.EXECUTION_TIMEOUT}秒），任务被终止"
            self.tm.fail_task(task_id, error_msg)
            logger.error(f"[TaskQueue] 任务超时: {task_id}")
            # 注意：Python无法强制终止线程，但已标记任务失败
            return

        # 6. 检查执行结果
        if result["success"]:
            self.tm.complete_task(task_id, result["output_path"])
        else:
            self.tm.fail_task(task_id, result["error"] or "未知错误")


# 全局单例
_task_queue_instance: Optional[TaskQueue] = None


def get_task_queue() -> Optional[TaskQueue]:
    """获取任务队列单例"""
    return _task_queue_instance


def init_task_queue(task_manager, k_engine_factory) -> TaskQueue:
    """
    初始化任务队列单例

    Args:
        task_manager: TaskManager 实例
        k_engine_factory: 返回 KFileEngine 实例的工厂函数

    Returns:
        TaskQueue 实例
    """
    global _task_queue_instance
    if _task_queue_instance is None:
        _task_queue_instance = TaskQueue(task_manager, k_engine_factory)
        _task_queue_instance.start()
    return _task_queue_instance


def shutdown_task_queue():
    """关闭任务队列"""
    global _task_queue_instance
    if _task_queue_instance:
        _task_queue_instance.shutdown()
        _task_queue_instance = None
