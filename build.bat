@echo off
chcp 65001 >nul 2>&1
title 构建视频比例转换工具

echo.
echo  ========================================
echo    构建视频比例转换工具 - 打包为 EXE
echo  ========================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    py --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo  [错误] 未检测到 Python，请先安装 Python 3.8+
        pause
        exit /b 1
    )
    set PYTHON=py
) else (
    set PYTHON=python
)

echo  [1/3] 安装构建依赖...
%PYTHON% -m pip install -r "%~dp0requirements.txt" -q
%PYTHON% -m pip install pyinstaller -q
if %errorlevel% neq 0 (
    echo  [错误] 依赖安装失败
    pause
    exit /b 1
)

echo  [2/3] 清理旧构建...
if exist "%~dp0dist" rmdir /s /q "%~dp0dist"
if exist "%~dp0build" rmdir /s /q "%~dp0build"

echo  [3/3] 打包中（请耐心等待）...
%PYTHON% -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --name "视频比例转换工具" ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --collect-all imageio_ffmpeg ^
    --hidden-import imageio_ffmpeg ^
    --hidden-import tkinter ^
    --hidden-import tkinter.filedialog ^
    "%~dp0app.py"

if %errorlevel% neq 0 (
    echo.
    echo  [错误] 打包失败，请检查上方错误信息
    pause
    exit /b 1
)

echo.
echo  ========================================
echo    打包完成！
echo    输出目录: %~dp0dist\视频比例转换工具\
echo    双击 视频比例转换工具.exe 即可运行
echo  ========================================
echo.

:: 打开输出目录
start "" "%~dp0dist\视频比例转换工具"

pause
