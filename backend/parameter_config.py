#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LS-DYNA K文件参数配置

定义可参数化的6个核心参数及其元数据
"""

from typing import Dict, Any, Callable
from unit_converter import UnitConverter


class ParameterConfig:
    """参数配置定义"""

    # 6个核心参数的完整定义
    PARAMETERS: Dict[str, Dict[str, Any]] = {
        "velocity_z": {
            "name_cn": "弹丸初速度",
            "name_en": "Bullet Velocity",
            "line": 239,  # K文件中的行号
            "physical_unit": "m/s",
            "k_unit": "10 km/s",
            "conversion_to_k": UnitConverter.velocity_to_k,
            "conversion_from_k": UnitConverter.k_to_velocity,
            "default_physical": 1600.0,  # 默认物理值
            "default_k": 0.16,  # 默认K文件值
            "min_physical": 500.0,  # 最小物理值
            "max_physical": 3000.0,  # 最大物理值
            "step": 50.0,  # 推荐步长
            "format": "%10.2f",  # 格式化字符串
            "description": "控制弹丸撞击速度，是穿透性能的最关键参数。低速(500-1000)用于抗冲击研究，中速(1000-2000)为典型穿甲弹，高速(2000-3000)为超高速冲击",
            "column_hint": "col 30-40 (approximate)"  # 列位置提示
        },

        "bullet_yield_stress": {
            "name_cn": "弹丸屈服强度",
            "name_en": "Bullet Yield Stress",
            "line": 211,
            "physical_unit": "MPa",
            "k_unit": "0.01 GPa",
            "conversion_to_k": UnitConverter.stress_mpa_to_k,
            "conversion_from_k": UnitConverter.k_to_stress_mpa,
            "default_physical": 1000.0,
            "default_k": 0.01,  # Correct: 1000 MPa → K value 0.01
            "min_physical": 500.0,
            "max_physical": 2000.0,
            "step": 100.0,
            "format": "%10.5f",  # Need precision for small values like 0.012
            "description": "决定弹丸是否变形或破碎。普通钢(500-800)易变形，硬化钢(1000-1500)保持形状，特种钢(1500-2000)穿甲能力强",
            "column_hint": "col 50-60 (approximate)"
        },

        "target_yield_stress": {
            "name_cn": "靶板屈服强度",
            "name_en": "Target Yield Stress",
            "line": 216,
            "physical_unit": "MPa",
            "k_unit": "0.01 GPa",
            "conversion_to_k": UnitConverter.stress_mpa_to_k,
            "conversion_from_k": UnitConverter.k_to_stress_mpa,
            "default_physical": 800.0,
            "default_k": 0.008,  # Correct: 800 MPa → K value 0.008
            "min_physical": 200.0,
            "max_physical": 1200.0,
            "step": 100.0,
            "format": "%10.5f",  # Need precision for small values
            "description": "决定靶板抗穿透能力。软钢(200-400)易穿透，中碳钢(400-700)中等防护，装甲钢(800-1200)高防护",
            "column_hint": "col 50-60 (approximate)"
        },

        "friction_static": {
            "name_cn": "静摩擦系数",
            "name_en": "Static Friction Coefficient",
            "line": 192,
            "physical_unit": "-",  # 无量纲
            "k_unit": "-",
            "conversion_to_k": lambda x: x,  # 无转换
            "conversion_from_k": lambda x: x,
            "default_physical": 0.0,
            "default_k": 0.0,
            "min_physical": 0.0,
            "max_physical": 0.8,
            "step": 0.05,
            "format": "%10.2f",
            "description": "影响接触界面的能量耗散。无摩擦(0.0)理想化情况，钢-钢(0.15-0.3)典型值，粗糙表面(0.5-0.8)高摩擦",
            # FIXED: 手动指定列位置以避免同行多个相同默认值的歧义
            "column_start": 0,
            "column_end": 10
        },

        "friction_dynamic": {
            "name_cn": "动摩擦系数",
            "name_en": "Dynamic Friction Coefficient",
            "line": 192,  # 与静摩擦同一行，不同列
            "physical_unit": "-",
            "k_unit": "-",
            "conversion_to_k": lambda x: x,
            "conversion_from_k": lambda x: x,
            "default_physical": 0.0,
            "default_k": 0.0,
            "min_physical": 0.0,
            "max_physical": 0.6,
            "step": 0.05,
            "format": "%10.2f",
            "description": "滑动阶段的摩擦力，通常为静摩擦的60-80%。影响弹丸轨迹偏转和能量耗散速率",
            # FIXED: 手动指定列位置以避免同行多个相同默认值的歧义
            "column_start": 10,
            "column_end": 20
        },

        "simulation_endtime": {
            "name_cn": "仿真终止时间",
            "name_en": "Simulation End Time",
            "line": 28,
            "physical_unit": "µs",
            "k_unit": "0.1 µs",
            "conversion_to_k": UnitConverter.time_us_to_k,
            "conversion_from_k": UnitConverter.k_to_time_us,
            "default_physical": 30.0,
            "default_k": 300.0,
            "min_physical": 10.0,
            "max_physical": 100.0,
            "step": 5.0,
            "format": "%10.1f",
            "description": "控制仿真持续时间。低速冲击(50-100µs)查看长时间响应，高速穿透(10-30µs)关注瞬态过程。时间越长计算成本越高",
            "column_hint": "col 10-20 (approximate)"
        }
    }

    @classmethod
    def get_parameter(cls, param_name: str) -> Dict[str, Any]:
        """
        获取指定参数的配置

        Args:
            param_name: 参数名称

        Returns:
            参数配置字典

        Raises:
            KeyError: 参数名称不存在
        """
        if param_name not in cls.PARAMETERS:
            raise KeyError(f"参数 '{param_name}' 不存在。可用参数: {list(cls.PARAMETERS.keys())}")
        return cls.PARAMETERS[param_name]

    @classmethod
    def get_all_parameters(cls) -> Dict[str, Dict[str, Any]]:
        """获取所有参数配置"""
        return cls.PARAMETERS

    @classmethod
    def convert_to_k_value(cls, param_name: str, physical_value: float) -> float:
        """
        将物理值转换为K文件值

        Args:
            param_name: 参数名称
            physical_value: 物理值

        Returns:
            K文件值
        """
        param = cls.get_parameter(param_name)
        converter = param["conversion_to_k"]
        return converter(physical_value)

    @classmethod
    def convert_to_physical_value(cls, param_name: str, k_value: float) -> float:
        """
        将K文件值转换为物理值

        Args:
            param_name: 参数名称
            k_value: K文件值

        Returns:
            物理值
        """
        param = cls.get_parameter(param_name)
        converter = param["conversion_from_k"]
        return converter(k_value)

    @classmethod
    def get_parameter_names(cls) -> list:
        """获取所有参数名称列表"""
        return list(cls.PARAMETERS.keys())

    @classmethod
    def validate_physical_value(cls, param_name: str, value: float) -> tuple:
        """
        验证物理值是否在合理范围内

        Args:
            param_name: 参数名称
            value: 物理值

        Returns:
            (is_valid, message) 元组
        """
        param = cls.get_parameter(param_name)
        min_val = param["min_physical"]
        max_val = param["max_physical"]

        if value < min_val:
            return False, f"{param['name_cn']}({value} {param['physical_unit']})小于最小值{min_val}"
        if value > max_val:
            return False, f"{param['name_cn']}({value} {param['physical_unit']})大于最大值{max_val}"

        return True, "OK"


# 单元测试
if __name__ == "__main__":
    print("参数配置测试：\n")

    # 测试1：获取参数
    velocity_config = ParameterConfig.get_parameter("velocity_z")
    print(f"1. 弹丸初速度配置：")
    print(f"   中文名：{velocity_config['name_cn']}")
    print(f"   默认值：{velocity_config['default_physical']} {velocity_config['physical_unit']}")
    print(f"   范围：{velocity_config['min_physical']}-{velocity_config['max_physical']}")

    # 测试2：单位转换
    print(f"\n2. 单位转换测试：")
    k_val = ParameterConfig.convert_to_k_value("velocity_z", 1600.0)
    print(f"   1600 m/s → K值: {k_val}")
    phys_val = ParameterConfig.convert_to_physical_value("velocity_z", 0.16)
    print(f"   K值 0.16 → {phys_val} m/s")

    # 测试3：验证
    print(f"\n3. 参数验证测试：")
    is_valid, msg = ParameterConfig.validate_physical_value("velocity_z", 1600.0)
    print(f"   1600 m/s: {msg}")
    is_valid, msg = ParameterConfig.validate_physical_value("velocity_z", 5000.0)
    print(f"   5000 m/s: {msg}")

    # 测试4：列出所有参数
    print(f"\n4. 所有参数：")
    for name in ParameterConfig.get_parameter_names():
        param = ParameterConfig.get_parameter(name)
        print(f"   - {param['name_cn']} ({param['physical_unit']})")
