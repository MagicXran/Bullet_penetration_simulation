@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ============================================================
echo  LS-DYNA K文件参数化系统 - 打包脚本
echo ============================================================
echo.

:: 检查 Python
python --version > nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.11+
    pause
    exit /b 1
)

:: 检查虚拟环境
if not exist ".venv" (
    echo [INFO] 创建虚拟环境...
    python -m venv .venv
)

:: 激活虚拟环境
call .venv\Scripts\activate.bat

:: 安装依赖
echo [INFO] 安装依赖...
pip install -r backend\requirements.txt -q

:: 检查 PyInstaller
pyinstaller --version > nul 2>&1
if errorlevel 1 (
    echo [INFO] 安装 PyInstaller...
    pip install pyinstaller -q
)

:: 清理旧的构建
if exist "build" (
    echo [INFO] 清理旧的 build 目录...
    rmdir /s /q build
)
if exist "dist" (
    echo [INFO] 清理旧的 dist 目录...
    rmdir /s /q dist
)

:: 执行打包
echo.
echo [INFO] 开始打包...
echo ============================================================
pyinstaller BulletSim.spec --noconfirm

if errorlevel 1 (
    echo.
    echo [错误] 打包失败！
    pause
    exit /b 1
)

:: 复制配置文件到输出目录（确保用户可以编辑）
echo.
echo [INFO] 复制配置文件...
copy /y backend\config.json dist\BulletSim\ > nul

:: 创建空的 tasks 目录
if not exist "dist\BulletSim\tasks" (
    mkdir dist\BulletSim\tasks
)

echo.
echo ============================================================
echo  打包完成！
echo ============================================================
echo.
echo 输出目录: dist\BulletSim\
echo.
echo 部署步骤:
echo   1. 将 dist\BulletSim\ 目录复制到目标服务器
echo   2. 编辑 config.json，配置 LS-DYNA 路径
echo   3. 双击 BulletSim.exe 启动
echo   4. 浏览器访问 http://localhost:8000
echo.
echo ============================================================

:: 打开输出目录
explorer dist\BulletSim

pause
