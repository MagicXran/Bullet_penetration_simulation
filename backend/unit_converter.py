#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LS-DYNA K文件单位转换器

单位系统说明：
- 时间单位: 0.1 µs (十分之一微秒)
- 应力单位: 0.01 GPa = 10 MPa
- 速度单位: 10 km/s
- 密度单位: g/cm³

转换关系：
- 速度: K值 × 10000 = m/s
- 应力: K值 × 1000 = MPa (K值 × 100 = GPa)
- 时间: K值 × 0.1 = µs
"""


class UnitConverter:
    """物理单位 ↔ K文件单位的双向转换器"""

    # ==================== 物理单位 → K文件值 ====================

    @staticmethod
    def velocity_to_k(velocity_ms: float) -> float:
        """
        速度：m/s → K文件值

        Args:
            velocity_ms: 速度（米/秒）

        Returns:
            K文件中的速度值

        Examples:
            >>> UnitConverter.velocity_to_k(1600)
            0.16
        """
        return velocity_ms / 10000.0

    @staticmethod
    def stress_mpa_to_k(stress_mpa: float) -> float:
        """
        应力：MPa → K文件值

        根据实际K文件：K值 0.01 = 1000 MPa
        因此转换公式：K值 = MPa / 100000

        Args:
            stress_mpa: 应力（兆帕）

        Returns:
            K文件中的应力值

        Examples:
            >>> UnitConverter.stress_mpa_to_k(1000)
            0.01
        """
        return stress_mpa / 100000.0

    @staticmethod
    def stress_gpa_to_k(stress_gpa: float) -> float:
        """
        应力：GPa → K文件值

        根据实际K文件：K值 0.01 = 1 GPa
        因此转换公式：K值 = GPa / 100

        Args:
            stress_gpa: 应力（吉帕）

        Returns:
            K文件中的应力值

        Examples:
            >>> UnitConverter.stress_gpa_to_k(1.0)
            0.01
        """
        return stress_gpa / 100.0

    @staticmethod
    def time_us_to_k(time_us: float) -> float:
        """
        时间：µs → K文件值

        Args:
            time_us: 时间（微秒）

        Returns:
            K文件中的时间值

        Examples:
            >>> UnitConverter.time_us_to_k(30)
            300.0
        """
        return time_us / 0.1

    @staticmethod
    def density_to_k(density_gcc: float) -> float:
        """
        密度：g/cm³ → K文件值

        注意：K文件中密度直接使用 g/cm³，不需要转换

        Args:
            density_gcc: 密度（克/立方厘米）

        Returns:
            K文件中的密度值

        Examples:
            >>> UnitConverter.density_to_k(7.86)
            7.86
        """
        return density_gcc

    # ==================== K文件值 → 物理单位 ====================

    @staticmethod
    def k_to_velocity(k_value: float) -> float:
        """
        速度：K文件值 → m/s

        Args:
            k_value: K文件中的速度值

        Returns:
            速度（米/秒）

        Examples:
            >>> UnitConverter.k_to_velocity(0.16)
            1600.0
        """
        return k_value * 10000.0

    @staticmethod
    def k_to_stress_mpa(k_value: float) -> float:
        """
        应力：K文件值 → MPa

        根据实际K文件：K值 0.01 = 1000 MPa
        因此转换公式：MPa = K值 × 100000

        Args:
            k_value: K文件中的应力值

        Returns:
            应力（兆帕）

        Examples:
            >>> UnitConverter.k_to_stress_mpa(0.01)
            1000.0
        """
        return k_value * 100000.0

    @staticmethod
    def k_to_stress_gpa(k_value: float) -> float:
        """
        应力：K文件值 → GPa

        根据实际K文件：K值 0.01 = 1 GPa
        因此转换公式：GPa = K值 × 100

        Args:
            k_value: K文件中的应力值

        Returns:
            应力（吉帕）

        Examples:
            >>> UnitConverter.k_to_stress_gpa(0.01)
            1.0
        """
        return k_value * 100.0

    @staticmethod
    def k_to_time_us(k_value: float) -> float:
        """
        时间：K文件值 → µs

        Args:
            k_value: K文件中的时间值

        Returns:
            时间（微秒）

        Examples:
            >>> UnitConverter.k_to_time_us(300.0)
            30.0
        """
        return k_value * 0.1

    @staticmethod
    def k_to_density(k_value: float) -> float:
        """
        密度：K文件值 → g/cm³

        注意：K文件中密度直接使用 g/cm³，不需要转换

        Args:
            k_value: K文件中的密度值

        Returns:
            密度（克/立方厘米）

        Examples:
            >>> UnitConverter.k_to_density(7.86)
            7.86
        """
        return k_value


# 单元测试
if __name__ == "__main__":
    import doctest
    doctest.testmod()

    print("===== Unit Converter Test =====")
    print(f"Velocity 1600 m/s -> K value: {UnitConverter.velocity_to_k(1600)}")
    print(f"K value 0.16 -> Velocity: {UnitConverter.k_to_velocity(0.16)} m/s")
    print(f"Stress 1000 MPa -> K value: {UnitConverter.stress_mpa_to_k(1000)}")
    print(f"K value 1.0 -> Stress: {UnitConverter.k_to_stress_mpa(1.0)} MPa")
    print(f"Time 30 us -> K value: {UnitConverter.time_us_to_k(30)}")
    print(f"K value 300.0 -> Time: {UnitConverter.k_to_time_us(300.0)} us")
    print("="*30)
