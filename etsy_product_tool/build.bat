@echo off
chcp 65001 >nul 2>&1
title 生成独立程序

echo.
echo  Etsy 白底产品图生成工具 - 打包程序
echo  =============================================
echo.

:: 检查 Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] 未找到 Python，无法打包。
    echo    请先安装 Python 3.9+：https://www.python.org/downloads/
    echo.
    echo    安装后运行：pip install pyinstaller requests Pillow
    echo.
    pause
    exit /b 1
)

:: 安装依赖
echo  检查依赖...
python -c "import requests, PIL" 2>nul
if %errorlevel% neq 0 (
    echo  安装依赖包 requests, Pillow...
    pip install requests Pillow -q
)

echo  检查 PyInstaller...
python -c "import PyInstaller" 2>nul
if %errorlevel% neq 0 (
    echo  安装 PyInstaller...
    pip install pyinstaller -q
)

:: 打包
echo.
echo  开始打包（约需 1-2 分钟）...
echo  ================================
echo.

cd /d "%~dp0"
python -m PyInstaller ^
    --name="etsy_product_tool" ^
    --onefile ^
    --console ^
    --clean ^
    --add-data "config.json;." ^
    run.py

if %errorlevel%==0 (
    echo.
    echo  =============================================
    echo  [OK] 打包成功！
    echo.
    echo  生成文件：
    echo    dist\etsy_product_tool.exe
    echo.
    echo  双击 etsy_product_tool.exe 即可运行！
    echo  =============================================
    echo.
    echo  提示：将 etsy_product_tool.exe 复制到任意位置，
    echo       保留 config.json 在同目录下即可。
    echo.
) else (
    echo.
    echo  [X] 打包失败，请检查上方错误信息。
)

pause
