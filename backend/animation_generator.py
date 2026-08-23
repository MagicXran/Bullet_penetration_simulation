"""
LS-PrePost动画生成引擎

核心功能：
1. 动态生成CFILE脚本
2. 调用LS-PrePost进行渲染
3. 管理异步任务队列

设计原则：
1. KISS原则 - 用f-string而非模板引擎
2. 防御性编程 - 多层错误处理
3. 实用主义 - 简化异步（threading而非Celery）
"""

import subprocess
import os
import json
import threading
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from animation_config import (
    AnimationTask,
    AnimationConfig,
    TaskStatus,
    FRINGE_VARIABLE_MAPPING,
    VIEW_MAPPING
)


class AnimationGenerator:
    """LS-PrePost动画生成器

    职责：
    1. 生成CFILE脚本
    2. 调用LS-PrePost子进程
    3. 管理任务状态

    设计哲学：
    - 数据结构驱动（状态机清晰）
    - 错误分层（配置错误 vs 运行时错误）
    - 零特殊情况（所有路径都经过相同的验证）
    """

    def __init__(self, config_path: str = "backend/config.json"):
        """初始化生成器

        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config = self._load_config()

        # 任务队列（内存字典，简化版异步）
        # Key: task_id, Value: AnimationTask
        self.tasks: Dict[str, AnimationTask] = {}

        # 任务锁（保护并发访问）
        self.task_lock = threading.Lock()

        # 验证LS-PrePost可执行文件
        self._verify_lsprepost()

    def _load_config(self) -> dict:
        """加载配置文件

        Returns:
            配置字典

        Raises:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置文件格式错误
        """
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(
                f"配置文件不存在: {self.config_path}\n"
                f"请创建配置文件，参考 backend/config.json.template"
            )

        with open(self.config_path, 'r', encoding='utf-8-sig') as f:
            config = json.load(f)

        # 验证必需的配置项（不再需要animation_output_dir）
        required_keys = ["lsprepost_executable"]
        missing_keys = [k for k in required_keys if k not in config]
        if missing_keys:
            raise ValueError(f"配置文件缺少必需项: {', '.join(missing_keys)}")

        return config

    def _verify_lsprepost(self):
        """验证LS-PrePost可执行文件是否存在

        Raises:
            FileNotFoundError: LS-PrePost不存在
        """
        lsprepost_path = self.config["lsprepost_executable"]
        if not os.path.exists(lsprepost_path):
            raise FileNotFoundError(
                f"LS-PrePost可执行文件不存在: {lsprepost_path}\n"
                f"请在配置文件中正确设置 lsprepost_executable 路径"
            )

    def _generate_cfile(
        self,
        d3plot_path: str,
        output_path: str,
        config: AnimationConfig
    ) -> str:
        """动态生成CFILE脚本（LS-PrePost 4.8兼容）

        设计决策：使用f-string而非模板引擎
        原因：CFILE结构简单（8-10行命令），不需要额外依赖

        Args:
            d3plot_path: d3plot文件路径
            output_path: 输出GIF路径（含扩展名如.gif）
            config: 动画配置

        Returns:
            CFILE脚本内容（字符串）
        """
        # 获取云图变量映射
        fringe = FRINGE_VARIABLE_MAPPING[config.fringe_variable]
        component = fringe["component"]
        variable = fringe["variable"]

        # 获取视角映射（LS-PrePost 4.8使用小写命令）
        view = VIEW_MAPPING[config.view]

        # 分辨率
        width, height = config.resolution

        # 帧范围
        start_frame = config.start_frame
        end_frame = config.end_frame if config.end_frame else 999  # 默认999，LS-PrePost会自动截断

        # 输出格式（转大写：gif → GIF）
        output_format = config.output_format.upper()

        # 移除输出路径的扩展名（LS-PrePost会自动添加）
        output_path_no_ext = os.path.splitext(output_path)[0]

        # Windows路径：单反斜杠即可（LS-PrePost 4.8格式）
        d3plot_path_escaped = d3plot_path
        output_path_escaped = output_path_no_ext

        # 生成CFILE脚本（基于用户提供的实际可工作格式）
        cfile_content = f"""$# LS-PrePost 4.8 GIF Animation Script
$# 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
$# d3plot: {d3plot_path}

$# 1) 打开 d3plot 文件
openc d3plot "{d3plot_path_escaped}" nodialog

"""
        # 2) 显示所有部件（可选）
        if config.show_all_parts:
            cfile_content += "c 2) 显示所有部件\npall\n\n"

        # 3) 设置视角
        cfile_content += f"""c 3) 设置视角
{view}

"""

        # 4) 自动居中缩放
        cfile_content += "c 4) 自动居中缩放\nac\n\n"

        # 5) 设置 fringe 变量
        cfile_content += f"""c 5) 设置云图变量
fringe {component} {variable}

"""

        # 6) 显示选项
        if config.show_legend or config.show_triad:
            cfile_content += "c 6) 显示选项\n"
            if config.show_legend:
                cfile_content += "showlegend 1\n"
            if config.show_triad:
                cfile_content += "showtriad 1\n"
            cfile_content += "\n"

        # 7) 输出动画
        cfile_content += f"""c 7) 输出动画
movie {output_format} {width}x{height} "{output_path_escaped}" {start_frame} {end_frame}

"""

        # 8) 退出
        cfile_content += "c 8) 退出\nexit\n"

        return cfile_content

    def _run_lsprepost(
        self,
        cfile_path: str,
        timeout: int = 600
    ) -> tuple[bool, str]:
        """调用LS-PrePost执行CFILE脚本

        错误处理层次：
        1. 可执行文件不存在 - 已在_verify_lsprepost()检查
        2. CFILE语法错误 - LS-PrePost返回stderr
        3. d3plot文件损坏 - LS-PrePost返回stderr
        4. 内存不足 - subprocess抛异常
        5. 超时 - subprocess.TimeoutExpired

        Args:
            cfile_path: CFILE脚本路径
            timeout: 超时时间（秒）

        Returns:
            (success: bool, message: str)
        """
        lsprepost_path = self.config["lsprepost_executable"]

        try:
            # 调用LS-PrePost批处理模式（LS-PrePost 4.8兼容）
            # 命令格式: lsprepost.exe c=script.cfile -nographicscls
            # 注意: LS-PrePost 4.8使用 c= 参数（不是 runc=）
            result = subprocess.run(
                [lsprepost_path, f"c={cfile_path}", "-nographicscls"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,  # 不自动抛异常，手动检查returncode
                encoding='utf-8',
                errors='ignore'  # 忽略编码错误（LS-PrePost可能输出非UTF-8字符）
            )

            # 分析输出判断成功还是失败
            stdout = result.stdout
            stderr = result.stderr

            # LS-PrePost的错误通常包含关键字
            error_keywords = ["error", "failed", "cannot", "invalid"]
            has_error = any(
                keyword in stderr.lower() or keyword in stdout.lower()
                for keyword in error_keywords
            )

            if result.returncode != 0 or has_error:
                error_msg = f"LS-PrePost执行失败 (returncode={result.returncode})\n"
                error_msg += f"STDOUT:\n{stdout[:500]}\n"
                error_msg += f"STDERR:\n{stderr[:500]}"
                return False, error_msg

            return True, "动画生成成功"

        except subprocess.TimeoutExpired:
            return False, f"LS-PrePost执行超时（超过{timeout}秒）"

        except Exception as e:
            return False, f"调用LS-PrePost时发生异常: {str(e)}"

    def _generate_task_worker(self, task: AnimationTask):
        """任务执行工作线程

        职责：
        1. 标记任务为processing
        2. 生成CFILE脚本
        3. 调用LS-PrePost
        4. 更新任务状态（completed/failed）

        这个函数在单独的线程中运行，不会阻塞主线程
        """
        try:
            # 标记为处理中
            with self.task_lock:
                task.mark_processing()

            # 输出到d3plot所在目录（最自然的行为）
            d3plot_dir = os.path.dirname(task.d3plot_path)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"animation_{timestamp}_{task.task_id[:8]}.{task.config.output_format}"
            output_path = os.path.join(d3plot_dir, output_filename)

            # 生成CFILE脚本（也放在d3plot目录）
            cfile_filename = f"cfile_{task.task_id[:8]}.cfile"
            cfile_path = os.path.join(d3plot_dir, cfile_filename)

            cfile_content = self._generate_cfile(
                task.d3plot_path,
                output_path,
                task.config
            )

            # 写入CFILE（UTF-8编码）
            with open(cfile_path, 'w', encoding='utf-8') as f:
                f.write(cfile_content)

            print(f"[INFO] CFILE脚本已生成: {cfile_path}")

            # 调用LS-PrePost
            print(f"[INFO] 开始调用LS-PrePost渲染动画...")
            success, message = self._run_lsprepost(cfile_path)

            # 更新任务状态
            with self.task_lock:
                if success:
                    task.mark_completed(output_path)
                    print(f"[SUCCESS] 任务 {task.task_id} 完成: {output_path}")
                else:
                    task.mark_failed(message)
                    print(f"[ERROR] 任务 {task.task_id} 失败: {message}")

        except Exception as e:
            # 捕获所有未预期的异常
            error_msg = f"任务执行时发生未预期的异常: {str(e)}"
            with self.task_lock:
                task.mark_failed(error_msg)
            print(f"[ERROR] 任务 {task.task_id} 异常: {error_msg}")

    def create_task(
        self,
        d3plot_path: str,
        config: Optional[AnimationConfig] = None
    ) -> AnimationTask:
        """创建动画生成任务

        这个函数立即返回，任务在后台线程执行

        Args:
            d3plot_path: d3plot文件的绝对路径
            config: 动画配置（可选，使用默认配置）

        Returns:
            AnimationTask对象

        Raises:
            FileNotFoundError: d3plot文件不存在
        """
        # 验证d3plot文件存在
        if not os.path.exists(d3plot_path):
            raise FileNotFoundError(f"d3plot文件不存在: {d3plot_path}")

        # 创建任务
        if config is None:
            config = AnimationConfig()

        task = AnimationTask(
            d3plot_path=d3plot_path,
            config=config
        )

        # 存储任务
        with self.task_lock:
            self.tasks[task.task_id] = task

        # 启动后台线程处理任务
        worker_thread = threading.Thread(
            target=self._generate_task_worker,
            args=(task,),
            daemon=True  # 守护线程，主程序退出时自动结束
        )
        worker_thread.start()

        print(f"[INFO] 任务 {task.task_id} 已创建并开始处理")

        return task

    def get_task(self, task_id: str) -> Optional[AnimationTask]:
        """获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            AnimationTask对象，如果不存在返回None
        """
        with self.task_lock:
            return self.tasks.get(task_id)

    def get_all_tasks(self) -> list[AnimationTask]:
        """获取所有任务列表

        Returns:
            任务列表（按创建时间倒序）
        """
        with self.task_lock:
            tasks = list(self.tasks.values())

        # 按创建时间倒序排序
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks
