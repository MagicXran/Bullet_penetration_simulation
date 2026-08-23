#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库操作层 - SQLite数据库封装

遵循第一性原理：一张表解决所有任务状态管理问题

状态码定义：
    0 - 待提交 (pending)
    1 - 排队中 (queued)
    2 - 生成K文件中 (generating)
    3 - 已完成 (completed)
    4 - 失败 (failed)
    5 - 已中止 (aborted)
    6 - LS-DYNA计算中 (computing)
    7 - 后处理中 (postprocessing)
"""

import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
from contextlib import contextmanager
from enum import IntEnum


class TaskStatus(IntEnum):
    """任务状态枚举"""
    PENDING = 0           # 待提交
    QUEUED = 1            # 排队中
    GENERATING = 2        # 生成K文件中
    COMPLETED = 3         # 已完成
    FAILED = 4            # 失败
    ABORTED = 5           # 已中止
    COMPUTING = 6         # LS-DYNA计算中
    POSTPROCESSING = 7    # 后处理中

    @classmethod
    def get_display_name(cls, status: int) -> str:
        """获取状态显示名称"""
        names = {
            0: "待提交",
            1: "排队中",
            2: "生成K文件中",
            3: "已完成",
            4: "失败",
            5: "已中止",
            6: "计算中",
            7: "后处理中"
        }
        return names.get(status, "未知")


class Database:
    """SQLite数据库管理器"""

    def __init__(self, db_path: str = "backend/tasks.db"):
        """
        初始化数据库连接

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    @contextmanager
    def get_connection(self):
        """
        获取数据库连接（上下文管理器）

        使用方法：
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(...)
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # 使查询结果可以像字典一样访问
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_database(self):
        """初始化数据库表结构"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 创建任务表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL DEFAULT 'standalone',
                    input_params TEXT NOT NULL,
                    output_file_path TEXT,
                    status INTEGER NOT NULL DEFAULT 0,
                    submission_time TEXT,
                    queued_at TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    error_message TEXT,
                    platform_a_synced INTEGER DEFAULT 0,
                    sync_retry_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_status
                ON tasks(status)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_platform_a_synced
                ON tasks(platform_a_synced, source, status)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_source
                ON tasks(source)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at
                ON tasks(created_at DESC)
            """)

            # 添加新列（如果不存在）
            new_columns = [
                ("queued_at", "TEXT"),
                ("k_file_content", "TEXT"),           # K文件内容
                ("work_directory", "TEXT"),           # 工作目录路径
                ("gif_path", "TEXT"),                 # GIF动画文件路径
                ("d3hsp_path", "TEXT"),               # d3hsp日志文件路径
                ("error_log_path", "TEXT"),           # 错误日志文件路径
                ("enable_postprocess", "INTEGER DEFAULT 0"),  # 是否启用后处理
                ("compute_start_time", "TEXT"),       # 计算开始时间
                ("compute_end_time", "TEXT"),         # 计算结束时间
                ("progress", "INTEGER DEFAULT 0"),    # 进度百分比 (0-100)
                # 平台交互新增字段
                ("platform_api_url", "TEXT"),         # 平台API地址（有值=平台任务）
                ("callback_url", "TEXT"),             # App回调URL（供平台触发执行）
                ("heartbeat_counter", "INTEGER DEFAULT 0"),  # 心跳计数器 (1-30000循环)
            ]

            for col_name, col_type in new_columns:
                try:
                    cursor.execute(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_type}")
                except sqlite3.OperationalError:
                    pass  # 列已存在，忽略错误

            # 创建 queued_at 相关索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_status_queued
                ON tasks(status, queued_at)
            """)

    def create_task(
        self,
        task_id: str,
        input_params: Dict[str, Any],
        source: str = 'standalone',
        enable_postprocess: bool = False,
        platform_api_url: Optional[str] = None,
        callback_url: Optional[str] = None
    ) -> bool:
        """
        创建新任务

        Args:
            task_id: 任务ID
            input_params: 输入参数字典
            source: 任务来源 ('standalone' | 'platform')
            enable_postprocess: 是否启用后处理
            platform_api_url: 平台API地址（有值表示平台任务）
            callback_url: App回调URL（供平台触发执行）

        Returns:
            是否创建成功
        """
        now = datetime.now().isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO tasks (
                        task_id, source, input_params, status,
                        enable_postprocess, platform_api_url, callback_url,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?)
                """, (task_id, source, json.dumps(input_params),
                      1 if enable_postprocess else 0,
                      platform_api_url, callback_url, now, now))
                return True
            except sqlite3.IntegrityError:
                # task_id已存在
                return False

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        根据task_id查询任务

        Args:
            task_id: 任务ID

        Returns:
            任务字典或None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tasks WHERE task_id = ?
            """, (task_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_dict(row)
            return None

    def update_task_status(
        self,
        task_id: str,
        status: int,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        error_message: Optional[str] = None,
        output_file_path: Optional[str] = None,
        queued_at: Optional[str] = None,
        k_file_content: Optional[str] = None,
        work_directory: Optional[str] = None,
        gif_path: Optional[str] = None,
        d3hsp_path: Optional[str] = None,
        error_log_path: Optional[str] = None,
        compute_start_time: Optional[str] = None,
        compute_end_time: Optional[str] = None,
        progress: Optional[int] = None
    ) -> bool:
        """
        更新任务状态

        Args:
            task_id: 任务ID
            status: 状态码 (参见 TaskStatus 枚举)
            start_time: 开始时间
            end_time: 结束时间
            error_message: 错误信息
            output_file_path: 输出文件路径
            queued_at: 加入队列时间
            k_file_content: K文件内容
            work_directory: 工作目录路径
            gif_path: GIF文件路径
            d3hsp_path: d3hsp文件路径
            error_log_path: 错误日志路径
            compute_start_time: 计算开始时间
            compute_end_time: 计算结束时间
            progress: 进度百分比

        Returns:
            是否更新成功
        """
        now = datetime.now().isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 构建动态更新SQL
            fields = ["status = ?", "updated_at = ?"]
            values = [status, now]

            optional_fields = [
                ("start_time", start_time),
                ("end_time", end_time),
                ("error_message", error_message),
                ("output_file_path", output_file_path),
                ("queued_at", queued_at),
                ("k_file_content", k_file_content),
                ("work_directory", work_directory),
                ("gif_path", gif_path),
                ("d3hsp_path", d3hsp_path),
                ("error_log_path", error_log_path),
                ("compute_start_time", compute_start_time),
                ("compute_end_time", compute_end_time),
                ("progress", progress),
            ]

            for field_name, field_value in optional_fields:
                if field_value is not None:
                    fields.append(f"{field_name} = ?")
                    values.append(field_value)

            # 状态变化时重置同步标志
            fields.append("platform_a_synced = 0")

            values.append(task_id)

            sql = f"UPDATE tasks SET {', '.join(fields)} WHERE task_id = ?"
            cursor.execute(sql, values)

            return cursor.rowcount > 0

    def update_task_progress(self, task_id: str, progress: int) -> bool:
        """
        更新任务进度

        Args:
            task_id: 任务ID
            progress: 进度百分比 (0-100)

        Returns:
            是否更新成功
        """
        now = datetime.now().isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks
                SET progress = ?, updated_at = ?
                WHERE task_id = ?
            """, (progress, now, task_id))

            return cursor.rowcount > 0

    def update_task_result_paths(
        self,
        task_id: str,
        gif_path: Optional[str] = None,
        d3hsp_path: Optional[str] = None,
        error_log_path: Optional[str] = None
    ) -> bool:
        """
        更新任务结果文件路径

        Args:
            task_id: 任务ID
            gif_path: GIF文件路径
            d3hsp_path: d3hsp文件路径
            error_log_path: 错误日志路径

        Returns:
            是否更新成功
        """
        now = datetime.now().isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()

            fields = ["updated_at = ?"]
            values = [now]

            if gif_path is not None:
                fields.append("gif_path = ?")
                values.append(gif_path)

            if d3hsp_path is not None:
                fields.append("d3hsp_path = ?")
                values.append(d3hsp_path)

            if error_log_path is not None:
                fields.append("error_log_path = ?")
                values.append(error_log_path)

            values.append(task_id)

            sql = f"UPDATE tasks SET {', '.join(fields)} WHERE task_id = ?"
            cursor.execute(sql, values)

            return cursor.rowcount > 0

    def save_k_file_content(self, task_id: str, k_file_content: str) -> bool:
        """
        保存K文件内容

        Args:
            task_id: 任务ID
            k_file_content: K文件内容

        Returns:
            是否保存成功
        """
        now = datetime.now().isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks
                SET k_file_content = ?, updated_at = ?
                WHERE task_id = ?
            """, (k_file_content, now, task_id))

            return cursor.rowcount > 0

    def update_task_submission_time(self, task_id: str, submission_time: str) -> bool:
        """
        更新任务提交时间

        Args:
            task_id: 任务ID
            submission_time: 提交时间

        Returns:
            是否更新成功
        """
        now = datetime.now().isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks
                SET submission_time = ?, updated_at = ?
                WHERE task_id = ?
            """, (submission_time, now, task_id))

            return cursor.rowcount > 0

    def mark_as_synced(self, task_id: str) -> bool:
        """
        标记任务已同步到平台A

        Args:
            task_id: 任务ID

        Returns:
            是否标记成功
        """
        now = datetime.now().isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks
                SET platform_a_synced = 1, updated_at = ?
                WHERE task_id = ?
            """, (now, task_id))

            return cursor.rowcount > 0

    def increment_sync_retry(self, task_id: str) -> int:
        """
        增加同步重试次数

        Args:
            task_id: 任务ID

        Returns:
            当前重试次数
        """
        now = datetime.now().isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks
                SET sync_retry_count = sync_retry_count + 1,
                    updated_at = ?
                WHERE task_id = ?
            """, (now, task_id))

            cursor.execute("""
                SELECT sync_retry_count FROM tasks WHERE task_id = ?
            """, (task_id,))

            row = cursor.fetchone()
            return row[0] if row else 0

    def get_unsynced_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取未同步到平台A的任务

        仅返回source='platform_a'的任务，独立任务不会被同步

        Args:
            limit: 最大返回数量

        Returns:
            任务列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tasks
                WHERE platform_a_synced = 0
                  AND source = 'platform_a'
                  AND sync_retry_count < 3
                ORDER BY updated_at ASC
                LIMIT ?
            """, (limit,))

            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_all_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取所有任务（按创建时间倒序）

        Args:
            limit: 最大返回数量

        Returns:
            任务列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tasks
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))

            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_tasks_by_status(self, status: int, limit: int = 100) -> List[Dict[str, Any]]:
        """
        根据状态获取任务列表

        Args:
            status: 状态码 (参见 TaskStatus 枚举)
            limit: 最大返回数量

        Returns:
            任务列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tasks
                WHERE status = ?
                ORDER BY queued_at ASC, updated_at ASC
                LIMIT ?
            """, (status, limit))

            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_running_tasks(self) -> List[Dict[str, Any]]:
        """
        获取所有运行中的任务（状态为2、6、7）

        Returns:
            任务列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tasks
                WHERE status IN (?, ?, ?)
                ORDER BY start_time ASC
            """, (TaskStatus.GENERATING, TaskStatus.COMPUTING, TaskStatus.POSTPROCESSING))

            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """
        将数据库行转换为字典

        Args:
            row: 数据库行

        Returns:
            字典
        """
        data = dict(row)

        # 解析JSON字段
        if data.get('input_params'):
            data['input_params'] = json.loads(data['input_params'])

        # 转换布尔字段
        data['platform_a_synced'] = bool(data.get('platform_a_synced', 0))
        data['enable_postprocess'] = bool(data.get('enable_postprocess', 0))

        # 添加状态显示名称
        data['status_name'] = TaskStatus.get_display_name(data.get('status', 0))

        return data

    # ==================== 平台交互相关方法 ====================

    def update_heartbeat_counter(self, task_id: str, counter: int) -> bool:
        """
        更新任务的心跳计数器

        Args:
            task_id: 任务ID
            counter: 心跳计数器值 (1-30000循环)

        Returns:
            是否更新成功
        """
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks SET heartbeat_counter = ?, updated_at = ?
                WHERE task_id = ?
            """, (counter, now, task_id))
            return cursor.rowcount > 0

    def get_platform_tasks(self, status: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        获取所有平台任务（platform_api_url不为空的任务）

        Args:
            status: 可选的状态过滤

        Returns:
            平台任务列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if status is not None:
                cursor.execute("""
                    SELECT * FROM tasks
                    WHERE platform_api_url IS NOT NULL
                      AND status = ?
                    ORDER BY created_at DESC
                """, (status,))
            else:
                cursor.execute("""
                    SELECT * FROM tasks
                    WHERE platform_api_url IS NOT NULL
                    ORDER BY created_at DESC
                """)
            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def is_platform_task(self, task_id: str) -> bool:
        """
        判断任务是否为平台任务

        Args:
            task_id: 任务ID

        Returns:
            是否为平台任务
        """
        task = self.get_task(task_id)
        return task is not None and task.get('platform_api_url') is not None

