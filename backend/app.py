#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LS-DYNA K文件参数化系统 - FastAPI后端

提供RESTful API接口，处理参数验证、K文件生成、LS-DYNA计算等功能
"""

import os
import sys
import json
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
from uuid import uuid4
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

# 添加backend目录到Python路径
sys.path.insert(0, os.path.dirname(__file__))


# ==================== 打包模式支持 ====================

def is_frozen() -> bool:
    """检测是否在 PyInstaller 打包模式下运行"""
    return getattr(sys, 'frozen', False)


def get_bundle_dir() -> Path:
    """
    获取打包资源目录（frontend/templates 等静态资源）

    开发模式: 项目根目录
    打包模式: PyInstaller 的 _MEIPASS 目录（_internal）
    """
    if is_frozen():
        # PyInstaller 打包模式：数据文件在 _MEIPASS 目录
        return Path(sys._MEIPASS)
    else:
        # 开发模式：backend/ 的父目录
        return Path(__file__).parent.parent


def get_application_dir() -> Path:
    """
    获取应用程序运行目录（用于存放用户数据：tasks、logs 等）

    开发模式: backend/ 的父目录（项目根目录）
    打包模式: exe 所在目录
    """
    if is_frozen():
        # PyInstaller 打包模式：exe 所在目录
        return Path(sys.executable).parent
    else:
        # 开发模式：backend/ 的父目录
        return Path(__file__).parent.parent


def get_backend_dir() -> Path:
    """
    获取配置文件目录（config.json 等用户可编辑文件）

    开发模式: __file__ 所在目录
    打包模式: exe 所在目录（config.json 放在 exe 同级）
    """
    if is_frozen():
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent


from parameter_config import ParameterConfig
from validators import ParameterValidator
from k_engine import KFileEngine
from animation_generator import AnimationGenerator
from animation_config import AnimationConfig, AnimationTask
from task_manager import TaskManager
from platform_sync import PlatformSyncClient
from task_sync_scheduler import TaskSyncScheduler
from task_queue import init_task_queue, shutdown_task_queue, get_task_queue
from database import TaskStatus

# ==================== 应用生命周期管理 ====================

def load_config() -> dict:
    """加载配置文件"""
    config_path = get_backend_dir() / "config.json"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器（替换on_event）"""
    # Startup
    global task_sync_scheduler
    print("[INFO] 应用启动中...")

    # 加载配置
    config = load_config()
    print(f"[INFO] 配置加载完成: {len(config)} 项配置")

    # 启动任务同步调度器
    try:
        task_sync_scheduler = TaskSyncScheduler()
        task_sync_scheduler.start()
    except Exception as e:
        print(f"[WARNING] 任务同步调度器启动失败: {e}")
        print("[WARNING] 平台A集成功能将不可用")

    # 启动任务执行队列
    try:
        tm = get_task_manager()
        template_path = TEMPLATE_DIR / "1.k"

        def k_engine_factory():
            """K文件引擎工厂函数"""
            return KFileEngine(str(template_path))

        init_task_queue(tm, k_engine_factory, config)
        print("[INFO] 任务执行队列启动成功")
    except Exception as e:
        print(f"[WARNING] 任务执行队列启动失败: {e}")
        print("[WARNING] 平台触发执行功能将不可用")

    print("[INFO] 应用启动完成")

    yield  # 应用运行中

    # Shutdown
    print("[INFO] 应用关闭中...")
    if task_sync_scheduler:
        task_sync_scheduler.shutdown()
    shutdown_task_queue()
    print("[INFO] 应用已关闭")


# 创建FastAPI应用（使用lifespan）
app = FastAPI(
    title="LS-DYNA K文件参数化系统",
    description="子弹穿透仿真参数化生成系统",
    version="1.0.0",
    lifespan=lifespan
)

# CORS配置（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路径配置（兼容开发模式和打包模式）
# 打包资源目录（frontend/templates - 只读，从 _MEIPASS 加载）
BUNDLE_DIR = get_bundle_dir()
TEMPLATE_DIR = BUNDLE_DIR / "templates"
FRONTEND_DIR = BUNDLE_DIR / "frontend"

# 用户数据目录（tasks/logs - 可写，在 exe 同级目录）
BASE_DIR = get_application_dir()

# 任务目录（从配置加载，延迟初始化）
def get_tasks_dir() -> Path:
    """获取任务目录（从配置文件读取）"""
    config = load_config()
    tasks_dir = BASE_DIR / config.get("tasks_base_dir", "tasks")
    tasks_dir.mkdir(parents=True, exist_ok=True)
    return tasks_dir

# 初始化动画生成器（延迟初始化，避免配置文件不存在时启动失败）
animation_generator: Optional[AnimationGenerator] = None

# 初始化任务管理器和调度器
task_manager: Optional[TaskManager] = None
task_sync_scheduler: Optional[TaskSyncScheduler] = None

def get_task_manager() -> TaskManager:
    """获取任务管理器实例（单例模式）"""
    global task_manager
    if task_manager is None:
        task_manager = TaskManager()
        print("[INFO] 任务管理器初始化成功")
    return task_manager

def get_animation_generator() -> AnimationGenerator:
    """获取动画生成器实例（单例模式）"""
    global animation_generator
    if animation_generator is None:
        try:
            animation_generator = AnimationGenerator("backend/config.json")
            print("[INFO] 动画生成器初始化成功")
        except FileNotFoundError as e:
            print(f"[WARNING] 动画生成器初始化失败: {e}")
            print("[WARNING] 动画生成功能将不可用，请配置 backend/config.json")
            raise HTTPException(
                status_code=503,
                detail="动画生成功能未配置。请创建 backend/config.json 并配置 LS-PrePost 路径"
            )
        except Exception as e:
            print(f"[ERROR] 动画生成器初始化异常: {e}")
            raise HTTPException(status_code=500, detail=f"动画生成器初始化失败: {str(e)}")
    return animation_generator


# ==================== 数据模型 ====================

class SimulationParameters(BaseModel):
    """仿真参数模型（放宽限制，允许更灵活的参数范围）"""
    velocity_z: float = Field(..., description="弹丸初速度 (m/s)", ge=100, le=5000)
    bullet_yield_stress: float = Field(..., description="弹丸屈服强度 (MPa)", ge=100, le=5000)
    target_yield_stress: float = Field(..., description="靶板屈服强度 (MPa)", ge=50, le=3000)
    friction_static: float = Field(..., description="静摩擦系数", ge=0.0, le=1.0)
    friction_dynamic: float = Field(..., description="动摩擦系数", ge=0.0, le=1.0)
    simulation_endtime: float = Field(..., description="仿真终止时间 (µs)", ge=1, le=500)
    enable_postprocess: bool = Field(default=False, description="是否启用后处理（生成GIF动画）")

    @field_validator('friction_dynamic')
    @classmethod
    def validate_friction(cls, v, info):
        """验证动摩擦不大于静摩擦（仅警告，不阻止）"""
        # 不再抛出异常，只在验证API返回警告
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "velocity_z": 1600.0,
                "bullet_yield_stress": 1000.0,
                "target_yield_stress": 800.0,
                "friction_static": 0.25,
                "friction_dynamic": 0.18,
                "simulation_endtime": 30.0,
                "enable_postprocess": False
            }
        }


class GenerationResult(BaseModel):
    """生成结果模型"""
    success: bool
    task_id: Optional[str] = None  # 任务ID（独立模式使用）
    filename: str
    file_path: str
    metadata_path: str
    timestamp: str
    parameters: Dict
    message: str
    warnings: Optional[List[str]] = []  # 警告信息（例如跳过的参数）


class ParameterInfo(BaseModel):
    """参数信息模型"""
    name: str
    name_cn: str
    unit: str
    default: float
    min: float
    max: float
    step: float
    description: str


# ==================== 任务提交数据模型 ====================

class TaskSubmitRequest(BaseModel):
    """任务提交请求模型（平台A集成）"""
    task_id: str = Field(..., min_length=8, max_length=128, description="任务ID")
    params: SimulationParameters = Field(..., description="仿真参数")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "platform_a_task_001",
                "params": {
                    "velocity_z": 1600.0,
                    "bullet_yield_stress": 1000.0,
                    "target_yield_stress": 800.0,
                    "friction_static": 0.25,
                    "friction_dynamic": 0.18,
                    "simulation_endtime": 30.0
                }
            }
        }


class TaskSaveRequest(BaseModel):
    """任务保存请求模型（方案2：平台触发执行模式）"""
    task_id: str = Field(..., min_length=8, max_length=128, description="任务ID（平台A生成的UUID）")
    params: SimulationParameters = Field(..., description="仿真参数")
    enable_postprocess: bool = Field(default=False, description="是否启用后处理（生成GIF动画）")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "params": {
                    "velocity_z": 1600.0,
                    "bullet_yield_stress": 1000.0,
                    "target_yield_stress": 800.0,
                    "friction_static": 0.25,
                    "friction_dynamic": 0.18,
                    "simulation_endtime": 30.0
                },
                "enable_postprocess": True
            }
        }


class TaskExecuteRequest(BaseModel):
    """任务执行请求模型"""
    force: bool = Field(default=False, description="是否强制重新执行已完成/失败任务")


# ==================== 动画生成数据模型 ====================

class AnimationGenerateRequest(BaseModel):
    """动画生成请求模型"""
    d3plot_path: str = Field(..., description="d3plot文件的绝对路径")
    view: str = Field(default="isometric", description="视角: isometric, front, back, top, bottom, left, right")
    fringe_variable: str = Field(default="stress", description="云图变量: stress, strain, displacement, velocity, acceleration, plastic_strain")
    resolution: List[int] = Field(default=[1920, 1080], description="分辨率 [宽, 高]")
    fps: int = Field(default=30, ge=15, le=60, description="帧率")
    output_format: str = Field(default="mp4", description="输出格式: mp4, avi")

    class Config:
        json_schema_extra = {
            "example": {
                "d3plot_path": "D:\\Simulations\\bullet_sim\\d3plot",
                "view": "isometric",
                "fringe_variable": "stress",
                "resolution": [1920, 1080],
                "fps": 30,
                "output_format": "mp4"
            }
        }


class AnimationTaskResponse(BaseModel):
    """动画任务响应模型"""
    task_id: str
    status: str
    d3plot_path: str
    config: Dict
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None
    progress: int

    class Config:
        from_attributes = True


# ==================== API端点 ====================

@app.get("/")
async def root():
    """根路径"""
    return {"message": "LS-DYNA K文件参数化系统 API", "version": "1.0.0"}


@app.get("/api/parameters", response_model=List[ParameterInfo])
async def get_parameters():
    """
    获取所有可配置参数的定义

    返回参数列表，包含名称、单位、范围、默认值等信息
    """
    params = []
    for param_name in ParameterConfig.get_parameter_names():
        config = ParameterConfig.get_parameter(param_name)
        params.append({
            "name": param_name,
            "name_cn": config["name_cn"],
            "unit": config["physical_unit"],
            "default": config["default_physical"],
            "min": config["min_physical"],
            "max": config["max_physical"],
            "step": config["step"],
            "description": config["description"]
        })
    return params


@app.get("/api/parameters/{param_name}/suggestions")
async def get_parameter_suggestions(param_name: str):
    """
    获取参数的推荐预设值

    Args:
        param_name: 参数名称

    Returns:
        推荐值字典 {场景名: 推荐值}
    """
    suggestions = ParameterValidator.get_parameter_suggestions(param_name)
    if not suggestions:
        raise HTTPException(status_code=404, detail=f"参数 '{param_name}' 没有推荐值")
    return suggestions


@app.post("/api/validate")
async def validate_parameters(params: SimulationParameters):
    """
    验证参数集合

    Args:
        params: 仿真参数

    Returns:
        验证结果
    """
    param_dict = {
        "velocity_z": params.velocity_z,
        "bullet_yield_stress": params.bullet_yield_stress,
        "target_yield_stress": params.target_yield_stress,
        "friction_static": params.friction_static,
        "friction_dynamic": params.friction_dynamic,
        "simulation_endtime": params.simulation_endtime
    }

    is_valid, errors = ParameterValidator.validate_parameter_set(param_dict)

    return {
        "valid": is_valid,
        "errors": errors if errors else [],
        "warnings": [err for err in errors if "警告" in err or "提示" in err]
    }


@app.post("/api/generate", response_model=GenerationResult)
async def generate_k_file(params: SimulationParameters):
    """
    生成K文件（独立模式）

    创建独立任务并生成K文件，任务会被保存到数据库但不会同步到平台A

    Args:
        params: 仿真参数

    Returns:
        生成结果，包含文件路径和元数据
    """
    try:
        tm = get_task_manager()

        # 生成独立任务ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_id = f"standalone_{timestamp}_{uuid4().hex[:8]}"

        # 1. 验证参数
        param_dict = {
            "velocity_z": params.velocity_z,
            "bullet_yield_stress": params.bullet_yield_stress,
            "target_yield_stress": params.target_yield_stress,
            "friction_static": params.friction_static,
            "friction_dynamic": params.friction_dynamic,
            "simulation_endtime": params.simulation_endtime
        }

        is_valid, errors = ParameterValidator.validate_parameter_set(param_dict)
        if not is_valid:
            # 只有严重错误才阻止生成（排除警告和提示）
            critical_errors = [e for e in errors if "警告" not in e and "提示" not in e]
            if critical_errors:
                raise HTTPException(status_code=400, detail={
                    "message": "参数验证失败",
                    "errors": critical_errors
                })

        # 2. 提交独立任务（source='standalone'）
        task = tm.submit_task(task_id, param_dict, source='standalone')

        # 3. 创建模板引擎
        template_path = TEMPLATE_DIR / "1.k"
        if not template_path.exists():
            tm.fail_task(task_id, f"模板文件不存在: {template_path}")
            raise HTTPException(status_code=500, detail=f"模板文件不存在: {template_path}")

        engine = KFileEngine(str(template_path))

        # 4. 开始任务
        tm.start_task(task_id)

        # 5. 替换参数（可能有些参数会被跳过）
        replace_results = engine.replace_multiple_parameters(param_dict)

        # 收集警告信息
        warnings = []
        if replace_results["skipped"]:
            for skipped in replace_results["skipped"]:
                warnings.append(
                    f"参数 '{skipped['param_name']}' 无法自动定位，已保持默认值。"
                    f"原因: {skipped.get('reason', 'unknown')}"
                )

        # 6. 生成文件名（使用任务目录结构）
        task_dir = get_tasks_dir() / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        summary = engine.get_parameter_summary()
        filename = f"bullet_sim_{task_id}_{summary}.k"
        output_path = task_dir / filename

        # 7. 生成K文件
        engine.generate(str(output_path), metadata={
            "task_id": task_id,
            "source": "standalone",
            "user_params": param_dict,
            "validation_errors": errors
        })

        # 8. 标记任务完成
        tm.complete_task(task_id, str(output_path))

        # 9. 返回结果
        success_msg = f"成功生成K文件: {filename}"
        if warnings:
            success_msg += f" (注意: {len(warnings)} 个参数被跳过)"

        return GenerationResult(
            success=True,
            task_id=task_id,  # 返回独立任务ID
            filename=filename,
            file_path=str(output_path),
            metadata_path=str(output_path).replace('.k', '_metadata.json'),
            timestamp=timestamp,
            parameters=param_dict,
            message=success_msg,
            warnings=warnings
        )

    except HTTPException:
        raise
    except Exception as e:
        # 记录失败状态
        try:
            if 'task_id' in locals():
                tm = get_task_manager()
                tm.fail_task(task_id, str(e))
        except:
            pass
        raise HTTPException(status_code=500, detail=f"生成K文件失败: {str(e)}")


@app.get("/api/files")
async def list_generated_files():
    """
    列出所有生成的K文件

    Returns:
        文件列表，包含文件名、生成时间、大小等信息
    """
    files = []
    tasks_dir = get_tasks_dir()

    # 遍历任务目录下的所有K文件
    for file_path in tasks_dir.glob("**/*.k"):
        # 读取元数据
        metadata_path = file_path.with_suffix('.k_metadata.json')
        metadata = {}
        if metadata_path.exists():
            import json
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

        files.append({
            "filename": file_path.name,
            "size": file_path.stat().st_size,
            "created": datetime.fromtimestamp(file_path.stat().st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
            "metadata": metadata.get("user_params", {})
        })

    # 按创建时间降序排序
    files.sort(key=lambda x: x["created"], reverse=True)
    return files


@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """
    下载生成的K文件

    Args:
        filename: 文件名

    Returns:
        文件内容
    """
    tasks_dir = get_tasks_dir()
    # 递归搜索（文件现在在 tasks/{task_id}/ 子目录中）
    matches = list(tasks_dir.glob(f"**/{filename}"))
    if not matches:
        raise HTTPException(status_code=404, detail="文件不存在")

    file_path = matches[0]  # 取第一个匹配
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream"
    )


@app.delete("/api/files/{filename}")
async def delete_file(filename: str):
    """
    删除生成的K文件及其元数据

    Args:
        filename: 文件名

    Returns:
        删除结果
    """
    tasks_dir = get_tasks_dir()
    # 递归搜索（文件现在在 tasks/{task_id}/ 子目录中）
    matches = list(tasks_dir.glob(f"**/{filename}"))
    if not matches:
        raise HTTPException(status_code=404, detail="文件不存在")

    file_path = matches[0]
    metadata_path = file_path.with_suffix('.k_metadata.json')

    # 删除K文件
    file_path.unlink()

    # 删除元数据文件（如果存在）
    if metadata_path.exists():
        metadata_path.unlink()

    return {"message": f"成功删除文件: {filename}"}


# ==================== 任务管理API端点（平台A集成）====================

@app.get("/api/task/{task_id}")
async def get_task(task_id: str):
    """
    查询任务详情

    Args:
        task_id: 任务ID

    Returns:
        任务详情或404错误
    """
    # 验证task_id格式
    if not TaskManager.validate_task_id(task_id):
        raise HTTPException(status_code=400, detail=f"无效的task_id格式: {task_id}")

    try:
        tm = get_task_manager()
        task = tm.get_task(task_id)

        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

        # 添加状态名称
        task['status_name'] = TaskManager.get_status_name(task['status'])

        return task

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询任务失败: {str(e)}")


# ==================== 平台触发执行模式API（方案2）====================

@app.post("/api/task/save")
async def save_task(request: TaskSaveRequest):
    """
    保存任务参数（方案2：仅保存不执行）

    用途：用户提交仿真参数，仅保存到数据库，等待平台A触发执行

    Args:
        request: 任务保存请求（包含task_id和params）

    Returns:
        保存结果
    """
    task_id = request.task_id
    params = request.params

    # 验证task_id格式
    if not TaskManager.validate_task_id(task_id):
        raise HTTPException(status_code=400, detail=f"无效的task_id格式: {task_id}")

    try:
        tm = get_task_manager()

        # 检查任务是否已存在
        existing_task = tm.get_task(task_id)
        if existing_task:
            # 任务已存在，检查状态
            status = existing_task['status']
            if status >= 1:  # 排队中/执行中/已完成/失败/中止
                return JSONResponse(
                    status_code=409,
                    content={
                        "success": False,
                        "error": "TASK_EXISTS",
                        "message": "任务已存在且参数已锁定，无法修改",
                        "current_status": status,
                        "current_status_name": TaskManager.get_status_name(status)
                    }
                )
            # status=0 (待执行) 可以更新参数 - 但目前不支持，返回已存在
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "error": "TASK_EXISTS",
                    "message": "任务已存在，参数已保存",
                    "current_status": status,
                    "current_status_name": TaskManager.get_status_name(status)
                }
            )

        # 参数字典
        param_dict = {
            "velocity_z": params.velocity_z,
            "bullet_yield_stress": params.bullet_yield_stress,
            "target_yield_stress": params.target_yield_stress,
            "friction_static": params.friction_static,
            "friction_dynamic": params.friction_dynamic,
            "simulation_endtime": params.simulation_endtime
        }

        # 验证参数
        is_valid, errors = ParameterValidator.validate_parameter_set(param_dict)
        if not is_valid:
            critical_errors = [e for e in errors if "警告" not in e and "提示" not in e]
            if critical_errors:
                raise HTTPException(status_code=400, detail={
                    "success": False,
                    "error": "VALIDATION_ERROR",
                    "message": "参数验证失败",
                    "details": critical_errors
                })

        # 保存任务（状态为0-待执行）
        task = tm.submit_task(task_id, param_dict, source='platform_a', enable_postprocess=request.enable_postprocess)

        return {
            "success": True,
            "task_id": task_id,
            "status": 0,
            "status_name": "待执行",
            "enable_postprocess": request.enable_postprocess,
            "message": "参数已保存，等待平台触发执行",
            "created_at": task.get('created_at')
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存任务失败: {str(e)}")


@app.post("/api/task/{task_id}/execute")
async def execute_task(task_id: str, request: TaskExecuteRequest = None):
    """
    触发任务执行（方案2：平台A调用）

    幂等性设计：
    - status=0（待执行）→ 加入队列，返回status=1
    - status=1（排队中）→ 返回当前状态和队列位置
    - status=2（生成K文件中）→ 返回当前状态和进度
    - status=3（已完成）→ 返回结果
    - status=4（已失败）→ 返回错误信息
    - status=5（已中止）→ 返回错误
    - status=6（LS-DYNA计算中）→ 返回当前状态和进度
    - status=7（后处理中）→ 返回当前状态和进度

    Args:
        task_id: 任务ID
        request: 执行请求（可选，包含force参数）

    Returns:
        执行结果
    """
    # 处理可选的request body
    force = request.force if request else False

    # 验证task_id格式
    if not TaskManager.validate_task_id(task_id):
        raise HTTPException(status_code=400, detail=f"无效的task_id格式: {task_id}")

    try:
        tm = get_task_manager()
        task_queue = get_task_queue()

        if task_queue is None:
            raise HTTPException(status_code=503, detail="任务队列未初始化")

        # 获取任务
        task = tm.get_task(task_id)
        if task is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "TASK_NOT_FOUND",
                    "message": "任务不存在，请先调用 /api/task/save 保存参数"
                }
            )

        status = task['status']

        # 状态机处理（幂等性）
        if status == TaskStatus.PENDING:  # 待执行 → 加入队列
            result = task_queue.enqueue(task_id)
            return {
                "success": True,
                "task_id": task_id,
                "status": TaskStatus.QUEUED,
                "status_name": "排队中",
                "message": "任务已加入执行队列",
                "queue_position": result.get("queue_position"),
                "estimated_wait_seconds": result.get("estimated_wait_seconds")
            }

        elif status == TaskStatus.QUEUED:  # 排队中 → 返回队列位置
            position = task_queue.get_task_position(task_id)
            return {
                "success": True,
                "task_id": task_id,
                "status": TaskStatus.QUEUED,
                "status_name": "排队中",
                "message": "任务已在队列中等待执行",
                "queue_position": position if position else "即将执行"
            }

        elif status == TaskStatus.GENERATING:  # 生成K文件中 → 返回进度
            return {
                "success": True,
                "task_id": task_id,
                "status": TaskStatus.GENERATING,
                "status_name": "生成K文件中",
                "message": "正在生成K文件",
                "progress": task.get("progress", 0),
                "started_at": task.get("start_time")
            }

        elif status == TaskStatus.COMPUTING:  # LS-DYNA计算中 → 返回进度
            queue_status = task_queue.get_status()
            running = queue_status.get("running_task", {})
            return {
                "success": True,
                "task_id": task_id,
                "status": TaskStatus.COMPUTING,
                "status_name": "LS-DYNA计算中",
                "message": "LS-DYNA求解器正在计算",
                "progress": task.get("progress", 30),
                "compute_start_time": task.get("compute_start_time"),
                "elapsed_seconds": running.get("elapsed_seconds") if running else None
            }

        elif status == TaskStatus.POSTPROCESSING:  # 后处理中 → 返回进度
            return {
                "success": True,
                "task_id": task_id,
                "status": TaskStatus.POSTPROCESSING,
                "status_name": "后处理中",
                "message": "LS-PrePost正在生成动画",
                "progress": task.get("progress", 80)
            }

        elif status == TaskStatus.COMPLETED:  # 已完成 → 返回结果
            if force:
                # 强制重新执行：重置状态为0，然后加入队列
                tm.db.update_task_status(task_id, TaskStatus.PENDING)
                result = task_queue.enqueue(task_id)
                return {
                    "success": True,
                    "task_id": task_id,
                    "status": TaskStatus.QUEUED,
                    "status_name": "排队中",
                    "message": "任务已重置并加入执行队列",
                    "queue_position": result.get("queue_position")
                }

            return {
                "success": True,
                "task_id": task_id,
                "status": TaskStatus.COMPLETED,
                "status_name": "已完成",
                "message": "任务已完成",
                "progress": 100,
                "output_file_path": task.get("output_file_path"),
                "gif_path": task.get("gif_path"),
                "d3hsp_path": task.get("d3hsp_path"),
                "completed_at": task.get("end_time")
            }

        elif status == TaskStatus.FAILED:  # 已失败 → 返回错误信息
            if force:
                # 强制重新执行
                tm.db.update_task_status(task_id, TaskStatus.PENDING)
                result = task_queue.enqueue(task_id)
                return {
                    "success": True,
                    "task_id": task_id,
                    "status": TaskStatus.QUEUED,
                    "status_name": "排队中",
                    "message": "任务已重置并加入执行队列",
                    "queue_position": result.get("queue_position")
                }

            return {
                "success": True,
                "task_id": task_id,
                "status": TaskStatus.FAILED,
                "status_name": "已失败",
                "message": "任务执行失败",
                "error_message": task.get("error_message"),
                "error_log_path": task.get("error_log_path"),
                "failed_at": task.get("end_time")
            }

        elif status == TaskStatus.ABORTED:  # 已中止 → 不允许执行
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "INVALID_STATE",
                    "message": "任务已中止，无法执行",
                    "current_status": TaskStatus.ABORTED,
                    "current_status_name": "已中止"
                }
            )

        else:
            raise HTTPException(status_code=500, detail=f"未知任务状态: {status}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"触发执行失败: {str(e)}")


@app.get("/api/queue/status")
async def get_queue_status():
    """
    查询任务队列状态

    Returns:
        队列状态信息
    """
    try:
        task_queue = get_task_queue()
        if task_queue is None:
            raise HTTPException(status_code=503, detail="任务队列未初始化")

        return task_queue.get_status()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询队列状态失败: {str(e)}")


# ==================== 结果文件下载API端点 ====================

@app.get("/api/task/{task_id}/result/gif")
async def download_task_animation(task_id: str):
    """
    下载任务生成的动画文件（支持GIF、AVI等格式）

    Args:
        task_id: 任务ID

    Returns:
        动画文件
    """
    try:
        tm = get_task_manager()
        task = tm.get_task(task_id)

        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

        gif_path = task.get("gif_path")
        if not gif_path or not os.path.exists(gif_path):
            raise HTTPException(
                status_code=404,
                detail="动画文件不存在（任务可能未启用后处理或尚未完成）"
            )

        filename = os.path.basename(gif_path)

        # 根据文件扩展名设置正确的媒体类型
        ext = os.path.splitext(filename)[1].lower()
        media_types = {
            ".gif": "image/gif",
            ".avi": "video/x-msvideo",
            ".mp4": "video/mp4",
            ".mpeg": "video/mpeg",
        }
        media_type = media_types.get(ext, "application/octet-stream")

        return FileResponse(
            path=gif_path,
            filename=filename,
            media_type=media_type
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载动画文件失败: {str(e)}")


@app.get("/api/task/{task_id}/result/d3hsp")
async def download_task_d3hsp(task_id: str):
    """
    下载任务的d3hsp日志文件

    Args:
        task_id: 任务ID

    Returns:
        d3hsp文本文件
    """
    try:
        tm = get_task_manager()
        task = tm.get_task(task_id)

        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

        d3hsp_path = task.get("d3hsp_path")
        if not d3hsp_path or not os.path.exists(d3hsp_path):
            raise HTTPException(
                status_code=404,
                detail="d3hsp文件不存在（任务可能尚未完成计算）"
            )

        filename = os.path.basename(d3hsp_path)
        return FileResponse(
            path=d3hsp_path,
            filename=filename,
            media_type="text/plain"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载d3hsp失败: {str(e)}")


@app.get("/api/task/{task_id}/result/error_log")
async def download_task_error_log(task_id: str):
    """
    下载任务的错误日志文件

    Args:
        task_id: 任务ID

    Returns:
        错误日志文本文件
    """
    try:
        tm = get_task_manager()
        task = tm.get_task(task_id)

        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

        error_log_path = task.get("error_log_path")
        if not error_log_path or not os.path.exists(error_log_path):
            raise HTTPException(
                status_code=404,
                detail="错误日志不存在（任务可能未失败或日志已清理）"
            )

        filename = os.path.basename(error_log_path)
        return FileResponse(
            path=error_log_path,
            filename=filename,
            media_type="text/plain"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载错误日志失败: {str(e)}")


@app.get("/api/task/{task_id}/result/k_file")
async def download_task_k_file(task_id: str):
    """
    下载任务生成的K文件

    Args:
        task_id: 任务ID

    Returns:
        K文件
    """
    try:
        tm = get_task_manager()
        task = tm.get_task(task_id)

        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

        k_file_path = task.get("output_file_path")
        if not k_file_path or not os.path.exists(k_file_path):
            raise HTTPException(
                status_code=404,
                detail="K文件不存在（任务可能尚未完成生成）"
            )

        filename = os.path.basename(k_file_path)
        return FileResponse(
            path=k_file_path,
            filename=filename,
            media_type="application/octet-stream"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载K文件失败: {str(e)}")


@app.post("/api/task/submit")
async def submit_task(request: TaskSubmitRequest):
    """
    提交任务（平台A集成入口）

    工作流程：
    1. 验证task_id
    2. 创建/更新任务记录
    3. 调用平台A的task-insert接口
    4. 生成K文件
    5. 更新任务状态并同步平台A

    Args:
        request: 任务提交请求（包含task_id和params）

    Returns:
        任务执行结果
    """
    task_id = request.task_id
    params = request.params

    # 验证task_id
    if not TaskManager.validate_task_id(task_id):
        raise HTTPException(status_code=400, detail=f"无效的task_id格式: {task_id}")

    try:
        tm = get_task_manager()

        # 参数字典
        param_dict = {
            "velocity_z": params.velocity_z,
            "bullet_yield_stress": params.bullet_yield_stress,
            "target_yield_stress": params.target_yield_stress,
            "friction_static": params.friction_static,
            "friction_dynamic": params.friction_dynamic,
            "simulation_endtime": params.simulation_endtime
        }

        # 1. 提交任务（记录submission_time，source='platform_a'）
        task = tm.submit_task(task_id, param_dict, source='platform_a')

        # 2. 验证参数
        is_valid, errors = ParameterValidator.validate_parameter_set(param_dict)
        if not is_valid:
            critical_errors = [e for e in errors if "警告" not in e and "提示" not in e]
            if critical_errors:
                tm.fail_task(task_id, f"参数验证失败: {'; '.join(critical_errors)}")
                raise HTTPException(status_code=400, detail={
                    "message": "参数验证失败",
                    "errors": critical_errors
                })

        # 3. 开始生成K文件
        tm.start_task(task_id)

        template_path = TEMPLATE_DIR / "1.k"
        if not template_path.exists():
            tm.fail_task(task_id, f"模板文件不存在: {template_path}")
            raise HTTPException(status_code=500, detail=f"模板文件不存在: {template_path}")

        engine = KFileEngine(str(template_path))
        replace_results = engine.replace_multiple_parameters(param_dict)

        # 收集警告
        warnings = []
        if replace_results["skipped"]:
            for skipped in replace_results["skipped"]:
                warnings.append(
                    f"参数 '{skipped['param_name']}' 无法自动定位，已保持默认值。"
                )

        # 4. 生成K文件（在任务专属目录中）
        task_dir = get_tasks_dir() / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary = engine.get_parameter_summary()
        filename = f"bullet_sim_{task_id}_{timestamp}_{summary}.k"
        output_path = task_dir / filename

        engine.generate(str(output_path), metadata={
            "task_id": task_id,
            "user_params": param_dict,
            "validation_errors": errors
        })

        # 5. 标记任务完成
        tm.complete_task(task_id, str(output_path))

        success_msg = f"任务 {task_id} 执行成功，K文件已生成: {filename}"
        if warnings:
            success_msg += f" (注意: {len(warnings)} 个参数被跳过)"

        return {
            "success": True,
            "task_id": task_id,
            "filename": filename,
            "file_path": str(output_path),
            "message": success_msg,
            "warnings": warnings,
            "status": TaskManager.STATUS_COMPLETED
        }

    except HTTPException:
        raise
    except Exception as e:
        # 记录失败状态
        try:
            tm = get_task_manager()
            tm.fail_task(task_id, str(e))
        except:
            pass
        raise HTTPException(status_code=500, detail=f"任务执行失败: {str(e)}")


# ==================== 动画生成API端点 ====================

@app.post("/api/animation/generate", response_model=AnimationTaskResponse)
async def create_animation_task(request: AnimationGenerateRequest):
    """
    创建动画生成任务

    这个API立即返回任务ID，实际渲染在后台异步执行
    前端应该使用 /api/animation/status/{task_id} 轮询任务状态

    Args:
        request: 动画生成请求参数

    Returns:
        任务信息
    """
    try:
        # 获取动画生成器实例
        generator = get_animation_generator()

        # 验证d3plot文件存在
        if not os.path.exists(request.d3plot_path):
            raise HTTPException(
                status_code=400,
                detail=f"d3plot文件不存在: {request.d3plot_path}"
            )

        # 创建AnimationConfig
        config = AnimationConfig(
            view=request.view,
            fringe_variable=request.fringe_variable,
            resolution=tuple(request.resolution),
            fps=request.fps,
            output_format=request.output_format
        )

        # 创建任务
        task = generator.create_task(request.d3plot_path, config)

        # 转换为响应模型
        return AnimationTaskResponse(
            task_id=task.task_id,
            status=task.status,
            d3plot_path=task.d3plot_path,
            config=task.config.dict(),
            output_path=task.output_path,
            error_message=task.error_message,
            created_at=task.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            completed_at=task.completed_at.strftime("%Y-%m-%d %H:%M:%S") if task.completed_at else None,
            progress=task.progress
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建动画任务失败: {str(e)}")


@app.get("/api/animation/status/{task_id}", response_model=AnimationTaskResponse)
async def get_animation_task_status(task_id: str):
    """
    查询动画生成任务状态

    前端应该每2-5秒轮询一次，直到任务完成或失败

    Args:
        task_id: 任务ID

    Returns:
        任务当前状态
    """
    try:
        generator = get_animation_generator()
        task = generator.get_task(task_id)

        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

        return AnimationTaskResponse(
            task_id=task.task_id,
            status=task.status,
            d3plot_path=task.d3plot_path,
            config=task.config.dict(),
            output_path=task.output_path,
            error_message=task.error_message,
            created_at=task.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            completed_at=task.completed_at.strftime("%Y-%m-%d %H:%M:%S") if task.completed_at else None,
            progress=task.progress
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询任务状态失败: {str(e)}")


@app.get("/api/animation/list", response_model=List[AnimationTaskResponse])
async def list_animation_tasks():
    """
    列出所有动画生成任务

    按创建时间倒序排列

    Returns:
        任务列表
    """
    try:
        generator = get_animation_generator()
        tasks = generator.get_all_tasks()

        return [
            AnimationTaskResponse(
                task_id=task.task_id,
                status=task.status,
                d3plot_path=task.d3plot_path,
                config=task.config.dict(),
                output_path=task.output_path,
                error_message=task.error_message,
                created_at=task.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                completed_at=task.completed_at.strftime("%Y-%m-%d %H:%M:%S") if task.completed_at else None,
                progress=task.progress
            )
            for task in tasks
        ]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {str(e)}")


@app.get("/api/animation/download/{task_id}")
async def download_animation(task_id: str):
    """
    下载生成的动画文件

    Args:
        task_id: 任务ID

    Returns:
        MP4视频文件
    """
    try:
        generator = get_animation_generator()
        task = generator.get_task(task_id)

        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

        if task.status != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"任务尚未完成，当前状态: {task.status}"
            )

        if not task.output_path or not os.path.exists(task.output_path):
            raise HTTPException(
                status_code=500,
                detail="动画文件不存在（可能已被删除）"
            )

        filename = os.path.basename(task.output_path)
        return FileResponse(
            path=task.output_path,
            filename=filename,
            media_type="video/mp4"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载动画失败: {str(e)}")


# 挂载静态文件（前端）
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ==================== 启动配置 ====================

if __name__ == "__main__":
    import uvicorn

    frozen = is_frozen()
    mode_text = "打包模式" if frozen else "开发模式"

    print("="*60)
    print(f"LS-DYNA K文件参数化系统 - 启动中... ({mode_text})")
    print("="*60)
    print(f"资源目录: {BUNDLE_DIR}")
    print(f"数据目录: {BASE_DIR}")
    print(f"模板目录: {TEMPLATE_DIR} {'✓' if TEMPLATE_DIR.exists() else '✗ 不存在!'}")
    print(f"前端目录: {FRONTEND_DIR} {'✓' if FRONTEND_DIR.exists() else '✗ 不存在!'}")
    print(f"任务目录: {get_tasks_dir()}")
    print(f"配置文件: {get_backend_dir() / 'config.json'}")
    print("="*60)
    print("访问地址:")
    print("  - Web界面: http://localhost:8000")
    print("  - API文档: http://localhost:8000/docs")
    print("="*60)

    if frozen:
        # 打包模式：直接传 app 对象，禁用 reload
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info"
        )
    else:
        # 开发模式：使用字符串引用，启用热重载
        uvicorn.run(
            "app:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
