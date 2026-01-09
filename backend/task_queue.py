#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
任务执行队列 - 串行执行引擎

设计原则：
1. 单Worker线程，保证串行执行
2. 内存队列 + 数据库持久化，重启可恢复
3. 线程安全的状态查询
4. 完整的任务流程：K文件生成 → LS-DYNA计算 → 后处理

状态流转：
    PENDING(0) → QUEUED(1) → GENERATING(2) → COMPUTING(6) → [POSTPROCESSING(7)] → COMPLETED(3)
                                   ↓              ↓              ↓
                               FAILED(4)     FAILED(4)       FAILED(4)
"""

import os
import sys
import json
import queue
import threading
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

from database import TaskStatus

# 平台交互模块（延迟导入，避免循环依赖）
def _get_platform_modules():
    """获取平台交互模块（延迟导入）"""
    try:
        from platform_notifier import PlatformNotifier
        from heartbeat_manager import get_heartbeat_manager
        return PlatformNotifier, get_heartbeat_manager
    except ImportError:
        return None, None

logger = logging.getLogger(__name__)


def _get_project_root() -> Path:
    """
    获取项目根目录，兼容开发模式和打包模式
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包模式：exe 所在目录
        return Path(sys.executable).parent
    else:
        # 开发模式：backend/ 的父目录
        return Path(__file__).parent.parent


class TaskQueue:
    """串行任务执行队列"""

    def __init__(self, task_manager, k_engine_factory, config: Dict[str, Any]):
        """
        初始化任务队列

        Args:
            task_manager: TaskManager 实例
            k_engine_factory: 返回 KFileEngine 实例的工厂函数
            config: 配置字典
        """
        self.tm = task_manager
        self.k_engine_factory = k_engine_factory
        self.config = config

        # 内存队列（FIFO）
        self._queue: queue.Queue = queue.Queue()

        # 当前执行任务
        self._running_task: Optional[str] = None
        self._running_since: Optional[datetime] = None
        self._current_stop_event: Optional[threading.Event] = None

        # 线程安全锁
        self._lock = threading.Lock()

        # Worker线程
        self._worker_thread: Optional[threading.Thread] = None
        self._shutdown = threading.Event()

        # 目录配置（统一为单一任务目录，兼容打包模式）
        project_root = _get_project_root()
        self._tasks_base_dir = project_root / config.get("tasks_base_dir", "tasks")

        # 确保目录存在
        self._tasks_base_dir.mkdir(parents=True, exist_ok=True)

        # LS-DYNA Runner（延迟初始化）
        self._lsdyna_runner = None

    def _get_lsdyna_runner(self):
        """获取或创建 LSDynaRunner 实例"""
        if self._lsdyna_runner is None:
            try:
                from lsdyna_runner import create_runner_from_config
                self._lsdyna_runner = create_runner_from_config(self.config)
            except ImportError as e:
                logger.error(f"无法导入 lsdyna_runner 模块: {e}")
                raise
        return self._lsdyna_runner

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

        # 中止当前任务
        if self._current_stop_event:
            self._current_stop_event.set()

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
            # 估算等待时间：基于配置的超时时间
            timeout_minutes = self.config.get("lsdyna_timeout_minutes", 60)
            estimated_wait = position * timeout_minutes * 60

            logger.info(f"[TaskQueue] 任务 {task_id} 加入队列，位置: {position}")

            return {
                "success": True,
                "queue_position": position,
                "estimated_wait_seconds": estimated_wait
            }

    def abort_task(self, task_id: str) -> bool:
        """
        中止任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功中止
        """
        with self._lock:
            # 如果是当前执行的任务，设置中止信号
            if self._running_task == task_id and self._current_stop_event:
                self._current_stop_event.set()
                logger.info(f"[TaskQueue] 发送中止信号: {task_id}")
                return True

            # 如果在队列中，移除
            queued_list = list(self._queue.queue)
            if task_id in queued_list:
                # 重建队列（排除该任务）
                new_queue = queue.Queue()
                for tid in queued_list:
                    if tid != task_id:
                        new_queue.put(tid)
                self._queue = new_queue

                # 更新数据库状态
                self.tm.abort_task(task_id)
                logger.info(f"[TaskQueue] 从队列移除: {task_id}")
                return True

        return False

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
            queued_tasks = self.tm.db.get_tasks_by_status(TaskStatus.QUEUED)
            for task in sorted(queued_tasks, key=lambda t: t.get('queued_at') or t.get('updated_at', '')):
                self._queue.put(task['task_id'])
                logger.info(f"[TaskQueue] 恢复排队任务: {task['task_id']}")

            # 恢复执行中但未完成的任务（status=2, 6, 7，可能上次崩溃）
            running_tasks = self.tm.db.get_running_tasks()
            for task in running_tasks:
                # 重置为排队中，重新执行
                self.tm.db.update_task_status(task['task_id'], status=TaskStatus.QUEUED)
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
                self._current_stop_event = threading.Event()

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
                    self._current_stop_event = None
                self._queue.task_done()

        logger.info("[TaskQueue] Worker 停止")

    def _execute_task(self, task_id: str):
        """
        执行单个任务（完整流程）

        Args:
            task_id: 任务ID
        """
        # 获取任务信息
        task = self.tm.get_task(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        params = task.get('input_params', {})
        enable_postprocess = task.get('enable_postprocess', False)

        # 创建任务目录（所有产出都在这个目录下）
        task_dir = self._tasks_base_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        try:
            # ===== 阶段1: 生成K文件 =====
            self.tm.db.update_task_status(
                task_id,
                status=TaskStatus.GENERATING,
                start_time=datetime.now().isoformat(),
                work_directory=str(task_dir),
                progress=10
            )

            if self._current_stop_event.is_set():
                self._handle_abort(task_id)
                return

            k_file_path, k_file_content = self._generate_k_file(task_id, params, task_dir)

            # 保存K文件内容到数据库
            self.tm.db.save_k_file_content(task_id, k_file_content)
            self.tm.db.update_task_progress(task_id, 20)

            # ===== 阶段2: LS-DYNA计算 =====
            self.tm.db.update_task_status(
                task_id,
                status=TaskStatus.COMPUTING,
                compute_start_time=datetime.now().isoformat(),
                progress=30
            )

            if self._current_stop_event.is_set():
                self._handle_abort(task_id)
                return

            lsdyna_result = self._run_lsdyna(task_id, k_file_path, task_dir)

            if self._current_stop_event.is_set():
                self._handle_abort(task_id)
                return

            # 检查LS-DYNA执行结果
            from lsdyna_runner import LSDynaStatus

            if lsdyna_result.status == LSDynaStatus.ABORTED:
                self._handle_abort(task_id)
                return

            if lsdyna_result.status != LSDynaStatus.SUCCESS:
                error_msg = lsdyna_result.error_message or f"LS-DYNA执行失败 (状态: {lsdyna_result.status})"
                self._handle_failure(task_id, error_msg, lsdyna_result, task_dir)
                return

            self.tm.db.update_task_status(
                task_id,
                status=TaskStatus.COMPUTING,
                compute_end_time=datetime.now().isoformat(),
                progress=70
            )

            # ===== 阶段3: 后处理（可选）=====
            gif_path = None
            if enable_postprocess and lsdyna_result.d3plot_path:
                self.tm.db.update_task_status(
                    task_id,
                    status=TaskStatus.POSTPROCESSING,
                    progress=80
                )

                gif_path = self._run_postprocess(task_id, lsdyna_result.d3plot_path, task_dir)

            # ===== 阶段4: 收集结果路径（无需复制，直接使用任务目录）=====
            self.tm.db.update_task_progress(task_id, 90)

            output_paths = self._get_result_paths(task_id, task_dir, lsdyna_result, gif_path)

            # ===== 完成 =====
            self.tm.db.update_task_status(
                task_id,
                status=TaskStatus.COMPLETED,
                end_time=datetime.now().isoformat(),
                output_file_path=output_paths.get("k_file"),
                gif_path=output_paths.get("gif"),
                d3hsp_path=output_paths.get("d3hsp"),
                progress=100
            )

            # 通知平台任务完成
            self._notify_platform_task_end(task_id, success=True, message="任务完成")
            logger.info(f"[TaskQueue] 任务完成: {task_id}")

        except Exception as e:
            logger.exception(f"[TaskQueue] 任务执行异常: {task_id}")
            self.tm.fail_task(task_id, str(e))

    def _generate_k_file(self, task_id: str, params: Dict[str, Any], work_dir: Path) -> tuple:
        """
        生成K文件

        Returns:
            (k_file_path, k_file_content)
        """
        engine = self.k_engine_factory()
        engine.replace_multiple_parameters(params)

        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary = engine.get_parameter_summary()
        filename = f"bullet_sim_{task_id[:16]}_{timestamp}_{summary}.k"
        k_file_path = work_dir / filename

        # 生成K文件
        engine.generate(str(k_file_path), metadata={
            "task_id": task_id,
            "source": "task_queue",
            "generated_at": datetime.now().isoformat()
        })

        # 读取内容
        with open(k_file_path, 'r', encoding='utf-8-sig') as f:
            k_file_content = f.read()

        logger.info(f"[TaskQueue] K文件生成: {k_file_path}")
        return k_file_path, k_file_content

    def _run_lsdyna(self, task_id: str, k_file_path: Path, work_dir: Path):
        """执行LS-DYNA计算"""
        runner = self._get_lsdyna_runner()

        def progress_callback(phase: str, progress: float):
            # 将LS-DYNA进度映射到30-70%
            mapped_progress = 30 + int(progress * 40)
            self.tm.db.update_task_progress(task_id, mapped_progress)

        result = runner.run(
            k_file_path=str(k_file_path),
            work_directory=str(work_dir),
            task_id=task_id,
            stop_event=self._current_stop_event,
            enable_postprocess=False,  # 后处理单独控制
            progress_callback=progress_callback
        )

        return result

    def _run_postprocess(self, task_id: str, d3plot_path: str, work_dir: Path) -> Optional[str]:
        """执行后处理生成GIF"""
        try:
            runner = self._get_lsdyna_runner()

            if runner.prepost_config:
                gif_filename = f"{task_id}.{runner.prepost_config.output_format}"
                gif_path = work_dir / gif_filename

                # 调用后处理
                result_gif = runner._run_postprocess(d3plot_path, str(work_dir), task_id)
                if result_gif and os.path.isfile(result_gif):
                    return result_gif

        except Exception as e:
            logger.warning(f"[TaskQueue] 后处理失败: {e}")

        return None

    def _get_result_paths(
        self,
        task_id: str,
        task_dir: Path,
        lsdyna_result,
        gif_path: Optional[str]
    ) -> Dict[str, Optional[str]]:
        """
        获取结果文件路径（直接返回任务目录中的路径，无需复制）

        设计原则：数据只存一份，消除不必要的复制

        Returns:
            输出文件路径字典
        """
        output_paths = {
            "k_file": None,
            "gif": None,
            "d3hsp": None
        }

        # K文件（直接在任务目录生成）
        k_files = list(task_dir.glob("*.k"))
        if k_files:
            output_paths["k_file"] = str(k_files[0])

        # d3hsp文件（LS-DYNA原地生成）
        if lsdyna_result.d3hsp_path and os.path.isfile(lsdyna_result.d3hsp_path):
            output_paths["d3hsp"] = lsdyna_result.d3hsp_path

        # GIF文件（后处理原地生成）
        if gif_path and os.path.isfile(gif_path):
            output_paths["gif"] = gif_path

        return output_paths

    def _handle_abort(self, task_id: str):
        """处理任务中止"""
        self.tm.abort_task(task_id)
        self._notify_platform_task_end(task_id, success=False, message="任务被中止")
        logger.info(f"[TaskQueue] 任务被中止: {task_id}")

    def _handle_failure(self, task_id: str, error_msg: str, lsdyna_result, task_dir: Path):
        """处理任务失败"""
        # 错误日志直接在任务目录中（无需复制）
        error_log_path = None
        if lsdyna_result.stderr_log and os.path.isfile(lsdyna_result.stderr_log):
            error_log_path = lsdyna_result.stderr_log

        self.tm.db.update_task_status(
            task_id,
            status=TaskStatus.FAILED,
            end_time=datetime.now().isoformat(),
            error_message=error_msg,
            error_log_path=error_log_path
        )

        self._notify_platform_task_end(task_id, success=False, message=error_msg)
        logger.error(f"[TaskQueue] 任务失败: {task_id} - {error_msg}")

    def _notify_platform_task_end(self, task_id: str, success: bool, message: str = ""):
        """
        通知平台任务结束并停止心跳

        仅对平台任务生效（platform_api_url不为空）

        Args:
            task_id: 任务ID
            success: 是否成功
            message: 附加消息
        """
        try:
            # 获取任务信息
            task = self.tm.get_task(task_id)
            if not task:
                return

            platform_api_url = task.get('platform_api_url')
            if not platform_api_url:
                # 非平台任务，无需通知
                return

            # 获取平台模块
            PlatformNotifier, get_heartbeat_manager = _get_platform_modules()
            if PlatformNotifier is None:
                logger.warning("[TaskQueue] 平台模块不可用，跳过通知")
                return

            # 停止心跳
            heartbeat_mgr = get_heartbeat_manager()
            heartbeat_mgr.stop_heartbeat(task_id)

            # 通知平台
            # 构建配置（从任务中获取platform_api_url）
            notifier = PlatformNotifier({
                'enabled': True,
                'platform_api_url': platform_api_url,
                'request_timeout_seconds': 10
            })
            notifier.notify_completion(task_id, success, message)

            logger.info(f"[TaskQueue] 平台通知已发送: {task_id} (success={success})")

        except Exception as e:
            logger.error(f"[TaskQueue] 平台通知失败: {task_id} - {e}")


# 全局单例
_task_queue_instance: Optional[TaskQueue] = None


def get_task_queue() -> Optional[TaskQueue]:
    """获取任务队列单例"""
    return _task_queue_instance


def init_task_queue(task_manager, k_engine_factory, config: Dict[str, Any]) -> TaskQueue:
    """
    初始化任务队列单例

    Args:
        task_manager: TaskManager 实例
        k_engine_factory: 返回 KFileEngine 实例的工厂函数
        config: 配置字典

    Returns:
        TaskQueue 实例
    """
    global _task_queue_instance
    if _task_queue_instance is None:
        _task_queue_instance = TaskQueue(task_manager, k_engine_factory, config)
        _task_queue_instance.start()
    return _task_queue_instance


def shutdown_task_queue():
    """关闭任务队列"""
    global _task_queue_instance
    if _task_queue_instance:
        _task_queue_instance.shutdown()
        _task_queue_instance = None
