@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

if not exist "config.json" (
  if not exist "config.example.json" (
    echo 缺少 config.example.json
    pause
    exit /b 1
  )
  copy /y "config.example.json" "config.json" >nul
  echo 已生成 config.json，请用记事本填写 jimeng_ak / jimeng_sk（可按需修改 prompts 节）后重新双击本脚本。
  echo 路径: %cd%\config.json
  pause
  exit /b 1
)

REM 与离线发布包一致：同目录有 exe 则直接运行（无需 Python）
if exist "imageFromjimeng.exe" (
  "imageFromjimeng.exe"
  if errorlevel 1 (
    echo.
    echo [提示] 程序返回错误，请向上翻看日志。
  )
  goto :end
)

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
  python "%~dp0process_images.py"
  if errorlevel 1 (
    echo.
    echo [提示] 程序返回错误，请向上翻看日志。
  )
  goto :end
)

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
  py -3 "%~dp0process_images.py"
  if errorlevel 1 (
    echo.
    echo [提示] 程序返回错误，请向上翻看日志。
  )
  goto :end
)

echo 未找到 imageFromjimeng.exe，也未找到 python / py。
echo 请任选其一：将 Windows 离线包里的 exe 放到本目录同批处理一起，或安装 Python 3 并把 python 加入 PATH。
goto :end

:end
echo.
echo Done.
pause
endlocal
