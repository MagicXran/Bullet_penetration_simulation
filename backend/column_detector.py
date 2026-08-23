#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LS-DYNA K文件列宽自动检测器

K文件使用固定列宽格式（Fortran风格），每个数值字段占据固定的列范围。
此模块负责自动检测参数在行中的精确列位置，确保替换时不破坏格式。
"""

import re
from typing import Tuple, Optional


class ColumnDetector:
    """K文件参数列宽自动检测器"""

    # LS-DYNA 标准列宽（通常为10列的倍数）
    STANDARD_WIDTHS = [5, 8, 10, 15, 20]

    def __init__(self):
        """初始化检测器"""
        self.debug = False  # 调试模式

    def detect_value_position(self, line: str, target_value: str) -> Optional[Tuple[int, int]]:
        """
        检测目标数值在行中的精确列位置

        Args:
            line: K文件中的一行文本
            target_value: 要查找的目标值（字符串形式，如 "0.16" 或 "300.0"）

        Returns:
            (col_start, col_end) 元组，如果未找到则返回 None

        Examples:
            >>> detector = ColumnDetector()
            >>> line = "       0.0       0.0       0.16       0.0"
            >>> detector.detect_value_position(line, "0.16")
            (20, 30)
        """
        # Try exact match first
        pos = line.find(target_value)

        # If not found, try numeric equivalence (e.g., "0.01" == "0.01000")
        if pos == -1:
            try:
                target_float = float(target_value.strip())
                # Try different decimal precisions (from 1 to 6 decimals)
                for precision in [1, 2, 3, 4, 5, 6]:
                    alternative = f"{target_float:.{precision}f}".strip()
                    pos = line.find(alternative)
                    if pos != -1:
                        target_value = alternative  # Update target_value for position calculation
                        break
            except ValueError:
                pass  # Not a number, keep original behavior

        if pos == -1:
            return None

        # 实现列范围检测逻辑
        # 策略：直接计算数值所在的10列字段边界（防止跨字段合并）

        # 计算数值所在的10列字段
        # 例如：pos=7 在第0个字段（0-10），pos=17 在第1个字段（10-20）
        field_index = pos // 10
        col_start = field_index * 10
        col_end = col_start + 10

        # 验证这个字段确实包含目标值（防止边界情况）
        field_content = line[col_start:col_end] if col_end <= len(line) else line[col_start:]
        if target_value not in field_content:
            # 如果当前字段不包含目标值，可能是因为值跨越了字段边界
            # 这种情况罕见，但需要处理
            # 尝试向左或向右查找
            if col_start > 0:
                prev_field = line[col_start-10:col_start]
                if target_value in prev_field:
                    col_start -= 10
                    col_end -= 10
            elif col_end < len(line):
                next_field = line[col_end:col_end+10]
                if target_value in next_field:
                    col_start += 10
                    col_end += 10

        if self.debug:
            print(f"检测到 '{target_value}' 在列 {col_start}-{col_end}")
            print(f"字段内容: '{line[col_start:col_end]}'")

        return (col_start, col_end)

    def _adjust_to_standard_width(self, col_start: int, col_end: int) -> Tuple[int, int]:
        """
        将列范围调整到LS-DYNA标准列宽

        Args:
            col_start: 初始列起始位置
            col_end: 初始列结束位置

        Returns:
            调整后的 (col_start, col_end)

        Note:
            LS-DYNA 通常使用10列宽的字段，如：
            col 0-10, 10-20, 20-30, 30-40...
        """
        # 调整起始列到10的倍数
        adjusted_start = (col_start // 10) * 10

        # 调整结束列到10的倍数
        adjusted_end = ((col_end + 9) // 10) * 10

        # 确保字段宽度至少为10
        if adjusted_end - adjusted_start < 10:
            adjusted_end = adjusted_start + 10

        return (adjusted_start, adjusted_end)

    def detect_multiple_values(self, line: str, values: list) -> dict:
        """
        检测一行中多个值的列位置

        Args:
            line: K文件中的一行文本
            values: 要查找的值列表

        Returns:
            {value: (col_start, col_end)} 字典
        """
        results = {}
        for value in values:
            pos = self.detect_value_position(line, str(value))
            if pos:
                results[value] = pos
        return results

    def validate_column_width(self, col_start: int, col_end: int) -> bool:
        """
        验证列宽是否合理

        Args:
            col_start: 列起始位置
            col_end: 列结束位置

        Returns:
            是否合理
        """
        width = col_end - col_start

        # 宽度必须为正
        if width <= 0:
            return False

        # 宽度应该是标准宽度之一，或10的倍数
        if width in self.STANDARD_WIDTHS or width % 10 == 0:
            return True

        # 宽度过大或过小都不合理
        if width > 50 or width < 5:
            return False

        return True

    def format_value_to_width(self, value: float, width: int, format_spec: str = None) -> str:
        """
        将数值格式化到指定列宽

        Args:
            value: 要格式化的数值
            width: 目标列宽
            format_spec: 格式化字符串（如 "%.2f"），如果为None则自动选择

        Returns:
            格式化后的字符串（右对齐，填充到指定宽度）

        Raises:
            ValueError: 如果格式化后的值超过列宽
        """
        if format_spec:
            # 使用指定格式
            formatted = format_spec % value
        else:
            # 自动选择格式
            if width >= 15:
                formatted = f"{value:.6f}"
            elif width >= 10:
                formatted = f"{value:.3f}"
            else:
                formatted = f"{value:.2f}"

        # 去除多余的零和小数点（可选）
        # formatted = formatted.rstrip('0').rstrip('.')

        # 右对齐填充
        formatted = formatted.rjust(width)

        # 验证长度
        if len(formatted) > width:
            raise ValueError(
                f"格式化后的值 '{formatted}' ({len(formatted)}字符) "
                f"超过列宽 {width}"
            )

        return formatted


# 单元测试
if __name__ == "__main__":
    detector = ColumnDetector()

    print("列宽检测器测试：\n")

    # 测试1：检测单个值
    test_line1 = "       0.0       0.0       0.16       0.0       0.0"
    print(f"1. 测试行: '{test_line1}'")
    result = detector.detect_value_position(test_line1, "0.16")
    if result:
        col_start, col_end = result
        print(f"   找到 '0.16' 在列 {col_start}-{col_end}")
        print(f"   字段内容: '{test_line1[col_start:col_end]}'")
    else:
        print("   未找到")

    # 测试2：标准列宽调整
    print(f"\n2. 标准列宽调整测试：")
    adjusted = detector._adjust_to_standard_width(22, 26)
    print(f"   原始: (22, 26) → 调整后: {adjusted}")

    # 测试3：格式化测试
    print(f"\n3. 数值格式化测试：")
    formatted = detector.format_value_to_width(0.16, 10, "%10.2f")
    print(f"   0.16 → 10列宽: '{formatted}' (长度{len(formatted)})")

    formatted2 = detector.format_value_to_width(1600.5, 10, "%10.1f")
    print(f"   1600.5 → 10列宽: '{formatted2}' (长度{len(formatted2)})")

    # 测试4：多值检测
    print(f"\n4. 多值检测测试：")
    test_line2 = "         2      7.86       2.1     0.284      0.01       0.0       1.0"
    values = ["7.86", "2.1", "0.01"]
    results = detector.detect_multiple_values(test_line2, values)
    for val, pos in results.items():
        print(f"   '{val}' → 列 {pos}")
