#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
平台通知器 - 事件驱动的状态推送

负责与外部平台通信：
1. 注册任务（status=0）
2. 发送心跳（每30秒）
3. 通知完成/失败（status=2/3）

基于 app_platform_interface.md v1.5.0 设计
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class PlatformNotifier:
    """
    平台通知器

    事件驱动模式：状态变化时立即推送，而非定时轮询
    """

    # 状态码映射：内部8状态 → 对外4状态
    STATUS_MAPPING = {
        0: 0,  # PENDING → 任务就绪
        1: 0,  # QUEUED → 任务就绪
        2: 1,  # GENERATING → 执行中
        6: 1,  # COMPUTING → 执行中
        7: 1,  # POSTPROCESSING → 执行中
        3: 2,  # COMPLETED → 已完成
        4: 3,  # FAILED → 已失败
        5: 3,  # ABORTED → 已失败
    }

    # 状态消息
    STATUS_MESSAGES = {
        0: "任务就绪",
        1: "执行中",
        2: "任务完成",
        3: "任务失败",
    }

    def __init__(self, config: Dict[str, Any]):
        """
        初始化平台通知器

        Args:
            config: 配置字典，包含：
                - platform_api_url: 平台API地址
                - callback_base_url: App回调基础地址
                - callback_endpoint: 回调端点路径
                - request_timeout_seconds: 请求超时时间
        """
        self.platform_api_url = config.get('platform_api_url', '').rstrip('/')
        self.callback_base_url = config.get('callback_base_url', '').rstrip('/')
        self.callback_endpoint = config.get('callback_endpoint', '/api/platform/callback')
        self.timeout = config.get('request_timeout_seconds', 10)

        self.enabled = config.get('enabled', False) and bool(self.platform_api_url)

        if self.enabled:
            logger.info(f"平台通知器已启用: {self.platform_api_url}")
        else:
            logger.info("平台通知器未启用（disabled或platform_api_url为空）")

    @classmethod
    def map_internal_to_external(cls, internal_status: int) -> int:
        """
        内部状态 → 对外状态映射

        Args:
            internal_status: 内部状态码 (0-7)

        Returns:
            对外状态码 (0-3)
        """
        return cls.STATUS_MAPPING.get(internal_status, 0)

    @classmethod
    def get_status_message(cls, external_status: int) -> str:
        """获取状态消息"""
        return cls.STATUS_MESSAGES.get(external_status, "未知状态")

    def get_callback_url(self) -> str:
        """构建完整的回调URL"""
        return f"{self.callback_base_url}{self.callback_endpoint}"

    def register_task(
        self,
        task_id: str,
        status: int = 0
    ) -> Tuple[bool, Optional[str]]:
        """
        向平台注册任务（status=0 任务就绪）

        Args:
            task_id: 任务ID
            status: 任务状态（默认0）

        Returns:
            (是否成功, 错误信息)
        """
        if not self.enabled:
            logger.debug("平台通知器未启用，跳过注册")
            return True, None

        url = f"{self.platform_api_url}/api/tasks/{task_id}"
        external_status = self.map_internal_to_external(status)

        payload = {
            "datas": {
                "task_id": task_id,
                "status": external_status,
                "message": self.get_status_message(external_status)
            },
            "callback_url": self.get_callback_url()
        }

        return self._post(url, payload, f"注册任务 {task_id}")

    def send_heartbeat(
        self,
        task_id: str,
        counter: int,
        internal_status: int
    ) -> Tuple[bool, Optional[str]]:
        """
        发送心跳

        Args:
            task_id: 任务ID
            counter: 心跳计数器 (1-30000)
            internal_status: 内部状态码

        Returns:
            (是否成功, 错误信息)
        """
        if not self.enabled:
            return True, None

        url = f"{self.platform_api_url}/api/tasks/{task_id}/heartbeat"
        external_status = self.map_internal_to_external(internal_status)

        payload = {
            "datas": {
                "counter": counter,
                "task_id": task_id,
                "status": external_status,
                "message": self.get_status_message(external_status)
            }
        }

        return self._post(url, payload, f"心跳 {task_id} (counter={counter})")

    def notify_completion(
        self,
        task_id: str,
        success: bool,
        message: str = ""
    ) -> Tuple[bool, Optional[str]]:
        """
        通知任务完成或失败

        Args:
            task_id: 任务ID
            success: 是否成功
            message: 附加消息

        Returns:
            (是否成功, 错误信息)
        """
        if not self.enabled:
            return True, None

        url = f"{self.platform_api_url}/api/tasks/{task_id}"
        external_status = 2 if success else 3

        payload = {
            "datas": {
                "task_id": task_id,
                "status": external_status,
                "message": message or self.get_status_message(external_status)
            }
        }

        return self._post(url, payload, f"完成通知 {task_id} (success={success})")

    def _post(
        self,
        url: str,
        payload: Dict[str, Any],
        operation: str
    ) -> Tuple[bool, Optional[str]]:
        """
        发送POST请求

        Args:
            url: 请求URL
            payload: 请求体
            operation: 操作描述（用于日志）

        Returns:
            (是否成功, 错误信息)
        """
        try:
            logger.debug(f"[{operation}] POST {url}")
            logger.debug(f"[{operation}] Payload: {json.dumps(payload, ensure_ascii=False)}")

            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout,
                headers={'Content-Type': 'application/json'}
            )

            # 检查响应
            if response.status_code == 200:
                result = response.json()
                code = result.get('code', 0)

                if code == 2000:
                    logger.info(f"[{operation}] 成功: {result.get('message', 'OK')}")
                    return True, None
                else:
                    error_msg = f"平台返回错误: code={code}, message={result.get('message')}"
                    logger.warning(f"[{operation}] {error_msg}")
                    return False, error_msg
            else:
                error_msg = f"HTTP错误: {response.status_code}, {response.text[:200]}"
                logger.error(f"[{operation}] {error_msg}")
                return False, error_msg

        except requests.exceptions.Timeout:
            error_msg = f"请求超时（{self.timeout}秒）"
            logger.error(f"[{operation}] {error_msg}")
            return False, error_msg

        except requests.exceptions.RequestException as e:
            error_msg = f"网络请求失败: {str(e)}"
            logger.error(f"[{operation}] {error_msg}")
            return False, error_msg

        except Exception as e:
            error_msg = f"未知错误: {str(e)}"
            logger.error(f"[{operation}] {error_msg}", exc_info=True)
            return False, error_msg
