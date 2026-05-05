Etsy 白底产品图生成工具
================================================================

功能说明
--------
将产品图片转换为白底电商标准产品图。
基于豆包 Seedream 4.5 AI 图生图 API，全自动处理，无需手动PS。

处理流程：
  1. 读取 input 文件夹中的原图
  2. 调用豆包 AI 生成白底产品图
  3. 白底图保存到 output 文件夹
  4. 原图自动移动到 bak 文件夹备份


快速开始（两种方式）
--------------------

【方式一：独立程序版（推荐，一键运行）】
  1. 先双击运行 build.bat，生成 etsy_product_tool.exe（约 20-30MB）
  2. 以后每次双击 etsy_product_tool.exe 即可运行，无需安装 Python

【方式二：Python 运行版】
  需要电脑已安装 Python 3.9+
  1. 安装依赖：pip install requests Pillow
  2. 双击 run.bat 运行


首次配置（重要！）
-----------------
首次运行会要求填写路径，可以直接回车使用默认路径（相对目录）：

  输入目录（原图）：将产品图放入此文件夹
  输出目录（白底图）：生成的图片保存位置
  备份目录：原图备份位置

也可以预先编辑 config.json 填写路径（更方便）。


目录结构
--------
etsy_product_tool/
  ├── config.json       ← 配置文件（可预先填写路径和API Key）
  ├── run.py            ← 主程序（Python版）
  ├── run.bat           ← 双击运行入口
  ├── etsy_product_tool.exe  ← 打包后生成（build.bat后出现）
  ├── build.bat         ← 打包脚本（首次运行一次即可）
  ├── input/           ← 原图输入目录（默认）
  ├── output/          ← 白底图输出目录（默认）
  ├── bak/             ← 原图备份目录（默认）
  ├── logs/            ← 日志目录（自动生成）
  └── README.txt       ← 本文件


config.json 配置说明
-------------------
{
  "api_key": "你的ARK_API_KEY",
  "endpoint_id": "ep-20260420205419-xw8pv",
  "model": "doubao-seedream-4-5-251128",
  "input_folder": "input",       ← 支持相对路径（相对于exe所在目录）
  "output_folder": "output",    ← 或绝对路径如 D:\\图片\\output
  "bak_folder": "bak",
  "image_size": "2K",           ← 图片尺寸：2K=2048x2048
  "n": 1,                       ← 每张原图生成几张白底图
  "max_workers": 2,             ← 并发处理数（建议不超过3）
  "retry": 2                    ← API失败重试次数
}

建议预先填好 api_key、input_folder、output_folder、bak_folder，
这样运行时无需手动输入任何内容，直接开始处理。


常见问题
-------
Q: 提示"未找到 Python 环境"？
A: 使用 build.bat 生成独立程序（exe版），无需安装 Python。

Q: API Key 哪里填？
A: 打开 config.json，找到 "api_key"，填入你的火山方舟 ARK API Key。

Q: 支持哪些图片格式？
A: 支持 .jpg、.jpeg、.png、.webp。

Q: 图片处理失败怎么办？
A: 查看 logs 目录下的日志文件，了解失败原因。部分失败会自动重试。

Q: 可以批量处理多少张？
A: 无限制，建议每次 50-100 张，避免 API 限流。


生成独立程序（build.bat）
-------------------------
在 Windows 上双击 build.bat，等待 1-2 分钟，自动生成 etsy_product_tool.exe
以后双击 exe 即可运行，不需要安装任何 Python 环境。


================================================================
工具版本：v1.0 | 日期：2026-04-20
API：豆包 Seedream 4.5（火山方舟 Ark）
