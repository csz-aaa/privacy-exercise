@echo off
rem 双击本文件即可启动网络诊断工具
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python main.py
    goto end
)

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 main.py
    goto end
)

echo 未找到 Python，请先安装 Python 3.10 或更高版本。
echo 安装时请勾选 "Add Python to PATH"。

:end
pause
