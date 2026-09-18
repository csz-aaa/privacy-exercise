@echo off
rem 双击本文件启动图形界面的网络检测助手
chcp 65001 >nul
cd /d "%~dp0"

where pythonw >nul 2>nul
if not errorlevel 1 goto use_pythonw

where python >nul 2>nul
if not errorlevel 1 goto use_python

goto missing_python

:use_pythonw
start "" pythonw "%~dp0network_detection_gui.py"
exit /b

:use_python
python "%~dp0network_detection_gui.py"
exit /b

:missing_python
echo 未找到 Python，请先安装 Python 3.10 或更高版本。
echo 安装时请勾选 "Add Python to PATH"。
pause
