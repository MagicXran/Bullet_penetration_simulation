#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
参数验证器

提供参数合理性验证、物理约束检查等功能
"""

from typing import Dict, Tuple, List
from parameter_config import ParameterConfig


class ParameterValidator:
    """参数验证器"""

    @staticmethod
    def validate_single_parameter(param_name: str, value: float) -> Tuple[bool, str]:
        """
        验证单个参数

        Args:
            param_name: 参数名称
            value: 参数值（物理单位）

        Returns:
            (is_valid, message) 元组
        """
        try:
            # 基础范围验证
            is_valid, msg = ParameterConfig.validate_physical_value(param_name, value)
            if not is_valid:
                return False, msg

            # 额外的物理合理性检查
            return ParameterValidator._check_physical_reasonableness(param_name, value)

        except KeyError as e:
            return False, f"未知参数: {param_name}"
        except Exception as e:
            return False, f"验证错误: {str(e)}"

    @staticmethod
    def _check_physical_reasonableness(param_name: str, value: float) -> Tuple[bool, str]:
        """
        检查物理合理性

        Args:
            param_name: 参数名称
            value: 参数值

        Returns:
            (is_valid, message) 元组
        """
        # 特定参数的物理约束检查

        if param_name == "friction_dynamic":
            # 动摩擦系数通常小于或等于静摩擦系数
            # 注意：这里我们无法访问其他参数，所以只做基本检查
            if value < 0:
                return False, "动摩擦系数不能为负"
            if value > 1.0:
                return False, "动摩擦系数通常不超过1.0（警告：可能不合理）"

        elif param_name == "friction_static":
            if value < 0:
                return False, "静摩擦系数不能为负"
            if value > 1.0:
                return False, "静摩擦系数通常不超过1.0（警告：可能不合理）"

        elif "yield_stress" in param_name:
            # 屈服强度检查
            if value <= 0:
                return False, "屈服强度必须为正值"

        elif param_name == "velocity_z":
            # 速度检查
            if value <= 0:
                return False, "速度必须为正值"
            if value > 10000:
                return False, "速度超过10000 m/s（超高速，可能导致数值不稳定）"

        elif param_name == "simulation_endtime":
            # 时间检查
            if value <= 0:
                return False, "仿真时间必须为正值"

        return True, "OK"

    @staticmethod
    def validate_parameter_set(params: Dict[str, float]) -> Tuple[bool, List[str]]:
        """
        验证一组参数，包括参数间的相互约束

        Args:
            params: {param_name: value} 字典

        Returns:
            (is_valid, error_messages) 元组
        """
        errors = []

        # 1. 逐个验证参数
        for param_name, value in params.items():
            is_valid, msg = ParameterValidator.validate_single_parameter(param_name, value)
            if not is_valid:
                errors.append(msg)

        # 2. 检查参数间的约束关系
        cross_validation_errors = ParameterValidator._cross_validate_parameters(params)
        errors.extend(cross_validation_errors)

        return (len(errors) == 0, errors)

    @staticmethod
    def _cross_validate_parameters(params: Dict[str, float]) -> List[str]:
        """
        交叉验证参数间的约束关系

        Args:
            params: 参数字典

        Returns:
            错误信息列表
        """
        errors = []

        # 检查1：动摩擦应该小于等于静摩擦
        if "friction_static" in params and "friction_dynamic" in params:
            fs = params["friction_static"]
            fd = params["friction_dynamic"]
            if fd > fs:
                errors.append(
                    f"动摩擦系数({fd})不应大于静摩擦系数({fs})。"
                    f"建议：动摩擦 = 静摩擦 × 0.6-0.8"
                )

        # 检查2：弹丸和靶板屈服强度的合理性
        if "bullet_yield_stress" in params and "target_yield_stress" in params:
            bullet_yield = params["bullet_yield_stress"]
            target_yield = params["target_yield_stress"]

            # 如果弹丸屈服强度远小于靶板，可能无法穿透
            if bullet_yield < target_yield * 0.5:
                errors.append(
                    f"警告：弹丸屈服强度({bullet_yield} MPa)远小于靶板({target_yield} MPa)，"
                    f"可能导致弹丸严重变形或破碎"
                )

        # 检查3：高速冲击需要较短的仿真时间
        if "velocity_z" in params and "simulation_endtime" in params:
            velocity = params["velocity_z"]
            endtime = params["simulation_endtime"]

            # 高速冲击（>2000 m/s）通常在很短时间内完成
            if velocity > 2000 and endtime > 50:
                errors.append(
                    f"提示：高速冲击({velocity} m/s)通常在50µs内完成，"
                    f"当前设置{endtime}µs可能过长"
                )

        return errors

    @staticmethod
    def get_parameter_suggestions(param_name: str) -> Dict[str, float]:
        """
        获取参数的推荐预设值

        Args:
            param_name: 参数名称

        Returns:
            {scenario_name: recommended_value} 字典
        """
        suggestions = {
            "velocity_z": {
                "低速冲击": 800.0,
                "中速穿甲": 1600.0,
                "高速穿甲": 2500.0,
                "超高速": 3000.0
            },
            "bullet_yield_stress": {
                "软钢弹丸": 500.0,
                "普通钢弹丸": 1000.0,
                "硬化钢弹丸": 1500.0,
                "特种钢弹丸": 2000.0
            },
            "target_yield_stress": {
                "软钢靶板": 300.0,
                "中碳钢靶板": 600.0,
                "装甲钢靶板": 1000.0,
                "高强度装甲": 1200.0
            },
            "friction_static": {
                "无摩擦（理想）": 0.0,
                "钢-钢干摩擦": 0.25,
                "粗糙表面": 0.5
            },
            "friction_dynamic": {
                "无摩擦（理想）": 0.0,
                "钢-钢滑动": 0.18,
                "粗糙表面滑动": 0.4
            },
            "simulation_endtime": {
                "快速穿透": 20.0,
                "标准仿真": 30.0,
                "长时间响应": 60.0
            }
        }

        return suggestions.get(param_name, {})


# 单元测试
if __name__ == "__main__":
    print("参数验证器测试：\n")

    # 测试1：单个参数验证
    print("1. 单个参数验证：")
    is_valid, msg = ParameterValidator.validate_single_parameter("velocity_z", 1600.0)
    print(f"   velocity_z = 1600.0: {msg}")

    is_valid, msg = ParameterValidator.validate_single_parameter("velocity_z", 5000.0)
    print(f"   velocity_z = 5000.0: {msg}")

    is_valid, msg = ParameterValidator.validate_single_parameter("velocity_z", -100.0)
    print(f"   velocity_z = -100.0: {msg}")

    # 测试2：参数集验证
    print("\n2. 参数集验证：")
    params_good = {
        "velocity_z": 1600.0,
        "bullet_yield_stress": 1000.0,
        "target_yield_stress": 800.0,
        "friction_static": 0.3,
        "friction_dynamic": 0.2
    }
    is_valid, errors = ParameterValidator.validate_parameter_set(params_good)
    print(f"   良好参数集: {'通过' if is_valid else '失败'}")
    if errors:
        for err in errors:
            print(f"     - {err}")

    # 测试3：违反约束的参数集
    print("\n3. 违反约束的参数集：")
    params_bad = {
        "velocity_z": 1600.0,
        "bullet_yield_stress": 300.0,  # 弹丸太软
        "target_yield_stress": 1000.0,  # 靶板很硬
        "friction_static": 0.2,
        "friction_dynamic": 0.5  # 动摩擦大于静摩擦！
    }
    is_valid, errors = ParameterValidator.validate_parameter_set(params_bad)
    print(f"   问题参数集: {'通过' if is_valid else '失败'}")
    if errors:
        for err in errors:
            print(f"     - {err}")

    # 测试4：获取推荐值
    print("\n4. 参数推荐值：")
    suggestions = ParameterValidator.get_parameter_suggestions("velocity_z")
    print("   velocity_z 推荐值：")
    for scenario, value in suggestions.items():
        print(f"     - {scenario}: {value} m/s")
