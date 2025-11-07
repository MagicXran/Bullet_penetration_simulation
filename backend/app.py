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
