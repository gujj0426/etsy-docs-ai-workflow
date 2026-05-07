@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo [build_release] 当前目录: %cd%
echo [build_release] 安装 PyInstaller（仅本机构建机需要）...
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
  python -m pip install -r requirements-build.txt
  if errorlevel 1 (
    echo pip 安装失败
    goto :fail
  )
  python build_release.py
  if errorlevel 1 goto :fail
  goto :ok
)

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
  py -3 -m pip install -r requirements-build.txt
  if errorlevel 1 (
    echo pip 安装失败
    goto :fail
  )
  py -3 build_release.py
  if errorlevel 1 goto :fail
  goto :ok
)

echo 未找到 python 或 py，请先安装 Python 3。
goto :fail

:ok
echo.
echo [build_release] 完成，输出目录: dist_release\imageFromjimeng\
goto :end

:fail
echo.
echo [build_release] 失败。

:end
pause
endlocal
