#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
平台A同步客户端

负责与平台A的HTTP通信，发送任务状态更新
遵循实用主义原则：简单的重试机制，不搞复杂的消息队列
"""

import requests
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import logging


# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PlatformSyncClient:
    """平台A同步客户端"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化同步客户端

        Args:
            config: 配置字典，包含：
                - base_url: 平台A的基础URL
                - task_insert_endpoint: 任务插入接口路径
                - task_update_endpoint: 任务更新接口路径
                - timeout: 请求超时时间（秒）
        """
        self.base_url = config.get('base_url', '').rstrip('/')
        self.task_insert_endpoint = config.get(
            'task_insert_endpoint',
            '/simulApi/web-app/task-insert/'
        )
        self.task_update_endpoint = config.get(
            'task_update_endpoint',
            '/simulApi/web-app/task-update/'
        )
        self.timeout = config.get('timeout', 10)

        if not self.base_url:
            raise ValueError("平台A的base_url配置不能为空")


    # [已删除] insert_task() 方法 - 死代码，触发条件几乎不可能满足

    def update_task(
        self,
        task_id: str,
        task_status: int,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        向平台A更新任务状态

        Args:
            task_id: 任务ID
            task_status: 任务状态
            start_time: 开始时间（ISO格式字符串）
            end_time: 结束时间（ISO格式字符串）
            error_message: 错误信息

        Returns:
            (是否成功, 错误信息)
        """
        url = f"{self.base_url}{self.task_update_endpoint}"

        payload = {
            "task_id": task_id,
            "start_time": start_time or "",
            "end_time": end_time or "",
            "error_message": error_message or "",
            "task_status": task_status
        }

        try:
            logger.info(f"向平台A更新任务状态: {task_id}, status={task_status}, URL: {url}")
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout,
                headers={'Content-Type': 'application/json'}
            )

            # 检查响应
            if response.status_code == 200:
                result = response.json()
                if result.get('code') == 0:
                    logger.info(f"任务 {task_id} 状态更新成功: {result.get('msg')}")
                    return True, None
                else:
                    error_msg = f"平台A返回错误: code={result.get('code')}, msg={result.get('msg')}"
                    logger.error(error_msg)
                    return False, error_msg
            else:
                error_msg = f"HTTP错误: {response.status_code}, {response.text}"
                logger.error(error_msg)
                return False, error_msg

        except requests.exceptions.Timeout:
            error_msg = f"请求超时（{self.timeout}秒）"
            logger.error(f"任务 {task_id} 更新失败: {error_msg}")
            return False, error_msg

        except requests.exceptions.RequestException as e:
            error_msg = f"网络请求失败: {str(e)}"
            logger.error(f"任务 {task_id} 更新失败: {error_msg}")
            return False, error_msg

        except Exception as e:
            error_msg = f"未知错误: {str(e)}"
            logger.error(f"任务 {task_id} 更新失败: {error_msg}")
            return False, error_msg

    def sync_task_status(self, task: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        根据任务当前状态同步到平台A

        [注意] 此方法为旧轮询模式遗留，新版本使用事件驱动
        统一调用update_task

        Args:
            task: 任务字典（来自数据库）

        Returns:
            (是否成功, 错误信息)
        """
        task_id = task['task_id']
        status = task['status']
        start_time = task.get('start_time')
        end_time = task.get('end_time')
        error_message = task.get('error_message')

        # 统一调用update（insert_task已删除）
        return self.update_task(
            task_id,
            status,
            start_time,
            end_time,
            error_message
        )
