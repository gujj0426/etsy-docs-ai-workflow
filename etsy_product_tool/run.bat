@echo off
chcp 65001 >nul 2>&1
title Etsy 白底产品图生成工具

:: ================================================================
:: 双击此文件运行
:: 如果目录下有 etsy_product_tool.exe（PyInstaller 打包版本），直接运行
:: 否则尝试用系统 Python 运行
:: ================================================================

echo.
echo  Etsy 白底产品图生成工具
echo  ================================
echo.

set "SCRIPT_DIR=%~dp0"
set "EXE_NAME=etsy_product_tool.exe"

if exist "%SCRIPT_DIR%%EXE_NAME%" (
    echo 启动独立程序版本...
    start "" "%SCRIPT_DIR%%EXE_NAME%"
    goto :end
)

:: 尝试找 Python
where python >nul 2>&1
if %errorlevel%==0 (
    echo 使用系统 Python 启动...
    python "%SCRIPT_DIR%run.py"
    goto :end
)

where python3 >nul 2>&1
if %errorlevel%==0 (
    echo 使用系统 Python3 启动...
    python3 "%SCRIPT_DIR%run.py"
    goto :end
)

:: 尝试常见 Python 安装路径
if exist "C:\Python39\python.exe" (
    echo 找到 Python 3.9...
    "C:\Python39\python.exe" "%SCRIPT_DIR%run.py"
    goto :end
)
if exist "C:\Python38\python.exe" (
    echo 找到 Python 3.8...
    "C:\Python38\python.exe" "%SCRIPT_DIR%run.py"
    goto :end
)
if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python39\python.exe" (
    echo 找到 Python 3.9（用户目录）...
    "%USERPROFILE%\AppData\Local\Programs\Python\Python39\python.exe" "%SCRIPT_DIR%run.py"
    goto :end
)

:: 都没找到
echo.
echo  [X] 未找到 Python 环境！
echo.
echo  请选择以下方式之一：
echo.
echo  方式一（推荐）：双击运行 build.bat 生成独立程序
echo  方式二：手动安装 Python 3.9+，然后重新运行此文件
echo.
echo  Python 下载地址：https://www.python.org/downloads/
echo.
pause

:end
pause
