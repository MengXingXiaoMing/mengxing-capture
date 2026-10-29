@echo off
rem 离线安装：用 vendor\wheels 里的 wheel 包创建 .venv，无需联网
rem 需要本机已安装 Python 3.10 - 3.12
chcp 65001 >nul
cd /d "%~dp0.."

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 没有找到 Python。请先安装 Python 3.10-3.12。
    echo        也可把离线 Python 安装包放到 vendor\python\。
    pause
    exit /b 1
)

if not exist "vendor\wheels" (
    echo [错误] 缺少 vendor\wheels。
    echo        请先在有网络的电脑上运行 build\build_offline_wheels.ps1。
    pause
    exit /b 1
)

echo 正在创建独立环境 .venv ...
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败。
        pause
        exit /b 1
    )
)

echo 正在从本地 wheel 安装依赖（不联网）...
".venv\Scripts\python.exe" -m pip install --no-index --find-links="vendor\wheels" -r requirements.txt
if errorlevel 1 (
    echo [错误] 安装失败，请确认 wheel 与本机 Python 版本匹配。
    pause
    exit /b 1
)

echo.
echo 安装完成，正在启动梦星截屏...
call "%~dp0run_console.bat"
