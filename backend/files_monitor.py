#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
文件监控模块，提供实时监控指定目录下是否存在所有指定文件的功能。
支持Windows和CentOS系统，可设置最大监控时间。
"""

import os
import time
import platform
import re
from typing import List, Optional, Union, Tuple, Any
import threading
from datetime import datetime, timedelta

# 状态码定义
STATUS_ALL_FILES_FOUND = 2000  # 文件全部存在
STATUS_PARTIAL_FILES_FOUND = 5000  # 文件不全
STATUS_NO_FILES_FOUND = 5500  # 监控失败，没有文件生成

class FilesMonitor:
    """
    文件监控器类，用于监控指定目录下是否存在所有指定的文件。
    支持Windows和CentOS系统，可设置最大监控时间。
    """
    
    def __init__(self, monitor_dir: str, file_names: List[str], max_time: Union[int, float] = -1):
        """
        初始化文件监控器
        
        参数:
            monitor_dir: 监控目录的路径
            file_names: 需要监控的文件名称列表（可以带或不带文件扩展名）
            max_time: 最大监控时间（分钟），-1表示无限监控，>0表示最大监控分钟数
        """
        self.monitor_dir = os.path.abspath(monitor_dir)
        self.file_names = file_names
        self.max_time = max_time
        self.stop_event = threading.Event()
        self.timeout_event = threading.Event()  # 新增超时事件
        self.system = platform.system()
        self.timeout_timer = None  # 超时计时器线程
        self.result = None  # 监控结果变量
        self.existing_files = []  # 已存在的文件
        
        print(f"初始化文件监控器: 目录={self.monitor_dir}, 文件列表={self.file_names}, 最大时间={self.max_time}分钟")
        
        # 检查监控目录是否存在
        if not os.path.exists(self.monitor_dir):
            error_msg = f"监控目录不存在: {self.monitor_dir}"
            print(error_msg)
            raise FileNotFoundError(error_msg)
    
    def _timeout_handler(self):
        """超时处理函数，在指定时间后设置超时事件并强制停止监控"""
        print(f"启动超时计时器，设置为{self.max_time}分钟")
        time.sleep(self.max_time * 60)  # 转换为秒
        if not self.stop_event.is_set():
            print(f"监控超时: 超过{self.max_time}分钟未找到所有文件")
            self.timeout_event.set()
            self.stop_event.set()  # 强制停止所有监控
    
    def _check_all_files_exist(self) -> Tuple[List[str], List[str]]:
        """
        检查所有指定的文件是否都存在于监控目录中
        
        返回:
            元组，包含 (已存在的文件路径列表, 缺失的文件名列表)
        """
        try:
            existing_files = []
            missing_files = []
            
            # 获取目录中的所有文件
            dir_files = os.listdir(self.monitor_dir)
            
            # 检查每个文件名
            for file_name in self.file_names:
                file_found = False
                
                # 对于没有扩展名的文件名，检查是否有以该名称开头的文件
                for dir_file in dir_files:
                    if dir_file == file_name or (os.path.splitext(dir_file)[0] == file_name):
                        file_path = os.path.join(self.monitor_dir, dir_file)
                        if os.path.isfile(file_path):
                            existing_files.append(file_path)
                            file_found = True
                            break
                
                if not file_found:
                    missing_files.append(file_name)
            
            if missing_files:
                print(f"仍有文件未找到: {missing_files}, 已找到的文件: {existing_files}")
            else:
                print(f"所有文件均已找到: {existing_files}")
                
            return existing_files, missing_files
            
        except Exception as e:
            print(f"检查文件存在性时发生错误: {str(e)}")
            return [], self.file_names
    
    def _windows_monitor(self) -> Union[List[str], Tuple[List[str], int]]:
        """
        Windows平台下的文件监控实现
        
        返回:
            如果所有文件都存在，返回文件路径列表
            如果部分文件存在且超时，返回元组 (已存在文件路径列表, 状态码)
            如果没有文件存在且超时，返回元组 ([], 状态码)
        """
        try:
            import win32file
            import win32con
            import win32event  # 添加对win32event的导入
            
            # 首先检查文件是否都已存在
            existing_files, missing_files = self._check_all_files_exist()
            self.existing_files = existing_files  # 保存已存在的文件
            
            if not missing_files:  # 所有文件都存在
                return existing_files
            
            print("Windows平台使用轮询方式监控文件，确保超时能立即响应")
            
            # 使用简单的轮询方式，确保能快速响应超时信号
            poll_interval = 2  # 轮询间隔秒数
            
            while not self.stop_event.is_set() and not self.timeout_event.is_set():
                # 检查文件是否存在
                existing_files, missing_files = self._check_all_files_exist()
                self.existing_files = existing_files  # 更新已存在的文件列表
                
                if not missing_files:  # 所有文件都存在
                    return existing_files
                
                # 短暂休眠，避免CPU占用过高
                time.sleep(poll_interval)
            
            # 如果是因为超时退出，返回已找到的文件和相应状态码
            if self.timeout_event.is_set():
                print("Windows监控检测到超时事件，立即退出")
                if self.existing_files:
                    return self.existing_files, STATUS_PARTIAL_FILES_FOUND
                else:
                    return [], STATUS_NO_FILES_FOUND
                
        except ImportError as ie:
            print(f"未安装必要的Windows监控库: {str(ie)}，将使用轮询方式监控文件")
            return self._polling_monitor()
        except Exception as e:
            print(f"Windows监控过程中发生错误: {str(e)}")
            return self._polling_monitor()
    
    def _linux_monitor(self) -> Union[List[str], Tuple[List[str], int]]:
        """
        Linux平台下的文件监控实现
        
        返回:
            如果所有文件都存在，返回文件路径列表
            如果部分文件存在且超时，返回元组 (已存在文件路径列表, 状态码)
            如果没有文件存在且超时，返回元组 ([], 状态码)
        """
        try:
            import pyinotify
            
            # 首先检查文件是否都已存在
            existing_files, missing_files = self._check_all_files_exist()
            self.existing_files = existing_files  # 保存已存在的文件
            
            if not missing_files:  # 所有文件都存在
                return existing_files
            
            class EventHandler(pyinotify.ProcessEvent):
                def __init__(self, monitor):
                    self.monitor = monitor
                
                def process_default(self, event):
                    # 检查是否所有文件都存在
                    existing_files, missing_files = self.monitor._check_all_files_exist()
                    self.monitor.existing_files = existing_files  # 更新已存在的文件
                    
                    if not missing_files:  # 所有文件都存在
                        self.monitor.stop_event.set()
                        self.monitor.found_files = existing_files
            
            # 设置监控
            wm = pyinotify.WatchManager()
            handler = EventHandler(self)
            notifier = pyinotify.Notifier(wm, handler)
            
            # 添加监控
            mask = (pyinotify.IN_CREATE | pyinotify.IN_MOVED_TO | 
                    pyinotify.IN_MODIFY | pyinotify.IN_ATTRIB)
            wm.add_watch(self.monitor_dir, mask)
            
            # 初始化结果变量
            self.found_files = None
            
            # 设置超时检查间隔
            check_interval = 0.5  # 秒
            
            # 开始监控
            while not self.stop_event.is_set() and not self.timeout_event.is_set():
                # 处理事件，设置较短的超时时间
                notifier.process_events()
                if notifier.check_events(timeout=int(check_interval * 1000)):  # 转换为毫秒
                    notifier.read_events()
                
                # 定期检查文件是否已经存在，避免错过某些事件
                existing_files, missing_files = self._check_all_files_exist()
                self.existing_files = existing_files  # 更新已存在的文件
                
                if not missing_files:  # 所有文件都存在
                    self.stop_event.set()
                    self.found_files = existing_files
                
                # 检查是否已超时
                if self.timeout_event.is_set():
                    print("检测到超时事件，停止Linux监控")
                    if self.existing_files:
                        return self.existing_files, STATUS_PARTIAL_FILES_FOUND
                    else:
                        return [], STATUS_NO_FILES_FOUND
            
            # 检查是否因为超时退出
            if self.timeout_event.is_set():
                if self.existing_files:
                    return self.existing_files, STATUS_PARTIAL_FILES_FOUND
                else:
                    return [], STATUS_NO_FILES_FOUND
            
            return self.found_files
            
        except ImportError as ie:
            print(f"未安装pyinotify库: {str(ie)}，将使用轮询方式监控文件")
            return self._polling_monitor()
        except Exception as e:
            print(f"Linux监控过程中发生错误: {str(e)}")
            return self._polling_monitor()
    
    def _polling_monitor(self) -> Union[List[str], Tuple[List[str], int]]:
        """
        基于轮询的文件监控实现（适用于所有平台的备选方案）
        
        返回:
            如果所有文件都存在，返回文件路径列表
            如果部分文件存在且超时，返回元组 (已存在文件路径列表, 状态码)
            如果没有文件存在且超时，返回元组 ([], 状态码)
        """
        print("使用轮询方式监控文件")
        
        # 首先检查文件是否都已存在
        existing_files, missing_files = self._check_all_files_exist()
        self.existing_files = existing_files  # 保存已存在的文件
            
        if not missing_files:  # 所有文件都存在
            return existing_files
        
        # 轮询检查文件
        while not self.stop_event.is_set() and not self.timeout_event.is_set():
            # 检查所有文件是否都存在
            existing_files, missing_files = self._check_all_files_exist()
            self.existing_files = existing_files  # 更新已存在的文件
            
            if not missing_files:  # 所有文件都存在
                return existing_files
            
            # 短暂休眠，避免占用过多CPU
            time.sleep(0.5)
            
            # 检查是否已超时
            if self.timeout_event.is_set():
                print("检测到超时事件，停止轮询监控")
                if self.existing_files:
                    return self.existing_files, STATUS_PARTIAL_FILES_FOUND
                else:
                    return [], STATUS_NO_FILES_FOUND
        
        # 检查是否因为超时退出
        if self.timeout_event.is_set():
            if self.existing_files:
                return self.existing_files, STATUS_PARTIAL_FILES_FOUND
            else:
                return [], STATUS_NO_FILES_FOUND
        
        return self.existing_files if not missing_files else (self.existing_files, STATUS_PARTIAL_FILES_FOUND)
    
    def start_monitor(self) -> Union[List[str], Tuple[List[str], int]]:
        """
        开始监控文件
        
        返回:
            如果所有文件都存在，返回文件路径列表
            如果部分文件存在且超时，返回元组 (已存在文件路径列表, 状态码)
            如果没有文件存在且超时，返回元组 ([], 状态码)
            如果发生错误，返回元组 ([], 状态码)
        """
        try:
            print(f"开始监控目录: {self.monitor_dir}")
            
            # 如果设置了超时时间，启动超时计时器线程
            if self.max_time > 0:
                self.timeout_timer = threading.Thread(target=self._timeout_handler)
                self.timeout_timer.daemon = True
                self.timeout_timer.start()
            
            # 根据不同平台选择不同的监控实现
            if self.system == "Windows":
                print("使用Windows平台监控机制")
                self.result = self._windows_monitor()
            elif self.system == "Linux":
                print("使用Linux平台监控机制")
                self.result = self._linux_monitor()
            else:
                print(f"不支持的平台: {self.system}，使用轮询方式监控")
                self.result = self._polling_monitor()
            
            # 如果是因为超时退出，确保返回正确的状态
            if self.timeout_event.is_set():
                print("因超时退出监控")
                if isinstance(self.result, tuple):
                    return self.result
                elif self.existing_files:
                    return self.existing_files, STATUS_PARTIAL_FILES_FOUND
                else:
                    return [], STATUS_NO_FILES_FOUND
                
            # 检查结果类型，确保返回格式正确
            if isinstance(self.result, list):
                if self.result:  # 所有文件都存在
                    return self.result
                else:  # 没有找到任何文件
                    return [], STATUS_NO_FILES_FOUND
            else:  # 返回的是元组，说明是部分文件存在或没有文件
                return self.result
                
        except Exception as e:
            print(f"监控过程中发生错误: {str(e)}")
            return [], STATUS_NO_FILES_FOUND
        finally:
            print("监控结束")
            self.stop_event.set()
            # 等待超时线程结束
            if self.timeout_timer and self.timeout_timer.is_alive():
                # 不需要join，因为timeout_timer是daemon线程
                pass
    
    def stop_monitor(self):
        """停止监控"""
        print("停止监控")
        self.stop_event.set()


def monitor_files(
    monitor_dir: str, 
    file_names: List[str], 
    max_time: Union[int, float] = -1
) -> Union[List[str], Tuple[List[str], int]]:
    """
    监控指定目录下是否存在所有指定的文件
    
    参数:
        monitor_dir: 监控目录的路径
        file_names: 需要监控的文件名称列表（可以带或不带文件扩展名）
        max_time: 最大监控时间（分钟），-1表示无限监控，>0表示最大监控分钟数
    
    返回:
        如果所有文件都存在，返回文件路径列表
        如果部分文件存在且超时，返回元组 (已存在文件路径列表, 5000)
        如果超时且没有文件存在，返回元组 ([], 5500)
        如果发生错误，返回元组 ([], 5500)
    """
    try:
        print(f"开始监控文件: 目录={monitor_dir}, 文件列表={file_names}, 最大时间={max_time}分钟")
        
        monitor = FilesMonitor(monitor_dir, file_names, max_time)
        result = monitor.start_monitor()
        
        # 根据结果类型，记录适当的日志信息
        if isinstance(result, list):
            if result:
                print(f"所有文件已找到: {result}")
                return result
            else:
                print("监控结束，未找到任何文件")
                return [], STATUS_NO_FILES_FOUND
        else:  # 元组结果
            files_list, status_code = result
            if status_code == STATUS_PARTIAL_FILES_FOUND:
                print(f"部分文件已找到: {files_list}")
            else:
                print("监控结束，未找到任何文件")
            return result
        
    except Exception as e:
        print(f"监控文件过程中发生错误: {str(e)}")
        return [], STATUS_NO_FILES_FOUND


def monitor_comsol_result_files(work_directory: str, task_id: str,
                                 estimated_time: Union[int, float],
                                 stop_event: Optional[threading.Event] = None) -> int:
    """
    监控 COMSOL 仿真结果文件

    参数:
        work_directory: 工作目录路径
        task_id: 任务ID
        estimated_time: 预计耗时(分钟)
        stop_event: 可选的中止事件，设置后立即退出监控

    返回:
        int: -1-被中止, 0-仿真失败, 1-仿真成功, 2-仿真部分成功, 3-超时返回
    """
    # 完成标志（中英文）
    COMPLETION_PATTERNS = [
        "Current Progress: 100 % - Done",
        "当前进度: 100 % - 完成",
        "Current Progress : 100 % - Done",   # 空格变体
        "当前进度 : 100 % - 完成",            # 空格变体
    ]

    # 错误标志正则表达式（使用单词边界匹配，避免误匹配 Tfail、NLfail、LinErr 等）
    # \b 表示单词边界，确保匹配完整单词而非子串
    ERROR_REGEX_PATTERNS = [
        r'\bError\b',           # 匹配独立的 Error 单词
        r'\berror\b',           # 匹配独立的 error 单词
        r'\bERROR\b',           # 匹配独立的 ERROR 单词
        r'\bFail\b',            # 匹配独立的 Fail 单词（不匹配 Tfail、NLfail）
        r'\bfail\b',            # 匹配独立的 fail 单词
        r'\bFAIL\b',            # 匹配独立的 FAIL 单词
        r'\bFailed\b',          # 匹配 Failed
        r'\bfailed\b',          # 匹配 failed
        r'\bFAILED\b',          # 匹配 FAILED
        r'失败',                 # 中文失败
        r'错误',                 # 中文错误（不带冒号，可匹配 "/*****错误********/"）
        r'出错',                 # 中文出错
        r'损坏',                 # 文件损坏
        r'无效',                 # 文件无效
        r'异常',                 # 异常情况
    ]

    try:
        print(f"开始监控 COMSOL 结果: 任务ID={task_id}, 预计时间={estimated_time}分钟")

        # 构建日志文件路径
        log_file_path = os.path.join(work_directory, f"{task_id}.log")

        # 设置超时时间，增加25%缓冲
        timeout_seconds = estimated_time 
        start_time = time.time()

        # 轮询检查日志文件
        while True:
            # 检查是否被中止
            if stop_event and stop_event.is_set():
                print(f"COMSOL 监控被中止: 任务 {task_id}")
                return -1  # 被中止

            current_time = time.time()
            elapsed_time = current_time - start_time

            # 检查是否超时
            if elapsed_time >= timeout_seconds:
                print(f"COMSOL 仿真监控超时: {elapsed_time:.2f} 秒")
                return 3  # 超时返回

            # 检查日志文件是否存在
            if os.path.exists(log_file_path):
                try:
                    # 读取日志文件内容
                    with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        log_content = f.read()

                    # 检查完成标志（任一匹配即可）
                    has_complete = any(pattern in log_content for pattern in COMPLETION_PATTERNS)

                    # 检查错误标志（使用正则表达式单词边界匹配）
                    has_error = any(re.search(pattern, log_content) for pattern in ERROR_REGEX_PATTERNS)

                    print(f"日志文件分析: has_error={has_error}, has_complete={has_complete}")

                    # 根据不同组合返回状态
                    if has_complete and has_error:
                        print(f"COMSOL 仿真部分成功: 任务 {task_id}")
                        return 2  # 仿真部分成功
                    elif has_complete and not has_error:
                        print(f"COMSOL 仿真成功: 任务 {task_id}")
                        return 1  # 仿真成功
                    elif not has_complete and has_error:
                        print(f"COMSOL 仿真失败: 任务 {task_id}")
                        return 0  # 仿真失败
                    # 如果都没有，继续监控

                except Exception as e:
                    print(f"读取日志文件时出错: {e}")
                    # 继续监控，不因读取错误而退出

            # 短暂休眠，避免过度占用CPU
            time.sleep(2)

    except Exception as e:
        print(f"监控 COMSOL 结果时发生错误: {e}")
        return 0  # 出错时返回失败状态


def monitor_thermo_result_files11(work_directory: str, task_id: str, estimated_time: Union[int, float]) -> int:
    """
    监控 Thermo-Calc 仿真结果文件
    
    参数:
        work_directory: 工作目录路径
        task_id: 任务ID  
        estimated_time: 预计耗时(分钟)
    
    返回:
        int: 0-仿真失败, 1-仿真成功, 3-超时返回
    """
    try:
        print(f"开始监控 Thermo-Calc 结果: 任务ID={task_id}, 预计时间={estimated_time}分钟")
        
        # 构建日志文件路径
        log_file_path = os.path.join(work_directory, f"{task_id}.log")
        
        # 设置超时时间，增加25%缓冲
        timeout_seconds = estimated_time * 1.25 * 60
        start_time = time.time()
        
        # 轮询检查日志文件
        while True:
            current_time = time.time()
            elapsed_time = current_time - start_time
            
            # 检查是否超时
            if elapsed_time >= timeout_seconds:
                print(f"Thermo-Calc 仿真监控超时: {elapsed_time:.2f} 秒")
                return 3  # 超时返回
            
            # 检查日志文件是否存在
            if os.path.exists(log_file_path):
                try:
                    # 读取日志文件内容
                    with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        log_content = f.read()
                    
                    # 检查是否包含SIMULATION_SUCCESS标记
                    if "SIMULATION_SUCCESS" in log_content:
                        print(f"Thermo-Calc 仿真成功: 任务 {task_id}")
                        return 1  # 仿真成功
                    
                    # 如果日志存在但没有成功标记，继续监控
                    
                except Exception as e:
                    print(f"读取日志文件时出错: {e}")
                    # 继续监控，不因读取错误而退出
            
            # 短暂休眠，避免过度占用CPU
            time.sleep(2)
            
    except Exception as e:
        print(f"监控 Thermo-Calc 结果时发生错误: {e}")
        return 0  # 出错时返回失败状态

def monitor_thermo_result_files(work_directory: str, task_id: str, estimated_time: Union[int, float],
                                  stop_event: Optional[threading.Event] = None) -> int:
      """
      监控 Thermo-Calc 仿真结果文件

      参数:
          work_directory: 工作目录路径
          task_id: 任务ID
          estimated_time: 预计耗时(分钟)
          stop_event: 可选的中止事件，设置后立即退出监控

      返回:
          int: -1-被中止, 0-仿真失败, 1-仿真成功, 3-超时返回
      """
      try:
          print(f"开始监控 Thermo-Calc 结果: 任务ID={task_id}, 预计时间={estimated_time}分钟")

          # 设置超时时间，增加25%缓冲
          timeout_seconds = estimated_time * 1.25 * 60
          start_time = time.time()

          # 轮询检查日志文件
          while True:
              # 检查是否被中止
              if stop_event and stop_event.is_set():
                  print(f"Thermo-Calc 监控被中止: 任务 {task_id}")
                  return -1  # 被中止

              current_time = time.time()
              elapsed_time = current_time - start_time

              # 检查是否超时
              if elapsed_time >= timeout_seconds:
                  print(f"Thermo-Calc 仿真监控超时: {elapsed_time:.2f} 秒")
                  return 3  # 超时返回

              # 查找工作目录中所有文件名等于task_id的文件（不区分扩展名）
              matching_files = []
              try:
                  for filename in os.listdir(work_directory):
                      file_path = os.path.join(work_directory, filename)
                      if os.path.isfile(file_path):
                          # 获取文件名（不含扩展名）
                          name_without_ext = os.path.splitext(filename)[0]
                          if name_without_ext == task_id:
                              matching_files.append(file_path)
              except Exception as e:
                  print(f"遍历工作目录时出错: {e}")
                  # 继续监控，不因目录遍历错误而退出

              # 检查找到的文件
              if matching_files:
                  print(f"找到匹配的文件: {matching_files}")

                  # 逐个读取文件，查找SIMULATION_SUCCESS标记
                  for file_path in matching_files:
                      try:
                          # 读取文件内容
                          with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                              file_content = f.read()

                          # 检查是否包含SIMULATION_SUCCESS标记
                          if "SIMULATION_SUCCESS" in file_content:
                              print(f"Thermo-Calc 仿真成功: 任务 {task_id}，在文件 {file_path} 中找到成功标记")
                              return 1  # 仿真成功

                      except Exception as e:
                          print(f"读取文件 {file_path} 时出错: {e}")
                          # 继续检查其他文件，不因单个文件读取错误而退出

                  # 如果所有匹配文件都已检查但没有找到成功标记，继续监控

              # 短暂休眠，避免过度占用CPU
              time.sleep(2)

      except Exception as e:
          print(f"监控 Thermo-Calc 结果时发生错误: {e}")
          return 0  # 出错时返回失败状态

def monitor_ansys_result_files(work_directory: str, task_id: str, estimated_time: Union[int, float], file_type: int) -> int:
    """
    监控 ANSYS 仿真结果文件
    
    参数:
        work_directory: 工作目录路径
        task_id: 任务ID  
        estimated_time: 预计耗时(分钟)
        file_type: 文件类型编号 (0:.k文件, 1:fluent文件, 2:Mechanical APDL文件)
    
    返回:
        int: 0-仿真失败, 1-仿真成功, 3-超时返回
    """
    try:
        print(f"开始监控 ANSYS 结果: 任务ID={task_id}, 文件类型={file_type}, 预计时间={estimated_time}分钟")
        
        # 设置超时时间，增加25%缓冲
        timeout_seconds = estimated_time * 1.25 * 60
        start_time = time.time()
        
        # 轮询检查结果文件
        while True:
            current_time = time.time()
            elapsed_time = current_time - start_time
            
            # 检查是否超时
            if elapsed_time >= timeout_seconds:
                print(f"ANSYS 仿真监控超时: {elapsed_time:.2f} 秒")
                return 3  # 超时返回
            
            # 根据文件类型检查不同的结果文件
            if file_type == 0:  # .k文件 - LS-DYNA
                # 先检查 d3plot 文件是否存在（主要结果输出文件）
                # d3plot 文件命名规则：d3plot 或 {jobid}.d3plot
                d3plot_exists = False
                for f in os.listdir(work_directory):
                    if f == 'd3plot' or f.endswith('.d3plot'):
                        d3plot_path = os.path.join(work_directory, f)
                        if os.path.isfile(d3plot_path):
                            d3plot_exists = True
                            break
                if d3plot_exists:
                    # d3plot 存在，读取 messag 文件检查完成标志
                    # messag 文件命名规则：
                    # - SMP模式：messag (无后缀)
                    # - MPP模式：messag0000, messag0001 等 (以 messag 开头)
                    # - 带 jobid：{jobid}.messag (以 .messag 结尾)
                    messag_files = [f for f in os.listdir(work_directory)
                                    if f == 'messag' or f.startswith('messag') or f.endswith('.messag')]
                    if messag_files:
                        try:
                            messag_file_path = os.path.join(work_directory, messag_files[0])
                            with open(messag_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()

                            # 检查是否含有 "Elapsed time" 完成标志（仿真结束时写入文件末尾）
                            if "Elapsed time" in content:
                                print(f"LS-DYNA 仿真成功: 任务 {task_id}")
                                return 1  # 仿真成功
                            # 如果没有 Elapsed time，继续等待（仿真可能还在进行）

                        except Exception as e:
                            print(f"读取 messag 文件时出错: {e}")
                            # 继续监控，不因读取错误而退出
                        
            elif file_type == 1:  # fluent文件
                # 监控 .trn 文件
                trn_files = [f for f in os.listdir(work_directory) if f.endswith('.trn')]
                if trn_files:
                    try:
                        trn_file_path = os.path.join(work_directory, trn_files[0])
                        with open(trn_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        
                        # 检查是否含有独立的 "error" 单词
                        if re.search(r'\berror\b', content, re.IGNORECASE):
                            print(f"Fluent 仿真失败: 任务 {task_id}")
                            return 0  # 仿真失败
                        else:
                            print(f"Fluent 仿真成功: 任务 {task_id}")
                            return 1  # 仿真成功
                            
                    except Exception as e:
                        print(f"读取 .trn 文件时出错: {e}")
                        # 继续监控，不因读取错误而退出
                        
            elif file_type == 2:  # Mechanical APDL文件
                # 监控 {task_id}_output.log 文件
                log_file_path = os.path.join(work_directory, f"{task_id}_output.log")
                if os.path.exists(log_file_path):
                    try:
                        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        
                        # 检查是否含有独立的 "error" 单词
                        if re.search(r'\berror\b', content, re.IGNORECASE):
                            print(f"Mechanical APDL 仿真失败: 任务 {task_id}")
                            return 0  # 仿真失败
                        else:
                            print(f"Mechanical APDL 仿真成功: 任务 {task_id}")
                            return 1  # 仿真成功
                            
                    except Exception as e:
                        print(f"读取输出日志文件时出错: {e}")
                        # 继续监控，不因读取错误而退出
            
            # 短暂休眠，避免过度占用CPU
            time.sleep(2)
            
    except Exception as e:
        print(f"监控 ANSYS 结果时发生错误: {e}")
        return 0  # 出错时返回失败状态


if __name__ == "__main__":
    # 使用示例
    import sys
    import os
    
    # 测试 monitor_ansys_result_files 函数
    print("=" * 60)
    print("测试 monitor_ansys_result_files 函数")
    print("=" * 60)
    
    # 从用户提供的文件路径推断参数
    work_directory = r"D:\Nercar\FuShunPDS\dab6b8ce_7b3b_4222_bcfd_f5801dfaa32f (2).messag"
    # 检查工作目录是否存在
    if not os.path.exists(work_directory):
        print(f"错误: 工作目录不存在: {work_directory}")
        sys.exit(1)
    

    try:
        with open(work_directory, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            # print(content)
        
        # 检查是否含有独立的 "E r r o r" 字样或独立的 "error" 单词
        if "E r r o r" in content or re.search(r'\berror\b', content, re.IGNORECASE):
            print("LS-DYNA 仿真失败")
           # 仿真失败
        else:
            print(f"LS-DYNA 仿真成功")
            
    except Exception as e:
        print(f"读取 .d3hsp 文件时出错: {e}")
