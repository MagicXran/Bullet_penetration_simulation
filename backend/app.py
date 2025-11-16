#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LS-DYNA K文件参数化系统 - FastAPI后端

提供RESTful API接口，处理参数验证、K文件生成等功能
"""

import os
import sys
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, validator

# 添加backend目录到Python路径
sys.path.insert(0, os.path.dirname(__file__))

from parameter_config import ParameterConfig
from validators import ParameterValidator
from k_engine import KFileEngine
from animation_generator import AnimationGenerator
from animation_config import AnimationConfig, AnimationTask
from task_manager import TaskManager
from platform_sync import PlatformSyncClient
from task_sync_scheduler import TaskSyncScheduler

# 创建FastAPI应用
app = FastAPI(
    title="LS-DYNA K文件参数化系统",
    description="子弹穿透仿真参数化生成系统",
    version="1.0.0"
)

# CORS配置（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路径配置
BASE_DIR = Path(__file__).parent.parent
TEMPLATE_DIR = BASE_DIR / "templates"
GENERATED_DIR = BASE_DIR / "generated"
FRONTEND_DIR = BASE_DIR / "frontend"

# 确保目录存在
GENERATED_DIR.mkdir(exist_ok=True)

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


# ==================== 应用生命周期事件 ====================

@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    global task_sync_scheduler
    print("[INFO] 应用启动中...")

    # 启动任务同步调度器
    try:
        task_sync_scheduler = TaskSyncScheduler()
        task_sync_scheduler.start()
    except Exception as e:
        print(f"[WARNING] 任务同步调度器启动失败: {e}")
        print("[WARNING] 平台A集成功能将不可用")

    print("[INFO] 应用启动完成")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时执行"""
    global task_sync_scheduler
    print("[INFO] 应用关闭中...")

    # 关闭任务同步调度器
    if task_sync_scheduler:
        task_sync_scheduler.shutdown()

    print("[INFO] 应用已关闭")


# ==================== 数据模型 ====================

class SimulationParameters(BaseModel):
    """仿真参数模型"""
    velocity_z: float = Field(..., description="弹丸初速度 (m/s)", ge=500, le=3000)
    bullet_yield_stress: float = Field(..., description="弹丸屈服强度 (MPa)", ge=500, le=2000)
    target_yield_stress: float = Field(..., description="靶板屈服强度 (MPa)", ge=200, le=1200)
    friction_static: float = Field(..., description="静摩擦系数", ge=0.0, le=0.8)
    friction_dynamic: float = Field(..., description="动摩擦系数", ge=0.0, le=0.6)
    simulation_endtime: float = Field(..., description="仿真终止时间 (µs)", ge=10, le=100)

    @validator('friction_dynamic')
    def validate_friction(cls, v, values):
        """验证动摩擦不大于静摩擦"""
        if 'friction_static' in values and v > values['friction_static']:
            raise ValueError('动摩擦系数不应大于静摩擦系数')
        return v

    class Config:
        schema_extra = {
            "example": {
                "velocity_z": 1600.0,
                "bullet_yield_stress": 1000.0,
                "target_yield_stress": 800.0,
                "friction_static": 0.25,
                "friction_dynamic": 0.18,
                "simulation_endtime": 30.0
            }
        }


class GenerationResult(BaseModel):
    """生成结果模型"""
    success: bool
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
        schema_extra = {
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
    生成K文件

    Args:
        params: 仿真参数

    Returns:
        生成结果，包含文件路径和元数据
    """
    try:
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

        # 2. 创建模板引擎
        template_path = TEMPLATE_DIR / "1.k"
        if not template_path.exists():
            raise HTTPException(status_code=500, detail=f"模板文件不存在: {template_path}")

        engine = KFileEngine(str(template_path))

        # 3. 替换参数（可能有些参数会被跳过）
        replace_results = engine.replace_multiple_parameters(param_dict)

        # 收集警告信息
        warnings = []
        if replace_results["skipped"]:
            for skipped in replace_results["skipped"]:
                warnings.append(
                    f"参数 '{skipped['param_name']}' 无法自动定位，已保持默认值。"
                    f"原因: {skipped.get('reason', 'unknown')}"
                )

        # 4. 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary = engine.get_parameter_summary()
        filename = f"bullet_sim_{timestamp}_{summary}.k"
        output_path = GENERATED_DIR / filename

        # 5. 生成K文件
        engine.generate(str(output_path), metadata={
            "user_params": param_dict,
            "validation_errors": errors
        })

        # 6. 返回结果
        success_msg = f"成功生成K文件: {filename}"
        if warnings:
            success_msg += f" (注意: {len(warnings)} 个参数被跳过)"

        return GenerationResult(
            success=True,
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
        raise HTTPException(status_code=500, detail=f"生成K文件失败: {str(e)}")


@app.get("/api/files")
async def list_generated_files():
    """
    列出所有生成的K文件

    Returns:
        文件列表，包含文件名、生成时间、大小等信息
    """
    files = []
    for file_path in GENERATED_DIR.glob("*.k"):
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
    file_path = GENERATED_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

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
    file_path = GENERATED_DIR / filename
    metadata_path = file_path.with_suffix('.k_metadata.json')

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

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


@app.post("/api/task/submit")
async def submit_task(
    task_id: str = Field(..., description="任务ID"),
    params: SimulationParameters = None
):
    """
    提交任务（平台A集成入口）

    工作流程：
    1. 验证task_id
    2. 创建/更新任务记录
    3. 调用平台A的task-insert接口
    4. 生成K文件
    5. 更新任务状态并同步平台A

    Args:
        task_id: 任务ID（由平台A传递）
        params: 仿真参数

    Returns:
        任务执行结果
    """
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

        # 1. 提交任务（记录submission_time）
        task = tm.submit_task(task_id, param_dict)

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

        # 4. 生成K文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary = engine.get_parameter_summary()
        filename = f"bullet_sim_{task_id}_{timestamp}_{summary}.k"
        output_path = GENERATED_DIR / filename

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

    print("="*60)
    print("LS-DYNA K文件参数化系统 - 启动中...")
    print("="*60)
    print(f"模板目录: {TEMPLATE_DIR}")
    print(f"生成目录: {GENERATED_DIR}")
    print(f"前端目录: {FRONTEND_DIR}")
    print("="*60)
    print("访问地址:")
    print("  - Web界面: http://localhost:8000")
    print("  - API文档: http://localhost:8000/docs")
    print("="*60)

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # 开发模式自动重载
        log_level="info"
    )
