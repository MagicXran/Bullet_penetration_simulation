#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库操作层 - SQLite数据库封装

遵循第一性原理：一张表解决所有任务状态管理问题
"""

import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
from contextlib import contextmanager


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
                    input_params TEXT NOT NULL,
                    output_file_path TEXT,
                    status INTEGER NOT NULL DEFAULT 0,
                    submission_time TEXT,
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
                ON tasks(platform_a_synced, status)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at
                ON tasks(created_at DESC)
            """)

    def create_task(
        self,
        task_id: str,
        input_params: Dict[str, Any]
    ) -> bool:
        """
        创建新任务

        Args:
            task_id: 任务ID（由平台A传递）
            input_params: 输入参数字典

        Returns:
            是否创建成功
        """
        now = datetime.now().isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO tasks (
                        task_id, input_params, status,
                        created_at, updated_at
                    ) VALUES (?, ?, 0, ?, ?)
                """, (task_id, json.dumps(input_params), now, now))
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
        output_file_path: Optional[str] = None
    ) -> bool:
        """
        更新任务状态

        Args:
            task_id: 任务ID
            status: 状态码 (0-待提交, 1-排队中, 2-运行中, 3-已完成, 4-失败, 5-中止)
            start_time: 开始时间
            end_time: 结束时间
            error_message: 错误信息
            output_file_path: 输出文件路径

        Returns:
            是否更新成功
        """
        now = datetime.now().isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 构建动态更新SQL
            fields = ["status = ?", "updated_at = ?"]
            values = [status, now]

            if start_time is not None:
                fields.append("start_time = ?")
                values.append(start_time)

            if end_time is not None:
                fields.append("end_time = ?")
                values.append(end_time)

            if error_message is not None:
                fields.append("error_message = ?")
                values.append(error_message)

            if output_file_path is not None:
                fields.append("output_file_path = ?")
                values.append(output_file_path)

            # 状态变化时重置同步标志
            fields.append("platform_a_synced = 0")

            values.append(task_id)

            sql = f"UPDATE tasks SET {', '.join(fields)} WHERE task_id = ?"
            cursor.execute(sql, values)

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

        return data
