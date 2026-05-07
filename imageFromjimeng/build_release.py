#!/usr/bin/env python3
"""
在有 Python 的机器上执行一次，生成 dist_release/imageFromjimeng/ 目录：
将该目录整体拷贝到未安装 Python 的电脑上即可（仅需填写同目录下的 config.json）。

用法：
  pip install -r requirements-build.txt
  python3 build_release.py
"""
from __future__ import annotations

import os
import platform
import shutil
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = "imageFromjimeng"
RELEASE_ROOT = ROOT / "dist_release"
OUT_DIR = RELEASE_ROOT / APP
BUILD_TMP = RELEASE_ROOT / "_build"


def write_windows_launcher(dst: Path) -> None:
    bat = dst / "双击运行.bat"
    bat.write_text(
        """@echo off
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
  echo 已生成 config.json，请用记事本填写 jimeng_ak / jimeng_sk（可按需改 prompts）后重新双击本脚本。
  echo 路径：%cd%\\config.json
  pause
  exit /b 1
)

if exist "imageFromjimeng.exe" (
  "%~dp0imageFromjimeng.exe"
  if errorlevel 1 (
    echo.
    echo [提示] 程序返回错误，请向上翻看日志。
  )
) else (
  echo 未找到 imageFromjimeng.exe，尝试使用 process_images.py（需已安装 Python）...
  where python >nul 2>nul
  if %ERRORLEVEL% equ 0 (
    python "%~dp0process_images.py"
    if errorlevel 1 (
      echo.
      echo [提示] 程序返回错误，请向上翻看日志。
    )
    goto :win_launch_done
  )
  where py >nul 2>nul
  if %ERRORLEVEL% equ 0 (
    py -3 "%~dp0process_images.py"
    if errorlevel 1 (
      echo.
      echo [提示] 程序返回错误，请向上翻看日志。
    )
    goto :win_launch_done
  )
  echo 未找到 Python。离线包请确认 imageFromjimeng.exe 与本脚本在同一文件夹。
)
:win_launch_done
echo.
pause
endlocal
""",
        encoding="utf-8",
    )


def write_mac_launcher(dst: Path) -> None:
    cmd = dst / "双击运行.command"
    cmd.write_text(
        """#!/bin/bash
cd "$(dirname "$0")" || exit 1
if [ ! -f "config.json" ]; then
  if [ ! -f "config.example.json" ]; then
    echo "缺少 config.example.json"
    read -r -p "按回车退出..." _
    exit 1
  fi
  cp config.example.json config.json
  echo "已生成 config.json，请填写 jimeng_ak / jimeng_sk（可按需改 prompts）后重新双击运行。"
  echo "路径: $(pwd)/config.json"
  read -r -p "按回车退出..." _
  exit 1
fi
EXE="./imageFromjimeng"
if [ ! -x "$EXE" ]; then
  chmod +x "$EXE" 2>/dev/null || true
fi
if [ ! -f "$EXE" ]; then
  echo "未找到 imageFromjimeng 可执行文件"
  read -r -p "按回车退出..." _
  exit 1
fi
EXIT=0
"$EXE" || EXIT=$?
if [ "$EXIT" -ne 0 ]; then
  echo ""
  echo "[提示] 程序异常结束，退出码: $EXIT"
fi
echo ""
read -r -p "按回车关闭..." _
exit "$EXIT"
""",
        encoding="utf-8",
    )
    mode = cmd.stat().st_mode
    cmd.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def write_readme(dst: Path, plat: str) -> None:
    extra_mac = ""
    if plat == "Darwin":
        extra_mac = (
            "\n【macOS】若提示「无法打开」：在「系统设置 → 隐私与安全性」中允许，"
            "或对「imageFromjimeng」右键 → 打开。\n"
        )
    text = f"""imageFromjimeng 离线发布包（无需安装 Python）

1. 将整个文件夹拷到任意路径（路径尽量不要含中文，避免个别环境兼容问题）。
2. 双击「双击运行」脚本：
   - 首次会自动从 config.example.json 复制出 config.json；
   - 用记事本 / 文本编辑器打开 config.json，填写 jimeng_ak、jimeng_sk；
   - 四类提示词在 config.json 的 prompts 节中，可按需修改；
   - 再次双击运行。
3. 把待处理图片放入各 input 子文件夹；生成结果在 output；成功后原图移到 backup。

四类目录：
  input/pet_black | pet_nonblack | human_black | human_nonblack
（output / backup 同名）

说明：本包不接网络以外的「环境变量」；密钥只写在 config.json 即可。
{extra_mac}
打包平台：{plat}
"""
    dst.joinpath("使用说明.txt").write_text(text, encoding="utf-8")


def ensure_dirs(dst: Path) -> None:
    for key in ("pet_black", "pet_nonblack", "human_black", "human_nonblack"):
        for sub in ("input", "output", "backup"):
            (dst / sub / key).mkdir(parents=True, exist_ok=True)


def main() -> int:
    example = ROOT / "config.example.json"
    if not example.exists():
        print("缺少 config.example.json")
        return 1
    if not (ROOT / "process_images.py").exists():
        print("缺少 process_images.py")
        return 1

    try:
        import PyInstaller.__main__ as pyi  # noqa: WPS433 — runtime dep for builders
    except ImportError:
        print("请先安装：pip install -r requirements-build.txt")
        return 1

    if RELEASE_ROOT.exists():
        shutil.rmtree(RELEASE_ROOT)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    sep = ";" if platform.system() == "Windows" else ":"
    pyi.run(
        [
            str(ROOT / "process_images.py"),
            "--name",
            APP,
            "--onefile",
            "--console",
            "--clean",
            "--noconfirm",
            f"--distpath={OUT_DIR}",
            f"--workpath={BUILD_TMP}",
            f"--specpath={RELEASE_ROOT}",
            f"--add-data={example}{sep}.",
        ]
    )

    shutil.copy2(example, OUT_DIR / "config.example.json")
    ensure_dirs(OUT_DIR)

    plat = platform.system()
    if plat == "Windows":
        write_windows_launcher(OUT_DIR)
    else:
        write_mac_launcher(OUT_DIR)

    write_readme(OUT_DIR, plat)

    print()
    print("=" * 60)
    print(f"发布包已生成：{OUT_DIR}")
    print("请将该文件夹整体压缩 / 拷贝到目标电脑。")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
