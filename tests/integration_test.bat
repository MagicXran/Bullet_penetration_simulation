@echo off
chcp 65001 > nul
REM ========================================
REM  平台A联调验证脚本
REM  用途：快速验证App API是否可用
REM ========================================

set APP_URL=http://localhost:8000/api
set TASK_ID=integration_test_%RANDOM%

echo ========================================
echo  App联调验证脚本
echo  APP_URL: %APP_URL%
echo  TASK_ID: %TASK_ID%
echo ========================================
echo.

REM Step 1: 检查服务可用性
echo [Step 1] 检查服务可用性...
curl -s "%APP_URL%/queue/status" > nul 2>&1
if errorlevel 1 (
    echo [FAIL] 服务不可用，请确认App已启动
    exit /b 1
)
echo [OK] 服务可用
echo.

REM Step 2: 模拟保存任务
echo [Step 2] 模拟保存任务...
curl -s -X POST "%APP_URL%/task/save" ^
    -H "Content-Type: application/json" ^
    -d "{\"task_id\":\"%TASK_ID%\",\"params\":{\"velocity_z\":1600,\"bullet_yield_stress\":1000,\"target_yield_stress\":800,\"friction_static\":0.25,\"friction_dynamic\":0.18,\"simulation_endtime\":30}}"
echo.
echo.

REM Step 3: 触发执行
echo [Step 3] 触发执行...
curl -s -X POST "%APP_URL%/task/%TASK_ID%/execute"
echo.
echo.

REM Step 4: 等待并查询状态
echo [Step 4] 等待3秒后查询状态...
timeout /t 3 /nobreak > nul
curl -s "%APP_URL%/task/%TASK_ID%"
echo.
echo.

echo ========================================
echo  联调验证完成！
echo  如果看到 status=3 表示成功
echo ========================================

pause
