@echo off
rem 首次运行环境安装：创建 .venv 并安装依赖（平时直接双击根目录「梦星截屏」快捷方式即可）
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
title MengXing Capture Setup

set "ROOT=%~dp0.."
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"
set "VENV_PYW=%ROOT%\.venv\Scripts\pythonw.exe"

if not exist "%VENV_PY%" goto :setup
if not exist "%VENV_PYW%" goto :setup
goto :launch

:setup
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo [错误] 没有找到 Python 3.10 - 3.12。
    echo        请先安装 https://www.python.org/downloads/ 并勾选 Add python.exe to PATH。
    echo.
    pause
    exit /b 1
)

if not exist "%VENV_PY%" (
    echo.
    echo 正在创建独立环境 .venv ...
    python -m venv "%ROOT%\.venv"
    if errorlevel 1 (
        echo [错误] 创建 .venv 失败
        pause
        exit /b 1
    )
    echo 正在安装依赖，可能需要几分钟...
    "%VENV_PY%" -m pip install --upgrade pip
    "%VENV_PY%" -m pip install -r "%ROOT%\requirements.txt"
    if errorlevel 1 (
        echo.
        echo [错误] 依赖安装失败，请检查网络后重试。
        pause
        exit /b 1
    )
)

:launch
if not exist "%VENV_PYW%" set "VENV_PYW=%VENV_PY%"
start "" "%VENV_PYW%" "%ROOT%\main.py"
exit /b 0
