#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
任务管理器 - 业务逻辑层

封装任务的创建、查询、状态更新等核心业务逻辑
遵循单一职责原则：只管理任务，不管HTTP通信
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

from database import Database


class TaskManager:
    """任务管理器"""

    # 任务状态常量
    STATUS_PENDING = 0      # 待提交
    STATUS_QUEUED = 1       # 排队中
    STATUS_RUNNING = 2      # 运行中
    STATUS_COMPLETED = 3    # 已完成
    STATUS_FAILED = 4       # 失败
    STATUS_ABORTED = 5      # 中止

    STATUS_NAMES = {
        0: "待提交",
        1: "排队中",
        2: "运行中",
        3: "已完成",
        4: "失败",
        5: "中止"
    }

    def __init__(self, db_path: str = "backend/tasks.db"):
        """
        初始化任务管理器

        Args:
            db_path: 数据库文件路径
        """
        self.db = Database(db_path)

    def create_or_get_task(
        self,
        task_id: str,
        input_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        创建任务或获取已存在的任务

        这是核心方法：平台B收到task_id后调用此方法
        - 如果task_id已存在：返回已有任务
        - 如果task_id不存在：创建新任务（input_params为必需）

        Args:
            task_id: 任务ID（由平台A传递）
            input_params: 输入参数（新建任务时必需）

        Returns:
            任务字典

        Raises:
            ValueError: task_id不存在且input_params为空时
        """
        # 先尝试获取已存在的任务
        existing_task = self.db.get_task(task_id)
        if existing_task:
            return existing_task

        # 任务不存在，需要创建
        if input_params is None:
            raise ValueError(
                f"任务 {task_id} 不存在，且未提供input_params参数，无法创建新任务"
            )

        # 创建新任务
        success = self.db.create_task(task_id, input_params)
        if not success:
            # 理论上不会到这里（因为前面已经查过），但保险起见再查一次
            return self.db.get_task(task_id)

        # 返回新创建的任务
        return self.db.get_task(task_id)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务详情

        Args:
            task_id: 任务ID

        Returns:
            任务字典或None
        """
        return self.db.get_task(task_id)

    def submit_task(
        self,
        task_id: str,
        input_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        提交任务（用户点击"提交计算"按钮时调用）

        Args:
            task_id: 任务ID
            input_params: 输入参数

        Returns:
            更新后的任务字典
        """
        # 确保任务存在
        task = self.create_or_get_task(task_id, input_params)

        # 记录提交时间
        submission_time = datetime.now().isoformat()
        self.db.update_task_submission_time(task_id, submission_time)

        # 更新状态为待提交
        self.db.update_task_status(task_id, self.STATUS_PENDING)

        return self.db.get_task(task_id)

    def start_task(self, task_id: str) -> bool:
        """
        开始执行任务

        Args:
            task_id: 任务ID

        Returns:
            是否更新成功
        """
        start_time = datetime.now().isoformat()
        return self.db.update_task_status(
            task_id,
            self.STATUS_RUNNING,
            start_time=start_time
        )

    def complete_task(
        self,
        task_id: str,
        output_file_path: str
    ) -> bool:
        """
        标记任务完成

        Args:
            task_id: 任务ID
            output_file_path: 输出文件路径

        Returns:
            是否更新成功
        """
        end_time = datetime.now().isoformat()
        return self.db.update_task_status(
            task_id,
            self.STATUS_COMPLETED,
            end_time=end_time,
            output_file_path=output_file_path
        )

    def fail_task(
        self,
        task_id: str,
        error_message: str
    ) -> bool:
        """
        标记任务失败

        Args:
            task_id: 任务ID
            error_message: 错误信息

        Returns:
            是否更新成功
        """
        end_time = datetime.now().isoformat()
        return self.db.update_task_status(
            task_id,
            self.STATUS_FAILED,
            end_time=end_time,
            error_message=error_message
        )

    def abort_task(self, task_id: str) -> bool:
        """
        中止任务

        Args:
            task_id: 任务ID

        Returns:
            是否更新成功
        """
        end_time = datetime.now().isoformat()
        return self.db.update_task_status(
            task_id,
            self.STATUS_ABORTED,
            end_time=end_time
        )

    def get_all_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取所有任务

        Args:
            limit: 最大返回数量

        Returns:
            任务列表
        """
        return self.db.get_all_tasks(limit)

    def get_unsynced_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取未同步到平台A的任务

        Args:
            limit: 最大返回数量

        Returns:
            任务列表
        """
        return self.db.get_unsynced_tasks(limit)

    def mark_synced(self, task_id: str) -> bool:
        """
        标记任务已同步

        Args:
            task_id: 任务ID

        Returns:
            是否标记成功
        """
        return self.db.mark_as_synced(task_id)

    def increment_sync_retry(self, task_id: str) -> int:
        """
        增加同步重试次数

        Args:
            task_id: 任务ID

        Returns:
            当前重试次数
        """
        return self.db.increment_sync_retry(task_id)

    @staticmethod
    def validate_task_id(task_id: str) -> bool:
        """
        验证task_id格式

        简单验证：非空且长度合理
        可根据平台A的实际格式扩展（如UUID格式）

        Args:
            task_id: 任务ID

        Returns:
            是否有效
        """
        if not task_id or not isinstance(task_id, str):
            return False

        # 长度验证（假设task_id在8-128字符之间）
        if len(task_id) < 8 or len(task_id) > 128:
            return False

        # 字符验证（只允许字母、数字、下划线、连字符）
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', task_id):
            return False

        return True

    @staticmethod
    def get_status_name(status: int) -> str:
        """
        获取状态名称

        Args:
            status: 状态码

        Returns:
            状态名称
        """
        return TaskManager.STATUS_NAMES.get(status, "未知状态")
