# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置文件 - LS-DYNA K文件参数化系统

使用方法:
    pyinstaller BulletSim.spec

输出目录:
    dist/BulletSim/
"""

import os
from pathlib import Path

# 项目根目录
project_root = Path(SPECPATH)

# 检查必要文件是否存在
required_files = [
    project_root / 'backend' / 'app.py',
    project_root / 'frontend' / 'index.html',
    project_root / 'templates' / '1.k',
]

for f in required_files:
    if not f.exists():
        raise FileNotFoundError(f"必要文件不存在: {f}")

block_cipher = None

a = Analysis(
    # 入口脚本
    [str(project_root / 'backend' / 'app.py')],

    # 额外搜索路径
    pathex=[str(project_root / 'backend')],

    # 二进制依赖（无特殊需求）
    binaries=[],

    # 数据文件（打包进exe）
    datas=[
        # 前端静态文件
        (str(project_root / 'frontend'), 'frontend'),
        # K文件模板
        (str(project_root / 'templates'), 'templates'),
        # 配置文件（也复制到输出目录，方便用户编辑）
        (str(project_root / 'backend' / 'config.json'), '.'),
    ],

    # 隐式导入（PyInstaller 无法自动检测的模块）
    hiddenimports=[
        # FastAPI 和 Pydantic
        'fastapi',
        'pydantic',
        'pydantic.deprecated.decorator',
        'pydantic_core',

        # Uvicorn 及其子模块
        'uvicorn',
        'uvicorn.main',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.http.httptools_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.websockets_impl',
        'uvicorn.protocols.websockets.wsproto_impl',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',

        # HTTP 相关
        'httpx',
        'httpcore',
        'h11',
        'httptools',
        'websockets',

        # APScheduler
        'apscheduler',
        'apscheduler.schedulers',
        'apscheduler.schedulers.background',
        'apscheduler.triggers',
        'apscheduler.triggers.interval',
        'apscheduler.triggers.cron',
        'apscheduler.executors',
        'apscheduler.executors.pool',
        'apscheduler.jobstores',
        'apscheduler.jobstores.memory',

        # Starlette (FastAPI 依赖)
        'starlette',
        'starlette.applications',
        'starlette.middleware',
        'starlette.middleware.cors',
        'starlette.routing',
        'starlette.staticfiles',
        'starlette.responses',
        'starlette.requests',

        # Anyio (异步支持)
        'anyio',
        'anyio._backends',
        'anyio._backends._asyncio',

        # 其他
        'multipart',
        'python_multipart',
        'email_validator',
        'typing_extensions',
        'annotated_types',
    ],

    # Hook 路径
    hookspath=[],

    # Hook 配置
    hooksconfig={},

    # 运行时 Hook
    runtime_hooks=[],

    # 排除模块（减小体积）
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'tensorflow',
        'torch',
        'pytest',
        'unittest',
    ],

    # 是否打包为压缩包
    noarchive=False,

    # 优化级别
    optimize=1,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BulletSim',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 保持控制台窗口以显示日志
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # 图标（如果存在）
    icon=str(project_root / 'icon.ico') if (project_root / 'icon.ico').exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BulletSim',
)
