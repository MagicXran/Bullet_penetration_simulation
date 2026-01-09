#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GIF生成功能快速测试

测试 lsdyna_runner.py 中的后处理cfile生成逻辑是否正确。
验证修复后：
1. cfile使用 movie GIF 命令（而非 movie avi）
2. 不生成临时AVI文件
3. 配置的 output_format 被正确使用

运行方式:
    python tests/test_gif_generation.py
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.lsdyna_runner import PrePostConfig, LSDynaRunner, LSDynaConfig


def test_cfile_format_gif():
    """测试GIF格式的cfile生成"""
    print("\n" + "=" * 60)
    print("测试1: GIF格式cfile生成")
    print("=" * 60)

    prepost_cfg = PrePostConfig(
        executable_path='lsprepost.exe',
        output_format='gif',
        resolution=(1920, 1080),
        fps=30,
        view='front',
        fringe_variable='stress'
    )

    lsdyna_cfg = LSDynaConfig(executable_path='lsdyna.exe')
    runner = LSDynaRunner(lsdyna_cfg, prepost_cfg)

    cfile = runner._generate_cfile(
        d3plot_path=r'G:\BulletSim\tasks\test\test.d3plot',
        output_path=r'G:\BulletSim\tasks\test\test.gif'
    )

    print("生成的CFILE内容:")
    print("-" * 40)
    print(cfile)
    print("-" * 40)

    # 验证
    errors = []

    if 'movie GIF' not in cfile:
        errors.append("ERROR: cfile未使用 'movie GIF' 命令")

    if 'movie avi' in cfile.lower() or 'movie AVI' in cfile:
        errors.append("ERROR: cfile仍然使用 'movie avi' 命令")

    if '_temp.avi' in cfile:
        errors.append("ERROR: cfile仍然引用临时AVI文件")

    if 'pall' not in cfile:
        errors.append("WARNING: cfile缺少 'pall' 命令（显示所有部件）")

    if 'showlegend 1' not in cfile:
        errors.append("WARNING: cfile缺少 'showlegend' 命令")

    if errors:
        for err in errors:
            print(err)
        return False
    else:
        print("PASS: GIF格式cfile生成正确")
        return True


def test_cfile_format_avi():
    """测试AVI格式的cfile生成"""
    print("\n" + "=" * 60)
    print("测试2: AVI格式cfile生成")
    print("=" * 60)

    prepost_cfg = PrePostConfig(
        executable_path='lsprepost.exe',
        output_format='avi',
        resolution=(1280, 720),
        fps=24,
        view='isometric',
        fringe_variable='displacement'
    )

    lsdyna_cfg = LSDynaConfig(executable_path='lsdyna.exe')
    runner = LSDynaRunner(lsdyna_cfg, prepost_cfg)

    cfile = runner._generate_cfile(
        d3plot_path=r'D:\sim\result.d3plot',
        output_path=r'D:\sim\output.avi'
    )

    print("生成的CFILE内容:")
    print("-" * 40)
    print(cfile)
    print("-" * 40)

    # 验证
    errors = []

    if 'movie AVI' not in cfile:
        errors.append("ERROR: cfile未使用 'movie AVI' 命令")

    if 'movie GIF' in cfile:
        errors.append("ERROR: AVI配置却生成了GIF命令")

    if '1280 720 24' not in cfile:
        errors.append("ERROR: 分辨率或帧率参数不正确")

    if 'view iso1' not in cfile:
        errors.append("ERROR: 视角映射不正确（isometric应映射为iso1）")

    if 'Displacement' not in cfile:
        errors.append("ERROR: 云图变量映射不正确")

    if errors:
        for err in errors:
            print(err)
        return False
    else:
        print("PASS: AVI格式cfile生成正确")
        return True


def test_cfile_format_mpeg():
    """测试MPEG格式的cfile生成"""
    print("\n" + "=" * 60)
    print("测试3: MPEG格式cfile生成")
    print("=" * 60)

    prepost_cfg = PrePostConfig(
        executable_path='lsprepost.exe',
        output_format='mpeg',
        resolution=(1920, 1080),
        fps=30,
        view='top',
        fringe_variable='velocity'
    )

    lsdyna_cfg = LSDynaConfig(executable_path='lsdyna.exe')
    runner = LSDynaRunner(lsdyna_cfg, prepost_cfg)

    cfile = runner._generate_cfile(
        d3plot_path=r'C:\work\sim.d3plot',
        output_path=r'C:\work\animation.mpeg'
    )

    print("生成的CFILE内容:")
    print("-" * 40)
    print(cfile)
    print("-" * 40)

    # 验证
    errors = []

    if 'movie MPEG' not in cfile:
        errors.append("ERROR: cfile未使用 'movie MPEG' 命令")

    if 'view top' not in cfile:
        errors.append("ERROR: 视角设置不正确")

    if 'Velocity' not in cfile:
        errors.append("ERROR: 云图变量映射不正确")

    if errors:
        for err in errors:
            print(err)
        return False
    else:
        print("PASS: MPEG格式cfile生成正确")
        return True


def test_output_path_no_extension():
    """测试输出路径是否正确移除扩展名"""
    print("\n" + "=" * 60)
    print("测试4: 输出路径扩展名处理")
    print("=" * 60)

    prepost_cfg = PrePostConfig(
        executable_path='lsprepost.exe',
        output_format='gif',
        resolution=(1920, 1080),
        fps=30,
        view='front',
        fringe_variable='stress'
    )

    lsdyna_cfg = LSDynaConfig(executable_path='lsdyna.exe')
    runner = LSDynaRunner(lsdyna_cfg, prepost_cfg)

    # 测试带.gif扩展名的路径
    cfile = runner._generate_cfile(
        d3plot_path=r'G:\test\sim.d3plot',
        output_path=r'G:\test\animation.gif'
    )

    # 验证movie命令中的路径不含扩展名
    errors = []

    # 提取movie行
    movie_line = None
    for line in cfile.split('\n'):
        if line.startswith('movie'):
            movie_line = line
            break

    print(f"Movie命令: {movie_line}")

    if movie_line:
        # 路径应该是 "G:\test\animation" 而不是 "G:\test\animation.gif"
        if '"G:\\test\\animation"' in movie_line or '"G:/test/animation"' in movie_line:
            print("PASS: 输出路径正确移除了扩展名")
        elif '.gif"' in movie_line:
            errors.append("ERROR: 输出路径仍包含.gif扩展名")
        else:
            print(f"INFO: 路径格式: {movie_line}")

    if errors:
        for err in errors:
            print(err)
        return False
    else:
        print("PASS: 输出路径扩展名处理正确")
        return True


def test_no_ffmpeg_dependency():
    """测试不依赖FFMPEG"""
    print("\n" + "=" * 60)
    print("测试5: FFMPEG依赖检查")
    print("=" * 60)

    from backend.lsdyna_runner import LSDynaRunner
    import inspect

    # 检查 _convert_avi_to_gif 方法是否已删除
    methods = [m for m in dir(LSDynaRunner) if not m.startswith('_')]
    private_methods = [m for m in dir(LSDynaRunner) if m.startswith('_') and not m.startswith('__')]

    print(f"LSDynaRunner 私有方法: {private_methods}")

    if '_convert_avi_to_gif' in private_methods:
        print("ERROR: _convert_avi_to_gif 方法仍然存在")
        return False
    else:
        print("PASS: _convert_avi_to_gif 方法已删除")

    # 检查源代码中是否还有ffmpeg引用
    source_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'backend', 'lsdyna_runner.py'
    )

    with open(source_file, 'r', encoding='utf-8') as f:
        content = f.read()

    if 'ffmpeg' in content.lower():
        print("WARNING: 代码中仍有ffmpeg相关引用（可能是注释）")
    else:
        print("PASS: 代码中无ffmpeg引用")

    if 'force_format="avi"' in content or "force_format='avi'" in content:
        print("ERROR: 代码中仍有 force_format='avi' 硬编码")
        return False
    else:
        print("PASS: 无 force_format='avi' 硬编码")

    return True


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("GIF生成功能测试套件")
    print("=" * 60)

    tests = [
        ("GIF格式cfile生成", test_cfile_format_gif),
        ("AVI格式cfile生成", test_cfile_format_avi),
        ("MPEG格式cfile生成", test_cfile_format_mpeg),
        ("输出路径扩展名处理", test_output_path_no_extension),
        ("FFMPEG依赖检查", test_no_ffmpeg_dependency),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\nERROR: 测试 '{name}' 抛出异常: {e}")
            results.append((name, False))

    # 汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")

    print("-" * 40)
    print(f"通过: {passed}/{total}")

    if passed == total:
        print("\n所有测试通过! GIF生成功能修复成功。")
        return 0
    else:
        print(f"\n有 {total - passed} 个测试失败，请检查代码。")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
