"""
LS-PrePost动画生成配置模块

数据模型：
- AnimationConfig: 动画生成参数
- AnimationTask: 异步任务状态管理

遵循原则：
1. 数据结构优先（Linus: "Bad programmers worry about code. Good programmers worry about data structures."）
2. 状态机清晰（只有4个状态，无特殊情况）
3. 类型安全（使用Pydantic验证）
"""

from pydantic import BaseModel, Field, validator
from typing import Literal, Optional, Tuple
from datetime import datetime
from enum import Enum
import uuid


class ViewType(str, Enum):
    """视角类型枚举"""
    ISOMETRIC = "isometric"
    FRONT = "front"
    BACK = "back"
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"


class FringeVariable(str, Enum):
    """云图变量类型枚举"""
    STRESS = "stress"              # 应力
    STRAIN = "strain"              # 应变
    DISPLACEMENT = "displacement"  # 位移
    VELOCITY = "velocity"          # 速度
    ACCELERATION = "acceleration"  # 加速度
    PLASTIC_STRAIN = "plastic_strain"  # 塑性应变


class TaskStatus(str, Enum):
    """任务状态枚举 - 简单的4状态机"""
    PENDING = "pending"        # 等待处理
    PROCESSING = "processing"  # 正在处理
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败


class AnimationConfig(BaseModel):
    """动画生成配置参数

    这个数据结构设计原则：
    - 所有参数都有合理的默认值
    - 类型明确，易于验证
    - 没有歧义和特殊情况
    """

    # 视角设置
    view: ViewType = Field(
        default=ViewType.ISOMETRIC,
        description="相机视角"
    )

    # 云图变量
    fringe_variable: FringeVariable = Field(
        default=FringeVariable.STRESS,
        description="云图显示的物理量"
    )

    # 视频参数
    resolution: Tuple[int, int] = Field(
        default=(1920, 1080),
        description="视频分辨率（宽x高）"
    )

    # 帧范围（替代fps参数）
    start_frame: int = Field(
        default=1,
        ge=1,
        description="起始帧号（通常从1开始）"
    )

    end_frame: Optional[int] = Field(
        default=None,
        description="结束帧号（None表示自动检测总帧数）"
    )

    # 显示选项
    show_all_parts: bool = Field(
        default=True,
        description="显示所有部件（pall命令）"
    )

    show_legend: bool = Field(
        default=True,
        description="显示图例（showlegend命令）"
    )

    show_triad: bool = Field(
        default=True,
        description="显示坐标轴（showtriad命令）"
    )

    # 输出格式（LS-PrePost 4.8支持：GIF, AVI, MPEG）
    output_format: Literal["gif", "avi", "mpeg"] = Field(
        default="gif",
        description="输出动画格式（LS-PrePost 4.8不支持MP4）"
    )

    @validator("resolution")
    def validate_resolution(cls, v):
        """验证分辨率合理性"""
        width, height = v
        if width < 640 or height < 480:
            raise ValueError("分辨率太小，最小640x480")
        if width > 3840 or height > 2160:
            raise ValueError("分辨率太大，最大3840x2160 (4K)")
        return v

    @validator("end_frame")
    def validate_end_frame(cls, v, values):
        """验证结束帧合理性"""
        if v is not None:
            start_frame = values.get("start_frame", 1)
            if v <= start_frame:
                raise ValueError(f"结束帧({v})必须大于起始帧({start_frame})")
        return v


class AnimationTask(BaseModel):
    """动画生成任务 - 状态机模型

    状态转换规则（无特殊情况）：
    pending → processing → completed
    pending → processing → failed

    设计原则：
    1. 状态只能单向转换（pending→processing不可逆）
    2. 所有状态都是终止状态或过渡状态，没有歧义
    3. 错误信息只在failed状态存在
    """

    # 任务标识
    task_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="任务唯一ID"
    )

    # 状态
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        description="任务当前状态"
    )

    # 输入
    d3plot_path: str = Field(
        ...,
        description="d3plot文件的绝对路径"
    )

    config: AnimationConfig = Field(
        default_factory=AnimationConfig,
        description="动画生成配置"
    )

    # 输出
    output_path: Optional[str] = Field(
        default=None,
        description="生成的MP4文件路径（完成后填充）"
    )

    # 错误信息（仅在failed状态有值）
    error_message: Optional[str] = Field(
        default=None,
        description="错误信息（仅失败时存在）"
    )

    # 时间戳
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="任务创建时间"
    )

    completed_at: Optional[datetime] = Field(
        default=None,
        description="任务完成时间"
    )

    # 进度（可选，初期可以不实现）
    progress: int = Field(
        default=0,
        ge=0,
        le=100,
        description="任务进度 0-100%"
    )

    class Config:
        """Pydantic配置"""
        use_enum_values = True  # 自动转换枚举为字符串

    def mark_processing(self):
        """标记为处理中"""
        if self.status != TaskStatus.PENDING:
            raise ValueError(f"只能从pending状态转换到processing，当前状态: {self.status}")
        self.status = TaskStatus.PROCESSING

    def mark_completed(self, output_path: str):
        """标记为已完成"""
        if self.status != TaskStatus.PROCESSING:
            raise ValueError(f"只能从processing状态转换到completed，当前状态: {self.status}")
        self.status = TaskStatus.COMPLETED
        self.output_path = output_path
        self.completed_at = datetime.now()
        self.progress = 100

    def mark_failed(self, error_message: str):
        """标记为失败"""
        if self.status != TaskStatus.PROCESSING:
            raise ValueError(f"只能从processing状态转换到failed，当前状态: {self.status}")
        self.status = TaskStatus.FAILED
        self.error_message = error_message
        self.completed_at = datetime.now()


# 云图变量到LS-PrePost命令的映射
FRINGE_VARIABLE_MAPPING = {
    FringeVariable.STRESS: {"component": 1, "variable": 1},  # Effective stress
    FringeVariable.STRAIN: {"component": 1, "variable": 2},  # Effective strain
    FringeVariable.DISPLACEMENT: {"component": 6, "variable": 1},  # Displacement magnitude
    FringeVariable.VELOCITY: {"component": 7, "variable": 1},  # Velocity magnitude
    FringeVariable.ACCELERATION: {"component": 8, "variable": 1},  # Acceleration magnitude
    FringeVariable.PLASTIC_STRAIN: {"component": 1, "variable": 3},  # Plastic strain
}


# 视角到LS-PrePost命令的映射（LS-PrePost 4.8使用小写命令）
VIEW_MAPPING = {
    ViewType.ISOMETRIC: "isometric",
    ViewType.FRONT: "front",
    ViewType.BACK: "back",
    ViewType.TOP: "top",
    ViewType.BOTTOM: "bottom",
    ViewType.LEFT: "left",
    ViewType.RIGHT: "right",
}
