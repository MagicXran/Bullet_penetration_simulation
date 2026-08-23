 #!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ANSYS子系统服务脚本，负责接收MQ消息、下载文件、处理文件内容、
执行ANSYS程序、监控和上传结果文件。
支持异步处理和通过stop_flag中止指定task_id的任务。
支持LS-DYNA(.k文件)、Fluent(.cas/.dat文件)、Mechanical APDL(.inp/.mac/.cdb文件)。
"""

import os
import sys
import time
import signal
import tempfile
import shutil
import subprocess
import traceback
import json
import threading
import glob
from typing import List, Dict, Any, Optional, Tuple
import logging
from concurrent.futures import ThreadPoolExecutor


# 添加父目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入相关模块
try:
    # from nangang_mq import MessageQueueSDK, SimulationType, TaskStatus
    # from minio_service import MinioService
    # from files_monitor import monitor_ansys_result_files
    # from common_logger import create_logger
    from nangang_mq import MessageQueueSDK, SimulationType, TaskStatus,MinioService,monitor_ansys_result_files,create_logger
except ImportError as e:
    print(f"导入模块失败: {e}")
    raise

# 设置日志
logger = create_logger('ansys_services')

def load_config(config_file):
    """加载配置文件
    
    参数:
        config_file: 配置文件路径，默认为同级目录下的sub-services.json
        
    返回:
        配置字典
    """
    config_path = config_file
    try:
        with open(config_path, 'r', encoding='utf-8-sig') as f:
            config = json.load(f)
        logger.info(f"成功加载配置文件: {config_path}")
        return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        raise 

class AnsysService:
    """ANSYS服务类，处理ANSYS仿真计算任务"""
    
    def __init__(self, config_path):
        """
        初始化ANSYS服务
        :param config_path: 配置文件路径
        """
        # 从配置文件中加载配置
        config = load_config(config_path)

        # RabbitMQ配置
        mq_config = config.get("rabbitmq", {})
        self.mq_sdk = MessageQueueSDK(
            host=mq_config.get("host"),
            port=mq_config.get("port"),
            username=mq_config.get("username"),
            password=mq_config.get("password"),
        )
        
        # MinIO配置
        minio_config = config.get("minio", {})
        self.minio_sdk = MinioService(
            endpoint=minio_config.get("endpoint"),
            access_key=minio_config.get("access_key"),
            secret_key=minio_config.get("secret_key"),
            secure=minio_config.get("secure", False)
        )
        
        # ANSYS程序路径配置
        self.ansys_lsdyna_path = config.get("ansys_lsdyna_path")
        self.ansys_fluent_path = config.get("ansys_fluent_path")
        self.ansys_exe_path = config.get("ansys_exe_path")
        self.plate_url = config.get("plate_url")

        # 存储活跃任务状态，用于stop_flag处理
        self.active_tasks = {}
        self.active_tasks_lock = threading.Lock()
        
        self.running = True
        
        # 线程池执行器，用于异步处理任务
        self.executor = ThreadPoolExecutor(max_workers=5)
        
        # 注册信号处理器以优雅地处理CTRL+C
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        logger.info("ANSYS服务初始化完成")
    
    def signal_handler(self, sig, frame):
        """处理信号（如CTRL+C）以优雅地退出"""
        logger.info(f"接收到信号 {sig}，准备退出程序...")
        self.running = False

        # 停止所有活跃任务并终止进程
        with self.active_tasks_lock:
            for task_id, task_info in self.active_tasks.items():
                logger.info(f"正在停止任务 {task_id}")
                task_info['stop_event'].set()

                # 立即终止进程
                process = task_info.get('process')
                if process and process.poll() is None:
                    logger.info(f"终止任务 {task_id} 的进程 PID={process.pid}")
                    try:
                        process.terminate()
                    except Exception as e:
                        logger.error(f"终止进程时出错: {e}")

        # 等待进程优雅退出
        time.sleep(2)

        # 强制杀死仍在运行的进程
        with self.active_tasks_lock:
            for task_id, task_info in self.active_tasks.items():
                process = task_info.get('process')
                if process and process.poll() is None:
                    logger.warning(f"强制杀死任务 {task_id} 的进程")
                    try:
                        process.kill()
                    except Exception:
                        pass

        # 关闭线程池
        self.executor.shutdown(wait=True, cancel_futures=True)

        # 清理资源
        self.mq_sdk.close()
        logger.info("已清理资源，程序退出")
        sys.exit(0)
    
    def add_active_task(self, task_id: str) -> threading.Event:
        """添加活跃任务并返回stop_event

        返回:
            stop_event: 中止事件，设置后任务应尽快退出
        """
        stop_event = threading.Event()
        result_sent = threading.Event()  # 新增：防止重复发送结果
        with self.active_tasks_lock:
            self.active_tasks[task_id] = {
                'stop_event': stop_event,
                'result_sent': result_sent,      # 新增：防止重复发送结果
                'process': None,                  # 新增：保存Popen对象引用
                'phase': 'pending',               # 新增：'pending'|'downloading'|'running'|'monitoring'|'uploading'
                'start_time': time.time()
            }
        logger.info(f"添加活跃任务: {task_id}")
        return stop_event
    
    def remove_active_task(self, task_id: str):
        """移除活跃任务"""
        with self.active_tasks_lock:
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]
                logger.info(f"移除活跃任务: {task_id}")
    
    def handle_stop_task(self, task_id: str) -> bool:
        """处理任务中止请求

        返回:
            bool: True表示找到并设置了中止标志，False表示任务不存在
        """
        with self.active_tasks_lock:
            if task_id in self.active_tasks:
                task_info = self.active_tasks[task_id]
                logger.info(f"设置任务 {task_id} 中止标志，当前阶段: {task_info.get('phase', 'unknown')}")
                task_info['stop_event'].set()

                # 如果有正在运行的进程，立即终止
                process = task_info.get('process')
                if process and process.poll() is None:
                    logger.info(f"立即终止任务 {task_id} 的进程 PID={process.pid}")
                    try:
                        process.terminate()
                    except Exception as e:
                        logger.error(f"终止进程时出错: {e}")

                return True
            else:
                logger.warning(f"未找到活跃任务 {task_id}")
                return False
    
    def determine_file_type(self, file_path: str) -> int:
        """
        根据文件扩展名确定文件类型
        
        参数:
            file_path: 文件路径
            
        返回:
            int: 文件类型编号 (0:.k文件, 1:fluent文件, 2:Mechanical APDL文件, -1:未知类型)
        """
        file_path_lower = file_path.lower()
        _, ext = os.path.splitext(file_path_lower)
        
        if ext == '.k':
            return 0  # LS-DYNA
        elif ext in ['.cas', '.dat'] or file_path_lower.endswith('.cas.h5') or file_path_lower.endswith('.dat.h5'):
            return 1  # Fluent
        elif ext in ['.inp', '.mac', '.cdb']:
            return 2  # Mechanical APDL
        else:
            return -1  # 未知类型
    
    def create_fluent_journal_file(self, work_directory: str, task_id: str, cas_file: str, dat_file: Optional[str], iterations: int) -> str:
        """
        创建Fluent的.jou文件
        
        参数:
            work_directory: 工作目录
            task_id: 任务ID
            cas_file: .cas文件路径
            dat_file: .dat文件路径（可选）
            iterations: 迭代次数
            
        返回:
            str: .jou文件路径
        """
        jou_file_path = os.path.join(work_directory, f"{task_id}.jou")
        
        try:
            with open(jou_file_path, 'w', encoding='utf-8') as f:
                f.write(f'/file/read-case "{cas_file}";\n\n')
                
                if dat_file and os.path.exists(dat_file):
                    f.write(f'/file/read-data "{dat_file}";\n\n')
                
                f.write('/solve/initialize/initialize-flow              ;\n\n')
                f.write(f'/solve/iterate {iterations}                             ;\n\n')
                f.write(f'/file/write-data "{task_id}.dat.h5"                ;\n\n')
                f.write('/exit yes\n')
            
            logger.info(f"成功创建Fluent journal文件: {jou_file_path}")
            return jou_file_path
            
        except Exception as e:
            logger.error(f"创建Fluent journal文件失败: {e}")
            raise
    
    def run_ansys_lsdyna(self, k_file_path: str, work_directory: str, task_id: str,
                        cpu_count: int, timeout_minutes: int, stop_event: threading.Event) -> bool:
        """
        运行LS-DYNA程序（支持真正的中止）

        参数:
            k_file_path: K文件路径
            work_directory: 工作目录
            task_id: 任务ID
            cpu_count: CPU核心数
            timeout_minutes: 超时时间(分钟)
            stop_event: 停止事件

        返回:
            bool: 是否成功执行
        """
        process = None
        try:
            k_filename = os.path.basename(k_file_path)

            # 构建LS-DYNA命令
            cmd = [
                self.ansys_lsdyna_path,
                f"i={k_filename}",
                f"ncpu={cpu_count}",
                f"jobid={task_id}"
            ]

            logger.info(f"执行LS-DYNA命令: {' '.join(cmd)}")

            if stop_event.is_set():
                logger.info(f"任务 {task_id} 在启动前被中止")
                return False

            timeout_seconds = timeout_minutes * 60 * 1.25
            start_time = time.time()

            # 将 stdout/stderr 重定向到文件，避免管道缓冲区死锁
            stdout_log = os.path.join(work_directory, f"{task_id}_lsdyna_stdout.log")
            stderr_log = os.path.join(work_directory, f"{task_id}_lsdyna_stderr.log")

            stdout_file = open(stdout_log, 'w', encoding='utf-8')
            stderr_file = open(stderr_log, 'w', encoding='utf-8')

            try:
                # 使用 Popen 启动进程，stdout/stderr 重定向到文件
                process = subprocess.Popen(
                    cmd,
                    cwd=work_directory,
                    stdout=stdout_file,
                    stderr=stderr_file,
                )

                # 保存进程引用
                with self.active_tasks_lock:
                    if task_id in self.active_tasks:
                        self.active_tasks[task_id]['process'] = process
                        self.active_tasks[task_id]['phase'] = 'running'

                logger.info(f"LS-DYNA进程已启动: PID={process.pid}")

                # 轮询检查
                while process.poll() is None:
                    # 检查中止信号
                    if stop_event.is_set():
                        logger.info(f"任务 {task_id} 收到中止信号，终止进程 PID={process.pid}")
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                            logger.info(f"LS-DYNA进程已优雅终止: PID={process.pid}")
                        except subprocess.TimeoutExpired:
                            logger.warning(f"LS-DYNA进程未响应terminate，强制kill: PID={process.pid}")
                            process.kill()
                            process.wait()
                        return False

                    # 检查超时
                    if time.time() - start_time > timeout_seconds:
                        logger.warning(f"任务 {task_id} LS-DYNA执行超时({time.time() - start_time:.0f}秒)，终止进程")
                        process.kill()
                        process.wait()
                        return False

                    time.sleep(1)

                # 进程已结束，检查返回码
                if process.returncode == 0:
                    logger.info(f"LS-DYNA程序执行成功: {task_id}")
                    return True
                else:
                    logger.warning(f"LS-DYNA程序执行失败: {task_id}, 返回码: {process.returncode}")
                    return False

            finally:
                # 确保关闭文件句柄
                stdout_file.close()
                stderr_file.close()

        except Exception as e:
            logger.error(f"运行LS-DYNA程序时出错: {e}")
            if process and process.poll() is None:
                try:
                    process.kill()
                    process.wait()
                except Exception:
                    pass
            return False

    def run_ansys_fluent(self, jou_file_path: str, work_directory: str, task_id: str,
                        cpu_count: int, timeout_minutes: int, stop_event: threading.Event) -> bool:
        """
        运行Fluent程序（支持真正的中止）

        参数:
            jou_file_path: JOU文件路径
            work_directory: 工作目录
            task_id: 任务ID
            cpu_count: CPU核心数
            timeout_minutes: 超时时间(分钟)
            stop_event: 停止事件

        返回:
            bool: 是否成功执行
        """
        process = None
        try:
            jou_filename = os.path.basename(jou_file_path)
            output_log = f"{task_id}_output.log"

            cmd = [
                self.ansys_fluent_path,
                "3ddp",
                "-g",
                f"-t{cpu_count}",
                f"-i", jou_filename,
                f"-o", output_log
            ]

            logger.info(f"执行Fluent命令: {' '.join(cmd)}")

            if stop_event.is_set():
                logger.info(f"任务 {task_id} 在启动前被中止")
                return False

            timeout_seconds = timeout_minutes * 60 * 1.25
            start_time = time.time()

            # 将 stdout/stderr 重定向到文件，避免管道缓冲区死锁
            stdout_log_file = os.path.join(work_directory, f"{task_id}_fluent_stdout.log")
            stderr_log_file = os.path.join(work_directory, f"{task_id}_fluent_stderr.log")

            stdout_file = open(stdout_log_file, 'w', encoding='utf-8')
            stderr_file = open(stderr_log_file, 'w', encoding='utf-8')

            try:
                # 使用 Popen 启动进程，stdout/stderr 重定向到文件
                process = subprocess.Popen(
                    cmd,
                    cwd=work_directory,
                    stdout=stdout_file,
                    stderr=stderr_file,
                )

                # 保存进程引用
                with self.active_tasks_lock:
                    if task_id in self.active_tasks:
                        self.active_tasks[task_id]['process'] = process
                        self.active_tasks[task_id]['phase'] = 'running'

                logger.info(f"Fluent进程已启动: PID={process.pid}")

                # 轮询检查
                while process.poll() is None:
                    # 检查中止信号
                    if stop_event.is_set():
                        logger.info(f"任务 {task_id} 收到中止信号，终止进程 PID={process.pid}")
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                            logger.info(f"Fluent进程已优雅终止: PID={process.pid}")
                        except subprocess.TimeoutExpired:
                            logger.warning(f"Fluent进程未响应terminate，强制kill: PID={process.pid}")
                            process.kill()
                            process.wait()
                        return False

                    # 检查超时
                    if time.time() - start_time > timeout_seconds:
                        logger.warning(f"任务 {task_id} Fluent执行超时({time.time() - start_time:.0f}秒)，终止进程")
                        process.kill()
                        process.wait()
                        return False

                    time.sleep(1)

                # 进程已结束，检查返回码
                if process.returncode == 0:
                    logger.info(f"Fluent程序执行成功: {task_id}")
                    return True
                else:
                    logger.warning(f"Fluent程序执行失败: {task_id}, 返回码: {process.returncode}")
                    return False

            finally:
                # 确保关闭文件句柄
                stdout_file.close()
                stderr_file.close()

        except Exception as e:
            logger.error(f"运行Fluent程序时出错: {e}")
            if process and process.poll() is None:
                try:
                    process.kill()
                    process.wait()
                except Exception:
                    pass
            return False

    def run_ansys_mechanical(self, inp_file_path: str, work_directory: str, task_id: str,
                           cpu_count: int, timeout_minutes: int, stop_event: threading.Event) -> bool:
        """
        运行Mechanical APDL程序（支持真正的中止）

        参数:
            inp_file_path: INP文件路径
            work_directory: 工作目录
            task_id: 任务ID
            cpu_count: CPU核心数
            timeout_minutes: 超时时间(分钟)
            stop_event: 停止事件

        返回:
            bool: 是否成功执行
        """
        process = None
        try:
            inp_filename = os.path.basename(inp_file_path)
            output_log = f"{task_id}_output.log"

            cmd = [
                self.ansys_exe_path,
                "-b",
                "-np", str(cpu_count),
                "-i", inp_filename,
                "-o", output_log
            ]

            logger.info(f"执行Mechanical APDL命令: {' '.join(cmd)}")

            if stop_event.is_set():
                logger.info(f"任务 {task_id} 在启动前被中止")
                return False

            timeout_seconds = timeout_minutes * 60 * 1.25
            start_time = time.time()

            # 将 stdout/stderr 重定向到文件，避免管道缓冲区死锁
            stdout_log_file = os.path.join(work_directory, f"{task_id}_mechanical_stdout.log")
            stderr_log_file = os.path.join(work_directory, f"{task_id}_mechanical_stderr.log")

            stdout_file = open(stdout_log_file, 'w', encoding='utf-8')
            stderr_file = open(stderr_log_file, 'w', encoding='utf-8')

            try:
                # 使用 Popen 启动进程，stdout/stderr 重定向到文件
                process = subprocess.Popen(
                    cmd,
                    cwd=work_directory,
                    stdout=stdout_file,
                    stderr=stderr_file,
                )

                # 保存进程引用
                with self.active_tasks_lock:
                    if task_id in self.active_tasks:
                        self.active_tasks[task_id]['process'] = process
                        self.active_tasks[task_id]['phase'] = 'running'

                logger.info(f"Mechanical APDL进程已启动: PID={process.pid}")

                # 轮询检查
                while process.poll() is None:
                    # 检查中止信号
                    if stop_event.is_set():
                        logger.info(f"任务 {task_id} 收到中止信号，终止进程 PID={process.pid}")
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                            logger.info(f"Mechanical APDL进程已优雅终止: PID={process.pid}")
                        except subprocess.TimeoutExpired:
                            logger.warning(f"Mechanical APDL进程未响应terminate，强制kill: PID={process.pid}")
                            process.kill()
                            process.wait()
                        return False

                    # 检查超时
                    if time.time() - start_time > timeout_seconds:
                        logger.warning(f"任务 {task_id} Mechanical APDL执行超时({time.time() - start_time:.0f}秒)，终止进程")
                        process.kill()
                        process.wait()
                        return False

                    time.sleep(1)

                # 进程已结束，检查返回码
                if process.returncode == 0:
                    logger.info(f"Mechanical APDL程序执行成功: {task_id}")
                    return True
                else:
                    logger.warning(f"Mechanical APDL程序执行失败: {task_id}, 返回码: {process.returncode}")
                    return False

            finally:
                # 确保关闭文件句柄
                stdout_file.close()
                stderr_file.close()

        except Exception as e:
            logger.error(f"运行Mechanical APDL程序时出错: {e}")
            if process and process.poll() is None:
                try:
                    process.kill()
                    process.wait()
                except Exception:
                    pass
            return False
    
    def upload_result_files(self, work_directory: str, task_id: str, user_id: str, 
                          bucket: str, file_type: int) -> None:
        """
        上传结果文件到MinIO
        """
        try:
            if file_type == 0:  # LS-DYNA
                # 上传 .d3hsp 和 .messag 文件
                for pattern in ["*.d3hsp", "*.messag"]:
                    for file_path in glob.glob(os.path.join(work_directory, pattern)):
                        if os.path.exists(file_path):
                            filename = os.path.basename(file_path)
                            minio_path = f"{user_id}/{task_id}/output/{filename}"
                            logger.info(f"上传LS-DYNA文件: {filename}")
                            self.minio_sdk.upload_file(bucket, minio_path, file_path)
                        
            elif file_type == 1:  # Fluent
                # 上传 .dat.h5 和 .trn 文件
                dat_h5_file = os.path.join(work_directory, f"{task_id}.dat.h5")
                if os.path.exists(dat_h5_file):
                    minio_path = f"{user_id}/{task_id}/output/{task_id}.dat.h5"
                    self.minio_sdk.upload_file(bucket, minio_path, dat_h5_file)
                
                for file_path in glob.glob(os.path.join(work_directory, "*.trn")):
                    if os.path.exists(file_path):
                        filename = os.path.basename(file_path)
                        minio_path = f"{user_id}/{task_id}/output/{filename}"
                        self.minio_sdk.upload_file(bucket, minio_path, file_path)
                        
            elif file_type == 2:  # Mechanical APDL
                # 上传除了输入文件外的所有文件
                for file_path in glob.glob(os.path.join(work_directory, "*")):
                    if os.path.isfile(file_path):
                        filename = os.path.basename(file_path)
                        if not filename.endswith(('.inp', '.mac', '.cdb')):
                            minio_path = f"{user_id}/{task_id}/output/{filename}"
                            self.minio_sdk.upload_file(bucket, minio_path, file_path)
                            
        except Exception as e:
            logger.error(f"上传结果文件时出错: {e}")

    def upload_work_directory_files(self, work_directory: str, bucket: str,
                                     user_id: str, task_id: str,
                                     exclude_files: List[str] = None) -> List[str]:
        """
        上传工作目录中的所有文件到 MinIO（排除指定文件）

        参数:
            work_directory: 工作目录路径
            bucket: MinIO bucket 名称
            user_id: 用户ID
            task_id: 任务ID
            exclude_files: 要排除的文件名列表（如原始输入文件）

        返回:
            上传成功的文件路径列表
        """
        if exclude_files is None:
            exclude_files = []

        output_files_found = []
        try:
            for filename in os.listdir(work_directory):
                # 跳过要排除的文件（原始输入文件已上传到 input/ 目录）
                if filename in exclude_files:
                    logger.debug(f"跳过已上传的输入文件: {filename}")
                    continue

                file_path = os.path.join(work_directory, filename)
                if os.path.isfile(file_path):
                    minio_path = f"app-task/{user_id}/{task_id}/output/{filename}"
                    logger.info(f"上传文件到MinIO: {file_path} -> {bucket}/{minio_path}")
                    self.minio_sdk.upload_file(bucket, minio_path, file_path)
                    output_files_found.append(minio_path)
        except Exception as e:
            logger.error(f"遍历或上传工作目录文件时出错: {e}")
        return output_files_found

    def process_task_async(self, msg_data: Dict[str, Any], context_data: Dict[str, Any],
                           stop_event: threading.Event):
        """
        异步处理单个任务

        参数:
            msg_data: 消息数据
            context_data: 上下文数据
            stop_event: 中止事件（由 run_service_loop 传入）
        """
        task_id = context_data.get("task_id")

        try:
            logger.info(f"开始异步处理ANSYS任务: {task_id}")

            # 注意：任务已在 run_service_loop 中注册，这里不再调用 add_active_task
            # stop_event 由参数传入

            # 更新阶段
            with self.active_tasks_lock:
                if task_id in self.active_tasks:
                    self.active_tasks[task_id]['phase'] = 'processing'

            bucket = msg_data.get("bucket") or msg_data.get("minio_file_path", {}).get("bucket")
            obj_path = msg_data.get("obj_path") or msg_data.get("minio_file_path", {}).get("obj_path")
            user_id = context_data.get("user_id")
            task_info = context_data.get("task_info", {})
            
            if not bucket or not obj_path or not user_id:
                self.send_task_result(task_id, TaskStatus.FAILED, "消息缺少必要字段", {})
                return
            
            estimated_time = 60*24*3  # 默认3天
            # estimated_time = task_info.get('estimated_time', 30)
            cpu_count = task_info.get('cpu_count')
            iterations = task_info.get('iterations', 500)
            auto_retry_on_failure = task_info.get('auto_retry_on_failure', 0)
            retry_count = task_info.get('retry_count', 0)
            
            attempts = 0
            success = False
            error_message = ""
            file_type = -1
            
            while attempts <= retry_count:
                if attempts > 0:
                    logger.info(f"任务 {task_id} 尝试第 {attempts} 次重试")
                
                attempts += 1
                
                if stop_event.is_set():
                    self.send_task_result(task_id, TaskStatus.ABORTED, "任务被用户手动中止", {})
                    return
                
                work_directory = tempfile.mkdtemp(prefix=f"ansys_{task_id}_")
                logger.info(f"任务 {task_id} 创建临时工作目录: {work_directory}")
                
                try:
                    original_filename = os.path.basename(obj_path)
                    local_file_path = os.path.join(work_directory, original_filename)
                    
                    logger.info(f"任务 {task_id} 从MinIO下载文件: {obj_path}")
                    self.minio_sdk.download_file(bucket, obj_path, local_file_path)
                    
                    file_type = self.determine_file_type(local_file_path)
                    if file_type == -1:
                        error_message = f"不支持的文件类型: {original_filename}"
                        self.send_task_result(task_id, TaskStatus.FAILED, error_message, {})
                        return
                    
                    logger.info(f"任务 {task_id} 检测到文件类型: {file_type}")
                    
                    # 上传输入文件到MinIO
                    input_minio_path = f"app-task/{user_id}/{task_id}/input/{original_filename}"
                    self.minio_sdk.upload_file(bucket, input_minio_path, local_file_path)
                    
                    ansys_success = False
                    
                    if file_type == 0:  # LS-DYNA
                        ansys_success = self.run_ansys_lsdyna(
                            local_file_path, work_directory, task_id, 
                            cpu_count, estimated_time, stop_event
                        )
                    elif file_type == 1:  # Fluent
                        # 检查是否有对应的.dat文件，确保格式一致
                        dat_file = None
                        
                        if original_filename.endswith('.cas.h5'):
                            # .cas.h5 文件只能搭配 .dat.h5 文件
                            base_name = original_filename[:-7]  # 去掉.cas.h5
                            dat_filename = f"{base_name}.dat.h5"
                            
                            dat_obj_path = obj_path.replace(original_filename, dat_filename)
                            dat_local_path = os.path.join(work_directory, dat_filename)
                            try:
                                self.minio_sdk.download_file(bucket, dat_obj_path, dat_local_path)
                                dat_file = dat_local_path
                                logger.info(f"找到并下载了对应的.dat.h5文件: {dat_filename}")
                            except:
                                logger.info(f"未找到对应的.dat.h5文件: {dat_filename}")
                                
                        elif original_filename.endswith('.cas'):
                            # .cas 文件只能搭配 .dat 文件
                            base_name = original_filename[:-4]  # 去掉.cas
                            dat_filename = f"{base_name}.dat"
                            
                            dat_obj_path = obj_path.replace(original_filename, dat_filename)
                            dat_local_path = os.path.join(work_directory, dat_filename)
                            try:
                                self.minio_sdk.download_file(bucket, dat_obj_path, dat_local_path)
                                dat_file = dat_local_path
                                logger.info(f"找到并下载了对应的.dat文件: {dat_filename}")
                            except:
                                logger.info(f"未找到对应的.dat文件: {dat_filename}")
                        
                        elif original_filename.endswith('.dat.h5'):
                            # 如果输入文件是.dat.h5，寻找对应的.cas.h5文件
                            base_name = original_filename[:-7]  # 去掉.dat.h5
                            cas_filename = f"{base_name}.cas.h5"
                            
                            cas_obj_path = obj_path.replace(original_filename, cas_filename)
                            cas_local_path = os.path.join(work_directory, cas_filename)
                            try:
                                self.minio_sdk.download_file(bucket, cas_obj_path, cas_local_path)
                                # 将cas文件设为主文件，dat文件为辅助文件
                                dat_file = local_file_path  # 原来的.dat.h5文件
                                local_file_path = cas_local_path  # .cas.h5文件作为主文件
                                logger.info(f"找到并下载了对应的.cas.h5文件: {cas_filename}")
                            except:
                                logger.warning(f"未找到对应的.cas.h5文件: {cas_filename}")
                                
                        elif original_filename.endswith('.dat'):
                            # 如果输入文件是.dat，寻找对应的.cas文件
                            base_name = original_filename[:-4]  # 去掉.dat
                            cas_filename = f"{base_name}.cas"
                            
                            cas_obj_path = obj_path.replace(original_filename, cas_filename)
                            cas_local_path = os.path.join(work_directory, cas_filename)
                            try:
                                self.minio_sdk.download_file(bucket, cas_obj_path, cas_local_path)
                                # 将cas文件设为主文件，dat文件为辅助文件
                                dat_file = local_file_path  # 原来的.dat文件
                                local_file_path = cas_local_path  # .cas文件作为主文件
                                logger.info(f"找到并下载了对应的.cas文件: {cas_filename}")
                            except:
                                logger.warning(f"未找到对应的.cas文件: {cas_filename}")
                        
                        jou_file_path = self.create_fluent_journal_file(
                            work_directory, task_id, local_file_path, dat_file, iterations
                        )
                        
                        ansys_success = self.run_ansys_fluent(
                            jou_file_path, work_directory, task_id, 
                            cpu_count, estimated_time, stop_event
                        )
                    elif file_type == 2:  # Mechanical APDL
                        ansys_success = self.run_ansys_mechanical(
                            local_file_path, work_directory, task_id, 
                            cpu_count, estimated_time, stop_event
                        )
                    
                    if stop_event.is_set():
                        self.send_task_result(task_id, TaskStatus.ABORTED, "任务被用户手动中止", {})
                        return
                    
                    if ansys_success:
                        logger.info(f"任务 {task_id} 开始监控ANSYS结果")
                        monitor_result = monitor_ansys_result_files(work_directory, task_id, estimated_time, file_type)
                        
                        if monitor_result == 1:
                            success = True
                            logger.info(f"任务 {task_id} ANSYS仿真成功")
                        else:
                            success = False
                            if monitor_result == 0:
                                error_message = "ANSYS仿真失败"
                            elif monitor_result == 3:
                                error_message = "ANSYS仿真超时"
                            logger.warning(f"任务 {task_id} ANSYS仿真未成功: 结果码: {monitor_result}")
                    else:
                        success = False
                        error_message = "ANSYS程序执行失败"

                    # 无论成功还是失败，都上传所有文件（便于调试）
                    # 收集所有需要排除的输入文件
                    exclude_files = [original_filename]
                    if file_type == 1 and dat_file:  # Fluent 有多个输入文件
                        exclude_files.append(os.path.basename(dat_file))

                    output_files_found = self.upload_work_directory_files(
                        work_directory, bucket, user_id, task_id,
                        exclude_files=exclude_files
                    )
                    
                    if success or (not auto_retry_on_failure) or attempts >= retry_count:
                        break
                
                except Exception as e:
                    logger.error(f"任务 {task_id} 处理时发生错误: {e}")
                    error_message = f"处理过程发生错误: {str(e)}"
                    
                    if not auto_retry_on_failure or attempts >= retry_count:
                        pass
                
                finally:
                    try:
                        shutil.rmtree(work_directory, ignore_errors=True)
                    except Exception as e:
                        logger.error(f"清理临时目录时出错: {e}")
            
            final_task_status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
            self.send_task_result(task_id, final_task_status, error_message, {})
            
        except Exception as e:
            logger.error(f"任务 {task_id} 异步处理时发生错误: {e}")
            self.send_task_result(task_id, TaskStatus.FAILED, f"异步处理错误: {str(e)}", {})
        finally:
            self.remove_active_task(task_id)
    
    def send_task_result(self, task_id: str, task_status: TaskStatus, error_message: str, output_data: Dict[str, Any]):
        """发送任务结果（带防重复机制）"""
        # 防重复发送检查
        with self.active_tasks_lock:
            task_info = self.active_tasks.get(task_id)
            if task_info:
                if task_info.get('result_sent') and task_info['result_sent'].is_set():
                    logger.warning(f"任务 {task_id} 结果已发送过，跳过重复发送")
                    return
                if task_info.get('result_sent'):
                    task_info['result_sent'].set()

        try:
            logger.info(f"任务 {task_id} 发送处理结果: status={task_status.name}")
            self.mq_sdk.send_result_http(
                output_data=output_data,
                url=self.plate_url,
                task_status=task_status,
                error_message=error_message,
                process_id=os.getpid(),
            )
        except Exception as e:
            logger.error(f"任务 {task_id} 发送结果时出错: {e}")
    
    def run_service_loop(self):
        """运行服务主循环"""
        logger.info("开始运行ANSYS服务循环")
        
        while self.running:
            try:
                msg_data, context_data = self.mq_sdk.receive_from_sub_service(
                    sub_service_type=SimulationType.ANSYS,
                    timeout=10
                )
                
                if not msg_data or not context_data:
                    continue
                
                logger.info(f"接收到消息: {msg_data}")
                logger.info(f"接收到上下文: {context_data}")
                
                task_id = context_data.get("task_id")
                if not task_id:
                    logger.error("上下文缺少task_id，跳过处理")
                    continue
                
                if msg_data.get("stop_flag", False):
                    logger.info(f"接收到中止任务请求: {task_id}")
                    if self.handle_stop_task(task_id):
                        logger.info(f"已设置任务 {task_id} 中止标志")
                    else:
                        try:
                            self.send_task_result(task_id, TaskStatus.ABORTED, "任务被用户手动中止", {})
                        except Exception as e:
                            logger.error(f"发送任务 {task_id} 中止状态时出错: {e}")
                    continue

                # 先注册任务（消除竞态条件：在提交到线程池前先注册，确保中止请求能找到任务）
                stop_event = self.add_active_task(task_id)

                # 然后提交到线程池，传入 stop_event
                logger.info(f"提交任务 {task_id} 到线程池进行异步处理")
                self.executor.submit(self.process_task_async, msg_data, context_data, stop_event)
            
            except KeyboardInterrupt:
                logger.info("接收到键盘中断，准备退出...")
                self.running = False
                break
            except Exception as e:
                logger.error(f"处理消息时出错: {e}")
                continue
        
        logger.info("服务循环已退出")


def main():
    """主函数"""
    try:
        logger.info("启动ANSYS服务")
        service = AnsysService(r"G:\pds\similation_services\nan-gang-pds_-simulation\model_app\sub-services.json")
        service.run_service_loop()
    except Exception as e:
        logger.error(f"服务运行时发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()