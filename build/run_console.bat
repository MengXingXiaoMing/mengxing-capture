@echo off
rem 控制台模式启动（调试用，会显示日志和错误）
chcp 65001 >nul
cd /d "%~dp0.."
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py %*
    goto :end
)
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 没有找到 Python，请先安装 Python 3.10 - 3.12 并勾选 "Add to PATH"。
    pause
    exit /b 1
)
python main.py %*
:end
if errorlevel 1 pause
