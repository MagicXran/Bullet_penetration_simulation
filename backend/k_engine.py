#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LS-DYNA K文件模板引擎

负责读取K文件模板，替换参数值，生成新的K文件。
核心功能：固定列宽的参数替换，确保格式100%正确。
"""

import os
from typing import Dict, List, Tuple
from datetime import datetime
import json

from column_detector import ColumnDetector
from parameter_config import ParameterConfig


class KFileEngine:
    """K文件模板引擎"""

    def __init__(self, template_path: str):
        """
        初始化模板引擎

        Args:
            template_path: 模板K文件的路径
        """
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"模板文件不存在: {template_path}")

        self.template_path = template_path
        self.lines: List[str] = []
        self.detector = ColumnDetector()
        self.modifications: List[Dict] = []  # 记录所有修改

        # 加载模板
        self._load_template()

    def _load_template(self):
        """
        加载模板文件

        注意：使用UTF-8编码读取，保留原始换行符
        """
        # 尝试不同的编码
        encodings = ['utf-8-sig', 'utf-8', 'latin-1']

        for encoding in encodings:
            try:
                with open(self.template_path, 'r', encoding=encoding) as f:
                    content = f.read()
                    # 统一使用 \n 作为内部行分隔符
                    self.lines = content.replace('\r\n', '\n').replace('\r', '\n').split('\n')
                print(f"成功使用 {encoding} 编码加载模板，共 {len(self.lines)} 行")
                return
            except UnicodeDecodeError:
                continue

        raise ValueError(f"无法使用任何编码读取模板文件: {self.template_path}")

    def replace_parameter(self, param_name: str, new_physical_value: float):
        """
        替换指定参数的值

        Args:
            param_name: 参数名称（如 "velocity_z"）
            new_physical_value: 新的物理值（如 1600.0 m/s）

        Raises:
            ValueError: 参数值超出范围或格式错误
        """
        # 获取参数配置
        param_config = ParameterConfig.get_parameter(param_name)

        # 验证物理值范围
        is_valid, msg = ParameterConfig.validate_physical_value(param_name, new_physical_value)
        if not is_valid:
            raise ValueError(msg)

        # 转换为K文件值
        new_k_value = ParameterConfig.convert_to_k_value(param_name, new_physical_value)

        # 获取行号（转换为0-based index）
        line_index = param_config["line"] - 1

        if line_index >= len(self.lines):
            raise IndexError(f"行号 {param_config['line']} 超出文件范围")

        # 获取原始行
        original_line = self.lines[line_index]

        # 检测列位置（优先使用手动指定的列位置）
        if "column_start" in param_config and "column_end" in param_config:
            # 使用手动指定的列位置（用于同行多个相同默认值的情况）
            col_start = param_config["column_start"]
            col_end = param_config["column_end"]
            print(f"[INFO] Using manually specified column position for '{param_name}': {col_start}-{col_end}")
        else:
            # 自动检测列位置
            old_k_value_str = param_config["format"] % param_config["default_k"]
            col_pos = self.detector.detect_value_position(original_line, old_k_value_str.strip())

            if col_pos is None:
                # 如果找不到默认值，返回警告而不是失败
                warning_msg = (
                    f"WARNING: Cannot locate parameter '{param_name}' at line {param_config['line']}. "
                    f"Looking for default value {old_k_value_str.strip()} but line has: {original_line.strip()[:80]}... "
                    f"This parameter will be SKIPPED."
                )
                print(f"[SKIP] {warning_msg}")

                # Return a warning result instead of raising exception
                return {
                    "status": "skipped",
                    "param_name": param_name,
                    "line": param_config["line"],
                    "reason": "ambiguous_position",
                    "warning": warning_msg
                }

            col_start, col_end = col_pos
        column_width = col_end - col_start

        # 格式化新值
        formatted_new_value = self.detector.format_value_to_width(
            new_k_value,
            column_width,
            param_config["format"]
        )

        # 替换
        new_line = (
            original_line[:col_start] +
            formatted_new_value +
            original_line[col_end:]
        )

        # 更新行
        self.lines[line_index] = new_line

        # 记录修改
        self.modifications.append({
            "param_name": param_name,
            "param_cn": param_config["name_cn"],
            "line": param_config["line"],
            "old_k_value": param_config["default_k"],
            "new_k_value": new_k_value,
            "old_physical": param_config["default_physical"],
            "new_physical": new_physical_value,
            "unit": param_config["physical_unit"],
            "column_range": f"{col_start}-{col_end}"
        })

        # ASCII-safe unit display
        unit_display = param_config["physical_unit"].replace('µ', 'u')

        print(f"[OK] Replace parameter: {param_name} "
              f"{param_config['default_physical']} -> {new_physical_value} {unit_display} "
              f"(K value: {param_config['default_k']} -> {new_k_value:.4f})")

        # Return modification record
        return {
            "status": "success",
            "param_name": param_name,
            "line": param_config["line"],
            "old_physical": param_config["default_physical"],
            "new_physical": new_physical_value,
            "old_k_value": param_config["default_k"],
            "new_k_value": new_k_value
        }

    def replace_multiple_parameters(self, param_dict: Dict[str, float]) -> Dict[str, List]:
        """
        批量替换多个参数

        Args:
            param_dict: {param_name: physical_value} 字典

        Returns:
            {
                "success": [list of successfully replaced params],
                "skipped": [list of skipped params with reasons]
            }

        Example:
            result = engine.replace_multiple_parameters({
                "velocity_z": 1800.0,
                "bullet_yield_stress": 1200.0
            })
        """
        results = {
            "success": [],
            "skipped": []
        }

        for param_name, physical_value in param_dict.items():
            result = self.replace_parameter(param_name, physical_value)
            if result["status"] == "success":
                results["success"].append(result)
            elif result["status"] == "skipped":
                results["skipped"].append(result)

        # Print summary
        if results["skipped"]:
            print(f"\n[SUMMARY] {len(results['success'])} parameters replaced, "
                  f"{len(results['skipped'])} parameters skipped")

        return results

    def generate(self, output_path: str, metadata: Dict = None) -> str:
        """
        生成新的K文件

        Args:
            output_path: 输出文件路径
            metadata: 附加元数据（可选）

        Returns:
            生成文件的完整路径
        """
        # 确保输出目录存在
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # 写入K文件
        # 注意：LS-DYNA (Fortran) 不支持 UTF-8 BOM，必须使用无BOM的UTF-8！
        # 虽然全局指令要求UTF-8-BOM，但这里为了兼容LS-DYNA，使用无BOM编码
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            # 手动添加 CRLF（Windows换行符）
            for line in self.lines:
                f.write(line + '\r\n')

        print(f"[OK] Generated K file: {output_path}")

        # 生成元数据JSON文件
        if metadata or self.modifications:
            metadata_path = output_path.replace('.k', '_metadata.json')
            self._generate_metadata(metadata_path, metadata)
            print(f"[OK] Generated metadata: {metadata_path}")

        return output_path

    def _generate_metadata(self, metadata_path: str, extra_metadata: Dict = None):
        """
        生成参数修改记录的元数据JSON文件

        Args:
            metadata_path: 元数据文件路径
            extra_metadata: 额外的元数据
        """
        metadata = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "template_file": os.path.basename(self.template_path),
            "modifications": self.modifications,
            "total_lines": len(self.lines)
        }

        if extra_metadata:
            metadata.update(extra_metadata)

        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def get_parameter_summary(self) -> str:
        """
        获取参数修改摘要（用于文件命名等）

        Returns:
            摘要字符串，如 "v1800_by1200_ty800"
        """
        summary_parts = []
        for mod in self.modifications:
            param_name = mod["param_name"]
            value = mod["new_physical"]

            # 生成简短标识
            if "velocity" in param_name:
                summary_parts.append(f"v{int(value)}")
            elif "bullet" in param_name and "yield" in param_name:
                summary_parts.append(f"by{int(value)}")
            elif "target" in param_name and "yield" in param_name:
                summary_parts.append(f"ty{int(value)}")
            elif "friction_static" in param_name:
                summary_parts.append(f"fs{value:.2f}")
            elif "friction_dynamic" in param_name:
                summary_parts.append(f"fd{value:.2f}")
            elif "endtime" in param_name:
                summary_parts.append(f"t{int(value)}")

        return "_".join(summary_parts) if summary_parts else "default"

    def reset(self):
        """重置引擎，重新加载模板"""
        self.modifications = []
        self._load_template()


# 单元测试
if __name__ == "__main__":
    print("K文件模板引擎测试：\n")

    # 创建引擎实例
    template_path = "../templates/1.k"
    if not os.path.exists(template_path):
        print(f"警告：模板文件不存在: {template_path}")
        print("请确保templates/1.k文件存在")
    else:
        engine = KFileEngine(template_path)

        print("1. 替换单个参数测试：")
        try:
            engine.replace_parameter("velocity_z", 1800.0)
        except Exception as e:
            print(f"   错误: {e}")

        print("\n2. 批量替换测试：")
        try:
            engine.replace_multiple_parameters({
                "bullet_yield_stress": 1200.0,
                "target_yield_stress": 600.0
            })
        except Exception as e:
            print(f"   错误: {e}")

        print("\n3. 生成文件测试：")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary = engine.get_parameter_summary()
        output_path = f"../generated/bullet_sim_{timestamp}_{summary}.k"

        try:
            engine.generate(output_path, metadata={"test": True})
            print(f"   成功生成: {output_path}")
        except Exception as e:
            print(f"   错误: {e}")
