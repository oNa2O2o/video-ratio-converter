@echo off
chcp 65001 >nul 2>&1
title 素材工具箱

echo.
echo  ========================================
echo    素材工具箱 - 启动中
echo  ========================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    py --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo  [错误] 未检测到 Python，请先安装 Python 3.8+
        echo  下载地址: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    set PYTHON=py
) else (
    set PYTHON=python
)

echo  [1/2] 安装依赖...
%PYTHON% -m pip install -r "%~dp0requirements.txt" -q
if %errorlevel% neq 0 (
    echo  [错误] 依赖安装失败，请检查网络连接
    pause
    exit /b 1
)

echo  [2/2] 启动服务器...
echo.

:: Start Flask server
%PYTHON% "%~dp0app.py"

pause
