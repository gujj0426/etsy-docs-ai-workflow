# imageFromjimeng

独立本地项目（不依赖 `ai_workflow`），功能：

- 轮询 4 个输入文件夹（4 种图片类型）
- 按类型自动套用对应 Prompt 调用即梦图生图
- 生成图写入各自输出文件夹
- 原图仅在生成成功后移动到各自备份文件夹
- 支持双击启动：`run_imageFromjimeng.command`（macOS）、`run_imageFromjimeng.bat`（Windows）

## 目录结构

- `input/pet_black`
- `input/pet_nonblack`
- `input/human_black`
- `input/human_nonblack`
- `output/...`（四类）
- `backup/...`（四类）

## 首次配置

1. 复制 `config.example.json` 为 `config.json`（脚本首次运行会自动生成）。
2. 在 `config.json` 填写：
   - `jimeng_ak`
   - `jimeng_sk`
3. **提示词**：在 `config.json` 的 **`prompts`** 对象中维护四类文案（键名：`pet_black`、`pet_nonblack`、`human_black`、`human_nonblack`）。若你沿用旧版 `config.json` 且未包含 `prompts`，程序会尝试用同目录 **`config.example.json`** 中的 `prompts` 自动补齐。
4. 把待处理图片放入对应 `input/*` 文件夹。
5. 可选：`delay_seconds_between_requests`（默认 `3`），每张成功后休眠几秒，减轻即梦并发限制。

> 也支持通过环境变量提供密钥：`JIMENG_AK` / `JIMENG_SK`（优先于 config）。
>
> `folders` 里的路径可为相对路径（相对于本项目目录）或绝对路径。

## 双击运行

### macOS

双击：`run_imageFromjimeng.command`（会调用 `python3 process_images.py`）。

### Windows

双击：**`run_imageFromjimeng.bat`**

与 macOS **同一套逻辑**（无需改代码）：

| 能力 | 说明 |
|------|------|
| 配置 | `config.json`：`jimeng_ak` / `jimeng_sk`、`seed`、`folders`、`delay_seconds_between_requests` |
| 提示词 | `config.json` 的 **`prompts`** 四类键；缺省时用同目录 **`config.example.json`** 补齐 |
| 启动方式 | **优先**运行同目录 **`imageFromjimeng.exe`**（离线包）；若无 exe 则用 **`python`** 或 **`py -3`** 运行 **`process_images.py`** |
| 控制台编码 | 脚本开头 **`chcp 65001`**，中文日志正常显示 |
| 防闪退 | 成功或失败结束均有 **`pause`**，并提示非零退出时向上翻看日志 |

离线绿色包：在 **Windows** 上执行 **`build_release.bat`**（或 `python build_release.py`），将生成的 **`dist_release\imageFromjimeng\`** 整夹拷贝到目标机，双击 **`双击运行.bat`** 即可（内含 exe 时无需安装 Python）。

> 环境变量 `JIMENG_AK` / `JIMENG_SK` 若设置，仍会覆盖 config 中的同名字段（与 macOS 一致）。

## 打包为双击程序（可选）

如果你希望不是 `.command`，而是 `.app`：

```bash
cd "/Users/mac/Desktop/etsy/imageFromjimeng"
osacompile -o "imageFromjimeng.app" -e 'do shell script "cd /Users/mac/Desktop/etsy/imageFromjimeng && /bin/zsh ./run_imageFromjimeng.command"'
```

生成后可直接双击 `imageFromjimeng.app`。

## 离线绿色包（目标电脑无需 Python）

在本机（仅需打包时用一次 Python）执行：

```bash
cd "/Users/mac/Desktop/etsy/imageFromjimeng"
pip install -r requirements-build.txt
python3 build_release.py
```

生成目录：**`dist_release/imageFromjimeng/`** —— 将该文件夹**整体**拷贝或打成 zip，解压到未安装 Python 的电脑上即可。

- **Windows**：发布包里双击 **`双击运行.bat`**（同目录会有 **`imageFromjimeng.exe`**）。
- **macOS**：同目录双击 **`双击运行.command`**（可执行文件名为 **`imageFromjimeng`**）。

**说明：** PyInstaller 需在对应系统上打包才能得到该平台可执行文件（例如在 Windows 上打包才能得到 `.exe`；在 macOS 上打包得到 Mac 版二进制）。
