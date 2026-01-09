#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LS-DYNA 计算执行模块 - 可复用的LS-DYNA调用抽象层

提供以下功能：
1. LS-DYNA求解器执行（支持超时和中止）
2. 仿真结果文件监控
3. LS-PrePost后处理（可选）

设计原则：
- 纯粹的执行层，不依赖MQ/MinIO/数据库
- 配置从外部注入，便于复用
- 异常处理完整，支持graceful shutdown

Author: Claude Code
"""

import os
import re
import time
import logging
import subprocess
import threading
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, Tuple, List, Callable

# 配置日志
logger = logging.getLogger(__name__)


class LSDynaStatus(IntEnum):
    """LS-DYNA执行状态码"""
    SUCCESS = 1           # 仿真成功
    FAILED = 0            # 仿真失败
    TIMEOUT = 3           # 超时返回
    ABORTED = -1          # 被中止
    ERROR = -2            # 内部错误


@dataclass
class LSDynaConfig:
    """LS-DYNA配置类"""
    executable_path: str                     # LS-DYNA可执行文件路径
    cpu_count: int = 4                       # CPU核心数
    timeout_minutes: int = 60                # 超时时间（分钟）
    poll_interval: float = 2.0               # 轮询间隔（秒）
    timeout_buffer: float = 1.25             # 超时缓冲系数


@dataclass
class PrePostConfig:
    """LS-PrePost配置类"""
    executable_path: str                     # LS-PrePost可执行文件路径
    output_format: str = "gif"               # 输出格式: gif, avi, mpeg
    resolution: Tuple[int, int] = (1920, 1080)  # 分辨率
    fps: int = 30                            # 帧率
    view: str = "isometric"                  # 视角
    fringe_variable: str = "stress"          # 云图变量


@dataclass
class LSDynaResult:
    """LS-DYNA执行结果"""
    status: LSDynaStatus                     # 执行状态
    work_directory: str                      # 工作目录
    d3plot_path: Optional[str] = None        # d3plot文件路径
    d3hsp_path: Optional[str] = None         # d3hsp文件路径（包含仿真日志）
    messag_path: Optional[str] = None        # messag文件路径
    gif_path: Optional[str] = None           # GIF动画路径（后处理生成）
    stdout_log: Optional[str] = None         # 标准输出日志路径
    stderr_log: Optional[str] = None         # 标准错误日志路径
    error_message: Optional[str] = None      # 错误信息
    elapsed_seconds: float = 0.0             # 执行耗时（秒）


class LSDynaRunner:
    """
    LS-DYNA执行器

    使用方法:
        config = LSDynaConfig(executable_path="path/to/lsdyna.exe")
        runner = LSDynaRunner(config)
        result = runner.run(k_file_path, work_directory, task_id)
    """

    def __init__(self, config: LSDynaConfig, prepost_config: Optional[PrePostConfig] = None):
        """
        初始化LS-DYNA执行器

        Args:
            config: LS-DYNA配置
            prepost_config: LS-PrePost配置（可选，用于后处理）
        """
        self.config = config
        self.prepost_config = prepost_config
        self._process: Optional[subprocess.Popen] = None
        self._current_stop_event: Optional[threading.Event] = None

    def run(
        self,
        k_file_path: str,
        work_directory: str,
        task_id: str,
        stop_event: Optional[threading.Event] = None,
        enable_postprocess: bool = False,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> LSDynaResult:
        """
        执行LS-DYNA仿真

        Args:
            k_file_path: K文件路径
            work_directory: 工作目录
            task_id: 任务ID
            stop_event: 中止事件
            enable_postprocess: 是否启用后处理
            progress_callback: 进度回调函数 callback(phase: str, progress: float)

        Returns:
            LSDynaResult: 执行结果
        """
        self._current_stop_event = stop_event or threading.Event()
        start_time = time.time()

        result = LSDynaResult(
            status=LSDynaStatus.ERROR,
            work_directory=work_directory
        )

        try:
            # 阶段1: 执行LS-DYNA
            if progress_callback:
                progress_callback("lsdyna_starting", 0.0)

            lsdyna_success = self._run_lsdyna(
                k_file_path, work_directory, task_id, result
            )

            if not lsdyna_success:
                result.elapsed_seconds = time.time() - start_time
                return result

            # 阶段2: 监控结果文件
            if progress_callback:
                progress_callback("monitoring", 0.5)

            monitor_status = self._monitor_result(work_directory, task_id)
            result.status = monitor_status

            # 收集结果文件路径
            self._collect_result_files(work_directory, task_id, result)

            # 阶段3: 后处理（可选）
            if enable_postprocess and monitor_status == LSDynaStatus.SUCCESS:
                if progress_callback:
                    progress_callback("postprocess", 0.8)

                if self.prepost_config and result.d3plot_path:
                    gif_path = self._run_postprocess(
                        result.d3plot_path, work_directory, task_id
                    )
                    if gif_path:
                        result.gif_path = gif_path

            if progress_callback:
                progress_callback("completed", 1.0)

        except Exception as e:
            logger.error(f"LS-DYNA执行异常: {e}")
            result.status = LSDynaStatus.ERROR
            result.error_message = str(e)

        finally:
            result.elapsed_seconds = time.time() - start_time
            self._process = None

        return result

    def _run_lsdyna(
        self,
        k_file_path: str,
        work_directory: str,
        task_id: str,
        result: LSDynaResult
    ) -> bool:
        """
        执行LS-DYNA求解器

        Returns:
            bool: 是否成功启动并完成
        """
        try:
            # 验证K文件存在
            if not os.path.isfile(k_file_path):
                result.status = LSDynaStatus.FAILED
                result.error_message = f"K文件不存在: {k_file_path}"
                logger.error(result.error_message)
                return False

            # 验证LS-DYNA可执行文件存在
            if not os.path.isfile(self.config.executable_path):
                result.status = LSDynaStatus.FAILED
                result.error_message = f"LS-DYNA可执行文件不存在: {self.config.executable_path}"
                logger.error(result.error_message)
                return False

            k_filename = os.path.basename(k_file_path)
            # 使用绝对路径，确保 LS-DYNA 能正确找到文件
            k_file_absolute = os.path.abspath(k_file_path)

            # 构建命令
            cmd = [
                self.config.executable_path,
                f"i={k_file_absolute}",
                f"ncpu={self.config.cpu_count}",
                f"jobid={task_id}"
            ]

            logger.info(f"执行LS-DYNA命令: {' '.join(cmd)}")

            # 检查是否已被中止
            if self._current_stop_event and self._current_stop_event.is_set():
                logger.info(f"任务 {task_id} 在启动前被中止")
                result.status = LSDynaStatus.ABORTED
                return False

            # 准备日志文件
            stdout_log = os.path.join(work_directory, f"{task_id}_lsdyna_stdout.log")
            stderr_log = os.path.join(work_directory, f"{task_id}_lsdyna_stderr.log")
            result.stdout_log = stdout_log
            result.stderr_log = stderr_log

            timeout_seconds = self.config.timeout_minutes * 60 * self.config.timeout_buffer
            start_time = time.time()

            with open(stdout_log, 'w', encoding='utf-8') as stdout_file, \
                 open(stderr_log, 'w', encoding='utf-8') as stderr_file:

                # 启动进程
                self._process = subprocess.Popen(
                    cmd,
                    cwd=work_directory,
                    stdout=stdout_file,
                    stderr=stderr_file,
                )

                logger.info(f"LS-DYNA进程已启动: PID={self._process.pid}")

                # 轮询等待完成
                while self._process.poll() is None:
                    # 检查中止信号
                    if self._current_stop_event and self._current_stop_event.is_set():
                        logger.info(f"任务 {task_id} 收到中止信号，终止进程")
                        self._terminate_process()
                        result.status = LSDynaStatus.ABORTED
                        return False

                    # 检查超时
                    if time.time() - start_time > timeout_seconds:
                        logger.warning(f"任务 {task_id} LS-DYNA执行超时")
                        self._terminate_process()
                        result.status = LSDynaStatus.TIMEOUT
                        return False

                    time.sleep(self.config.poll_interval)

                # 检查返回码
                if self._process.returncode == 0:
                    logger.info(f"LS-DYNA程序执行完成: {task_id}")
                    return True
                else:
                    logger.warning(f"LS-DYNA返回非零退出码: {self._process.returncode}")
                    result.status = LSDynaStatus.FAILED
                    result.error_message = f"LS-DYNA退出码: {self._process.returncode}"
                    return False

        except Exception as e:
            logger.error(f"运行LS-DYNA时出错: {e}")
            result.status = LSDynaStatus.ERROR
            result.error_message = str(e)
            return False

    def _terminate_process(self):
        """终止当前进程"""
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                try:
                    self._process.wait(timeout=10)
                    logger.info("LS-DYNA进程已优雅终止")
                except subprocess.TimeoutExpired:
                    logger.warning("LS-DYNA进程未响应terminate，强制kill")
                    self._process.kill()
                    self._process.wait()
            except Exception as e:
                logger.error(f"终止进程时出错: {e}")

    def _monitor_result(self, work_directory: str, task_id: str) -> LSDynaStatus:
        """
        监控LS-DYNA结果文件

        Returns:
            LSDynaStatus: 监控结果状态
        """
        try:
            timeout_seconds = self.config.timeout_minutes * 60 * self.config.timeout_buffer
            start_time = time.time()

            while True:
                # 检查中止
                if self._current_stop_event and self._current_stop_event.is_set():
                    logger.info("监控被中止")
                    return LSDynaStatus.ABORTED

                # 检查超时
                if time.time() - start_time > timeout_seconds:
                    logger.warning("结果监控超时")
                    return LSDynaStatus.TIMEOUT

                # 检查d3plot文件
                d3plot_exists = self._check_d3plot_exists(work_directory)

                if d3plot_exists:
                    # 检查messag文件中的完成标志
                    messag_files = self._find_messag_files(work_directory)
                    if messag_files:
                        for messag_file in messag_files:
                            try:
                                with open(messag_file, 'r', encoding='utf-8', errors='ignore') as f:
                                    content = f.read()

                                # "Elapsed time" 是LS-DYNA完成的标志
                                if "Elapsed time" in content:
                                    logger.info(f"LS-DYNA仿真成功: 任务完成")
                                    return LSDynaStatus.SUCCESS

                                # 检查错误标志
                                if "E r r o r" in content or re.search(r'\bError\b', content, re.IGNORECASE):
                                    logger.warning("检测到LS-DYNA错误")
                                    return LSDynaStatus.FAILED

                            except Exception as e:
                                logger.warning(f"读取messag文件时出错: {e}")

                time.sleep(self.config.poll_interval)

        except Exception as e:
            logger.error(f"监控结果时出错: {e}")
            return LSDynaStatus.ERROR

    def _check_d3plot_exists(self, work_directory: str) -> bool:
        """检查d3plot文件是否存在"""
        try:
            for f in os.listdir(work_directory):
                if f == 'd3plot' or f.endswith('.d3plot') or f.startswith('d3plot'):
                    file_path = os.path.join(work_directory, f)
                    if os.path.isfile(file_path):
                        return True
        except Exception:
            pass
        return False

    def _find_messag_files(self, work_directory: str) -> List[str]:
        """查找messag文件"""
        messag_files = []
        try:
            for f in os.listdir(work_directory):
                # messag命名规则: messag, messag0000, {jobid}.messag
                if f == 'messag' or f.startswith('messag') or f.endswith('.messag'):
                    messag_files.append(os.path.join(work_directory, f))
        except Exception:
            pass
        return messag_files

    def _collect_result_files(self, work_directory: str, task_id: str, result: LSDynaResult):
        """收集结果文件路径"""
        try:
            for f in os.listdir(work_directory):
                file_path = os.path.join(work_directory, f)

                # d3plot文件
                if f == 'd3plot' or f.endswith('.d3plot') or f.startswith('d3plot'):
                    if os.path.isfile(file_path) and not result.d3plot_path:
                        result.d3plot_path = file_path

                # d3hsp文件（仿真日志）
                if f == 'd3hsp' or f.endswith('.d3hsp'):
                    if os.path.isfile(file_path):
                        result.d3hsp_path = file_path

                # messag文件
                if f == 'messag' or f.startswith('messag') or f.endswith('.messag'):
                    if os.path.isfile(file_path) and not result.messag_path:
                        result.messag_path = file_path

        except Exception as e:
            logger.warning(f"收集结果文件时出错: {e}")

    def _run_postprocess(
        self,
        d3plot_path: str,
        work_directory: str,
        task_id: str
    ) -> Optional[str]:
        """
        执行LS-PrePost后处理生成动画

        直接使用LS-PrePost生成目标格式（GIF/AVI/MPEG）
        LS-PrePost 4.8原生支持这些格式，无需中间转换

        Returns:
            Optional[str]: 动画文件路径，失败返回None
        """
        if not self.prepost_config:
            return None

        try:
            # 直接使用配置的输出格式（LS-PrePost 4.8支持gif/avi/mpeg）
            target_format = self.prepost_config.output_format.lower()
            d3plot_absolute = os.path.abspath(d3plot_path)

            # 输出文件路径（LS-PrePost会自动添加扩展名）
            output_filename = f"{task_id}.{target_format}"
            output_path = os.path.abspath(os.path.join(work_directory, output_filename))
            cfile_path = os.path.abspath(os.path.join(work_directory, f"{task_id}_animation.cfile"))

            # 不再使用force_format，尊重配置中的格式
            cfile_content = self._generate_cfile(d3plot_absolute, output_path)

            with open(cfile_path, 'w', encoding='utf-8') as f:
                f.write(cfile_content)

            # 执行LS-PrePost（批处理模式，-nographicscls 确保无GUI自动关闭）
            cmd = [
                self.prepost_config.executable_path,
                "c=" + cfile_path,
                "-nographicscls"
            ]

            logger.info(f"执行LS-PrePost命令: {' '.join(cmd)}")
            logger.info(f"目标格式: {target_format.upper()}, 输出路径: {output_path}")

            process = subprocess.run(
                cmd,
                cwd=work_directory,
                capture_output=True,
                text=True,
                timeout=600  # 10分钟超时
            )

            # 检查文件是否生成（即使returncode非0，文件可能已生成）
            if os.path.isfile(output_path):
                file_size = os.path.getsize(output_path)
                logger.info(f"后处理完成: {output_path} ({file_size} bytes)")
                return output_path
            else:
                logger.warning(f"LS-PrePost未生成文件，returncode={process.returncode}")
                if process.stderr:
                    logger.warning(f"stderr: {process.stderr[:500]}")
                return None

        except subprocess.TimeoutExpired:
            logger.error("LS-PrePost执行超时")
            return None
        except Exception as e:
            logger.error(f"后处理时出错: {e}")
            return None

    def _generate_cfile(self, d3plot_path: str, output_path: str) -> str:
        """
        生成LS-PrePost cfile脚本（LS-PrePost 4.8兼容格式）

        Args:
            d3plot_path: d3plot文件路径
            output_path: 输出文件路径（含扩展名，方法内部会处理）
        """
        cfg = self.prepost_config

        # 视角映射
        view_map = {
            "isometric": "iso1",
            "front": "front",
            "back": "back",
            "top": "top",
            "bottom": "bottom",
            "left": "left",
            "right": "right"
        }
        view_cmd = view_map.get(cfg.view, "iso1")

        # 云图变量映射
        fringe_map = {
            "stress": "Stress",
            "strain": "Strain",
            "displacement": "Displacement",
            "velocity": "Velocity",
            "acceleration": "Acceleration",
            "plastic_strain": "Plastic strain"
        }
        fringe_var = fringe_map.get(cfg.fringe_variable, "Stress")

        # 输出格式（大写，LS-PrePost 4.8要求）
        format_ext = cfg.output_format.upper()

        # 输出路径不含扩展名（LS-PrePost会自动添加）
        output_path_no_ext = os.path.splitext(output_path)[0]

        cfile = f"""$# LS-PrePost 4.8 Animation Script
openc d3plot "{d3plot_path}" nodialog
pall
view {view_cmd}
ac
fringe 1
fcomp 1 "{fringe_var}"
range auto
showlegend 1
showtriad 1
movie {format_ext} {cfg.resolution[0]}x{cfg.resolution[1]} "{output_path_no_ext}" 1 999
exit
"""
        return cfile

    def abort(self):
        """中止当前执行"""
        if self._current_stop_event:
            self._current_stop_event.set()
        self._terminate_process()


def create_runner_from_config(config_dict: dict) -> LSDynaRunner:
    """
    从配置字典创建LSDynaRunner实例

    Args:
        config_dict: 配置字典，应包含:
            - lsdyna_executable: LS-DYNA可执行文件路径
            - lsdyna_cpu_count: CPU核心数（可选）
            - lsdyna_timeout_minutes: 超时时间（可选）
            - lsprepost_executable: LS-PrePost可执行文件路径（可选）
            - animation_output_format: 动画格式（可选）
            - default_resolution: 分辨率（可选）
            - default_fps: 帧率（可选）

    Returns:
        LSDynaRunner: 配置好的执行器实例
    """
    lsdyna_config = LSDynaConfig(
        executable_path=config_dict.get("lsdyna_executable", ""),
        cpu_count=config_dict.get("lsdyna_cpu_count", 4),
        timeout_minutes=config_dict.get("lsdyna_timeout_minutes", 60)
    )

    prepost_config = None
    prepost_path = config_dict.get("lsprepost_executable")
    if prepost_path and os.path.isfile(prepost_path):
        resolution = config_dict.get("default_resolution", [1920, 1080])
        prepost_config = PrePostConfig(
            executable_path=prepost_path,
            output_format=config_dict.get("animation_output_format", "gif"),
            resolution=tuple(resolution) if isinstance(resolution, list) else resolution,
            fps=config_dict.get("default_fps", 30),
            view=config_dict.get("default_view", "isometric"),
            fringe_variable=config_dict.get("default_fringe_variable", "stress")
        )

    return LSDynaRunner(lsdyna_config, prepost_config)


# 便捷函数：直接执行LS-DYNA
def run_lsdyna_simple(
    executable_path: str,
    k_file_path: str,
    work_directory: str,
    task_id: str,
    cpu_count: int = 4,
    timeout_minutes: int = 60,
    stop_event: Optional[threading.Event] = None
) -> LSDynaResult:
    """
    简化的LS-DYNA执行函数

    Args:
        executable_path: LS-DYNA可执行文件路径
        k_file_path: K文件路径
        work_directory: 工作目录
        task_id: 任务ID
        cpu_count: CPU核心数
        timeout_minutes: 超时时间（分钟）
        stop_event: 中止事件

    Returns:
        LSDynaResult: 执行结果
    """
    config = LSDynaConfig(
        executable_path=executable_path,
        cpu_count=cpu_count,
        timeout_minutes=timeout_minutes
    )
    runner = LSDynaRunner(config)
    return runner.run(k_file_path, work_directory, task_id, stop_event)


if __name__ == "__main__":
    # 测试示例
    import sys

    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("LSDynaRunner 模块测试")
    print("=" * 60)

    # 显示模块接口
    print("\n可用类:")
    print("  - LSDynaConfig: LS-DYNA配置")
    print("  - PrePostConfig: LS-PrePost配置")
    print("  - LSDynaResult: 执行结果")
    print("  - LSDynaRunner: 执行器")

    print("\n便捷函数:")
    print("  - create_runner_from_config(config_dict): 从配置字典创建执行器")
    print("  - run_lsdyna_simple(...): 简化执行函数")

    print("\n使用示例:")
    print("""
    from lsdyna_runner import LSDynaConfig, LSDynaRunner, LSDynaStatus

    config = LSDynaConfig(
        executable_path="C:/Program Files/LSTC/LS-DYNA/ls-dyna_smp_s_R13.exe",
        cpu_count=4,
        timeout_minutes=60
    )

    runner = LSDynaRunner(config)
    result = runner.run(
        k_file_path="D:/sim/test.k",
        work_directory="D:/sim/work",
        task_id="task_001"
    )

    if result.status == LSDynaStatus.SUCCESS:
        print(f"仿真成功! d3plot: {result.d3plot_path}")
    else:
        print(f"仿真失败: {result.error_message}")
    """)
