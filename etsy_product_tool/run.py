"""
Etsy 电商白底产品图生成工具
===============================
功能：读取本地图片 → 调用豆包 Seedream 4.5 图生图 → 生成白底电商产品图
作者：AI 辅助生成
日期：2026-04-20
依赖：Python 3.9+，requests，Pillow
"""

import os
import sys
import json
import time
import base64
import shutil
import logging
import requests
import traceback
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

# ═══════════════════════════════════════════════════════════
# 自动获取脚本/可执行文件所在目录（支持 PyInstaller exe）
# ═══════════════════════════════════════════════════════════
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent.resolve()
else:
    BASE_DIR = Path(__file__).parent.resolve()

CONFIG_FILE = BASE_DIR / "config.json"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


# ═══════════════════════════════════════════════════════════
# 配置加载（config.json > 环境变量 > 默认值）
# ═══════════════════════════════════════════════════════════
def load_config() -> dict:
    defaults = {
        "api_key": os.getenv("ARK_API_KEY", ""),
        "endpoint_id": "ep-20260420205419-xw8pv",
        "model": "doubao-seedream-4-5-251128",
        "input_folder": "",
        "output_folder": "",
        "bak_folder": "",
        "image_size": "2K",
        "n": 1,
        "max_workers": 2,
        "retry": 2,
    }

    if not CONFIG_FILE.exists():
        logging.warning(f"未找到 config.json，将使用默认配置")
        return defaults

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        for k, v in defaults.items():
            if k not in user_cfg or not str(user_cfg.get(k, "")).strip():
                user_cfg[k] = v
        for key in ["input_folder", "output_folder", "bak_folder"]:
            val = user_cfg.get(key, "")
            if val:
                p = Path(val)
                user_cfg[key] = str(p.resolve() if p.is_absolute() else (BASE_DIR / p).resolve())
        return user_cfg
    except Exception as e:
        logging.error(f"读取 config.json 失败: {e}")
        return defaults


# ═══════════════════════════════════════════════════════════
# 白底产品图 prompt（英文，Seedream 效果更稳定）
# ═══════════════════════════════════════════════════════════
WHITE_BG_PROMPT = (
    "Remove the background completely and replace with pure solid white (#FFFFFF). "
    "Do NOT rotate, tilt, flip, or change the orientation of the product in any way. "
    "The product must remain in its EXACT original angle, pose, and viewpoint as shown in the input image. "
    "Do NOT move the camera angle or change the perspective. "
    "Preserve every detail exactly: colors, textures, engravings, materials, shapes, "
    "reflections, highlights, shadows on the product itself. "
    "Center the product on the white background. "
    "No new shadows, no new reflections, no outlines, no artifacts, no cropping, "
    "no changes to the product itself. "
    "Ultra high quality, 4K resolution."
)


# ═══════════════════════════════════════════════════════════
# API 调用
# ═══════════════════════════════════════════════════════════
class ArkProductAPI:
    BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

    def __init__(self, api_key: str, endpoint_id: str, model: str,
                 image_size: str = "2K", n: int = 1):
        self.api_key = api_key
        self.endpoint_id = endpoint_id
        self.model = model
        self.image_size = image_size
        self.n = n
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Endpoint-Id": endpoint_id,
        })

    def _post(self, endpoint: str, payload: dict, timeout: int = 120) -> dict:
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        resp = self.session.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def generate(self, image_b64: str, prompt: str, retry: int = 2) -> list:
        mime_type = "image/jpeg" if image_b64.startswith("/9j/") else "image/png"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "image": f"data:{mime_type};base64,{image_b64}",
            "size": self.image_size,
            "n": self.n,
            "response_format": "url",
            "watermark": False,
        }
        errors = []
        for attempt in range(retry + 1):
            try:
                data = self._post("images/generations", payload, timeout=120)
                urls = [item.get("url") for item in (data.get("data") or [])
                        if item.get("url")]
                if urls:
                    logging.info(f"  API 成功，返回 {len(urls)} 张图片")
                    return urls
                err = data.get("error") or data
                errors.append(str(err))
                logging.warning(f"  API 返回无图片: {err}")
            except requests.exceptions.Timeout:
                msg = f"请求超时（尝试 {attempt+1}/{retry+1}）"
                logging.warning(msg)
                errors.append(msg)
                time.sleep(5)
            except requests.exceptions.HTTPError as e:
                err = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                errors.append(err)
                logging.warning(f"  {err}")
                if e.response.status_code == 429:
                    logging.info("  触发限流，等待 15 秒后重试...")
                    time.sleep(15)
                else:
                    time.sleep(3)
            except Exception as e:
                errors.append(str(e))
                logging.warning(f"  API 异常: {e}")
                time.sleep(2)
        raise RuntimeError(f"API 调用失败: {'; '.join(errors)}")


def download_image(url: str, save_path: Path) -> Path:
    resp = requests.get(url, timeout=60, stream=True)
    resp.raise_for_status()
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(65536):
            f.write(chunk)
    return save_path


# ═══════════════════════════════════════════════════════════
# 核心处理逻辑
# ═══════════════════════════════════════════════════════════
def process_image(api: ArkProductAPI, src_path: Path,
                  output_dir: Path, bak_dir: Path) -> dict:
    result = {"success": False, "input": str(src_path), "output": None, "error": None}
    try:
        logging.info(f"  读取原图: {src_path.name}")
        with open(src_path, "rb") as f:
            img_bytes = f.read()
        b64_str = base64.b64encode(img_bytes).decode("utf-8")
        fmt = "png" if img_bytes[:4] == b"\x89PNG" else "jpg"

        logging.info(f"  调用豆包图生图 API...")
        urls = api.generate(b64_str, WHITE_BG_PROMPT)
        if not urls:
            raise RuntimeError("API 未返回任何图片")

        out_ext = ".png" if fmt == "png" else ".jpg"
        stem = src_path.stem
        out_name = f"{stem}_白底{out_ext}"
        out_path = output_dir / out_name
        download_image(urls[0], out_path)
        result["output"] = str(out_path)
        logging.info(f"  ✅ 生成成功: {out_path.name}")

        bak_path = bak_dir / src_path.name
        bak_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(bak_path))
        logging.info(f"  📦 原图已移至: {bak_path.name}")

        result["success"] = True
        return result

    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        logging.error(f"  ❌ 处理失败: {err_msg}")
        result["error"] = err_msg
        return result


def main():
    log_file = LOG_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )

    print("=" * 56)
    print("  Etsy 白底产品图生成工具 v1.0")
    print("  豆包 Seedream 4.5 图生图")
    print("=" * 56)
    print()

    cfg = load_config()

    # 交互式路径配置
    for key, label, default_sub in [
        ("input_folder",  "📁 输入目录（原图）", "input"),
        ("output_folder", "📤 输出目录（白底图）", "output"),
        ("bak_folder",    "📦 备份目录（原图备份）", "bak"),
    ]:
        val = cfg.get(key, "").strip()
        while not val or not Path(val).is_dir():
            prompt = f"{label}"
            try:
                val = input(f"{prompt}: ").strip()
            except (EOFError, IOError):
                val = str(BASE_DIR / default_sub)
                Path(val).mkdir(exist_ok=True)
                print(f"  → 使用默认: {val}")
                break
            if not val:
                val = str(BASE_DIR / default_sub)
                Path(val).mkdir(exist_ok=True)
                print(f"  → 使用默认: {val}")
                break
            if not Path(val).is_dir():
                try:
                    Path(val).mkdir(parents=True, exist_ok=True)
                    print(f"  → 已创建目录: {val}")
                except Exception as e:
                    print(f"  ❌ 目录无效: {e}")
                    val = ""
                    continue
            break
        cfg[key] = val

    input_dir  = Path(cfg["input_folder"]).resolve() if Path(cfg["input_folder"]).is_absolute() else (BASE_DIR / cfg["input_folder"]).resolve()
    output_dir = Path(cfg["output_folder"]).resolve() if Path(cfg["output_folder"]).is_absolute() else (BASE_DIR / cfg["output_folder"]).resolve()
    bak_dir    = Path(cfg["bak_folder"]).resolve() if Path(cfg["bak_folder"]).is_absolute() else (BASE_DIR / cfg["bak_folder"]).resolve()

    print()
    print(f"输入目录: {input_dir}")
    print(f"输出目录: {output_dir}")
    print(f"备份目录: {bak_dir}")
    print()

    supported = {".jpg", ".jpeg", ".png", ".webp"}
    image_files = [p for p in input_dir.iterdir()
                   if p.suffix.lower() in supported]

    if not image_files:
        print("⚠️  输入目录中没有找到图片文件（支持: jpg, png, webp）")
        print(f"   请将图片放入: {input_dir}")
        try:
            input("\n按回车退出...")
        except (EOFError, IOError):
            pass
        return

    print(f"找到 {len(image_files)} 张图片待处理\n")

    api_key = cfg.get("api_key", "").strip()
    if not api_key:
        try:
            api_key = input("🔑 请输入 ARK API Key: ").strip()
        except (EOFError, IOError):
            api_key = ""
        if not api_key:
            print("❌ 未提供 API Key，退出。")
            try:
                input("\n按回车退出...")
            except (EOFError, IOError):
                pass
            return

    api = ArkProductAPI(
        api_key=api_key,
        endpoint_id=cfg.get("endpoint_id", "ep-20260420205419-xw8pv"),
        model=cfg.get("model", "doubao-seedream-4-5-251128"),
        image_size=cfg.get("image_size", "2K"),
        n=cfg.get("n", 1),
    )

    success_count = 0
    fail_count = 0
    results = []
    max_workers = max(1, int(cfg.get("max_workers", 2)))
    print(f"并发处理数: {max_workers}\n")

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(process_image, api, f, output_dir, bak_dir): f
            for f in sorted(image_files)
        }
        for i, future in enumerate(as_completed(futures), 1):
            src_path = futures[future]
            try:
                result = future.result()
                results.append(result)
                if result["success"]:
                    success_count += 1
                    print(f"[{i}/{len(image_files)}] ✅ {src_path.name} → {Path(result['output']).name}")
                else:
                    fail_count += 1
                    print(f"[{i}/{len(image_files)}] ❌ {src_path.name}: {result['error']}")
            except Exception as e:
                fail_count += 1
                print(f"[{i}/{len(image_files)}] ❌ {src_path.name}: {e}")

    print()
    print("=" * 56)
    print(f"  处理完成！")
    print(f"  ✅ 成功: {success_count} 张")
    print(f"  ❌ 失败: {fail_count} 张")
    print(f"  📤 白底图: {output_dir}")
    print(f"  📦 原图备份: {bak_dir}")
    print(f"  📋 日志: {log_file}")
    print("=" * 56)

    report_path = LOG_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "total": len(image_files),
            "success": success_count,
            "failed": fail_count,
            "results": results,
            "input_dir": str(input_dir),
            "output_dir": str(output_dir),
            "bak_dir": str(bak_dir),
        }, f, ensure_ascii=False, indent=2)
    print(f"\n📋 处理报告: {report_path}")

    try:
        input("\n按回车退出...")
    except (EOFError, IOError):
        pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断，退出。")
