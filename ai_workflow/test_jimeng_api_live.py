#!/usr/bin/env python3
"""
即梦 4.0 图生图接口联调测试（与生产 scf_pipeline 同路径）
- 使用 jimeng_generate + extract_image_b64
- 验证返回可解码为 PNG/JPEG 字节并落盘

用法:
  python3 test_jimeng_api_live.py
  python3 test_jimeng_api_live.py /path/to/input.png
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

# 与 SCF 一致：从本目录加载 scf_pipeline（及 config 兜底）
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))


def _default_test_image_bytes() -> bytes:
    """即梦会拒绝过小的输入图；生成 512×512 占位图（无 Pillow 时退化为灰度 raw PNG 思路会很长，故要求 Pillow）。"""
    from io import BytesIO

    from PIL import Image, ImageDraw

    im = Image.new("RGB", (512, 512), (240, 240, 245))
    d = ImageDraw.Draw(im)
    d.ellipse((156, 156, 356, 356), outline=(40, 40, 40), width=3)
    buf = BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _is_image_magic(b: bytes) -> str:
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if b[:2] == b"\xff\xd8":
        return "JPEG"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "WEBP"
    return "unknown"


def main() -> int:
    out_dir = _SCRIPT_DIR / "generated_images"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "jimeng_api_test_output.png"

    if len(sys.argv) > 1:
        src = Path(sys.argv[1]).expanduser().resolve()
        if not src.is_file():
            print(f"找不到输入文件: {src}", file=sys.stderr)
            return 1
        img_bytes = src.read_bytes()
        print(f"输入: {src} ({len(img_bytes)} bytes)")
    else:
        try:
            img_bytes = _default_test_image_bytes()
        except ImportError as e:
            print(
                "未指定输入且无法 import Pillow，请: pip install Pillow\n"
                "或: python3 test_jimeng_api_live.py /path/to/photo.png",
                file=sys.stderr,
            )
            return 1
        print(f"未指定输入，使用内置 512×512 测试 PNG ({len(img_bytes)} bytes)")

    # 延迟导入：会先加载腾讯文档 token（需 config 或环境变量）
    from scf_pipeline import (
        extract_image_b64,
        get_prompt,
        jimeng_generate,
    )

    img_b64_list = [base64.b64encode(img_bytes).decode()]
    # 与生产一致的一条 Prompt（非黑色宠物）
    prompt = get_prompt("宠物头像(见附图)", "银色")
    print(f"Prompt 长度: {len(prompt)} 字")

    print("调用即梦 CVSync2AsyncSubmitTask / CVSync2AsyncGetResult ...")
    try:
        result = jimeng_generate(img_b64_list, prompt, poll_interval=3, max_wait=600)
    except Exception as e:
        print(f"即梦调用失败: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 2

    try:
        b64_out = extract_image_b64(result)
    except Exception as e:
        print(f"解析图片字段失败: {e}", file=sys.stderr)
        print("原始 result keys:", result.keys(), file=sys.stderr)
        import json

        print(json.dumps(result, ensure_ascii=False, indent=2)[:4000], file=sys.stderr)
        return 3

    raw = base64.b64decode(b64_out[0])
    kind = _is_image_magic(raw)
    print(f"解码首帧: {len(raw)} bytes, 格式: {kind}")

    if kind == "unknown":
        print("警告: 魔数不像常见图片，仍写入文件供人工查看。", file=sys.stderr)

    # 若实为 JPEG，改扩展名
    if kind == "JPEG":
        out_path = out_path.with_suffix(".jpg")
    elif kind == "WEBP":
        out_path = out_path.with_suffix(".webp")

    out_path.write_bytes(raw)
    print(f"已保存: {out_path}")
    print("OK — 即梦 API 返回可解码图片数据。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
