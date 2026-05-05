#!/usr/bin/env python3
"""
腾讯文档智能表格 - 图片下载脚本
功能：从指定 sheet 读取图片字段，按「订单编号_产品名_颜色_id」命名后保存到本地
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path


# ==================== 配置 ====================
MCP_URL = "https://docs.qq.com/openapi/mcp"
MCP_TOKEN = "ec99103b892a4c52a5e441a829e3fae0"

FILE_ID = "KFoUkmaZFqLP"      # 库存管理系统
SHEET_ID = "t5u9lX"           # test 页（实际使用时换成目标 sheet）

# 字段名映射（如表格列名不同，改这里即可）
COL_ORDER_NO = "订单编号"
COL_PRODUCT  = "产品名"
COL_COLOR    = "颜色"
COL_ID       = "id"
COL_IMAGE    = "图片"

# 下载输出目录
OUTPUT_DIR = Path(__file__).parent / "downloaded_images"


# ==================== 工具函数 ====================

def mcp_call(tool_name: str, arguments: dict) -> dict:
    """调用腾讯文档 MCP 工具，返回解析后的 JSON 结果"""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments}
    }).encode("utf-8")

    req = urllib.request.Request(
        MCP_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": MCP_TOKEN,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    # MCP 响应结构：result.content[0].text → JSON 字符串
    content = raw.get("result", {}).get("content", [{}])[0].get("text", "{}")
    return json.loads(content)


def safe_filename_part(value) -> str:
    """把任意值转成安全的文件名片段（去掉非法字符，截断过长）"""
    if value is None:
        return "unknown"
    text = str(value).strip()
    # 去掉文件系统不允许的字符
    text = re.sub(r'[\\/:*?"<>|]', "_", text)
    # 截断
    return text[:40] if text else "unknown"


def extract_text(field_value) -> str:
    """从智能表格字段值中提取文字"""
    if field_value is None:
        return "unknown"
    # 自动编号：{"seq": "1", "text": "20260419001"}
    if isinstance(field_value, dict):
        return field_value.get("text") or field_value.get("seq") or str(field_value)
    # 单选/多选：[{"text": "银色", ...}]
    if isinstance(field_value, list) and field_value and isinstance(field_value[0], dict):
        return field_value[0].get("text", "unknown")
    # 数字 / 纯字符串
    return str(field_value)


def download_image(url: str, save_path: Path):
    """下载图片到指定路径（腾讯文档图片需要带 Referer 才能访问）"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://docs.qq.com/",
        "Origin": "https://docs.qq.com",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(resp.read())


# ==================== 主逻辑 ====================

def fetch_records(file_id: str, sheet_id: str) -> list:
    """分页拉取 sheet 全量记录"""
    all_records = []
    offset = 0
    limit = 100
    while True:
        result = mcp_call("smartsheet.list_records", {
            "file_id": file_id,
            "sheet_id": sheet_id,
            "offset": offset,
            "limit": limit,
        })
        if result.get("error"):
            print(f"[错误] 获取记录失败：{result['error']}")
            break
        records = result.get("records", [])
        all_records.extend(records)
        if not result.get("has_more"):
            break
        offset += limit
    return all_records


def process_record(record: dict, output_dir: Path) -> dict:
    """处理单条记录，下载图片并以指定格式命名"""
    fv = record.get("field_values", {})

    order_no  = safe_filename_part(extract_text(fv.get(COL_ORDER_NO)))
    product   = safe_filename_part(extract_text(fv.get(COL_PRODUCT)))
    color     = safe_filename_part(extract_text(fv.get(COL_COLOR)))
    row_id    = safe_filename_part(extract_text(fv.get(COL_ID)))

    images = fv.get(COL_IMAGE, [])
    if not images:
        return {"record_id": record.get("record_id"), "status": "skip", "reason": "无图片"}

    results = []
    for idx, img in enumerate(images):
        url = img.get("imageUrl") or img.get("url")
        if not url:
            continue

        # 从 URL 猜扩展名，兜底用 .jpg
        ext = ".jpg"
        url_path = url.split("?")[0]
        if "." in url_path.split("/")[-1]:
            ext = "." + url_path.split("/")[-1].rsplit(".", 1)[-1].lower()
            if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                ext = ".jpg"

        suffix = f"_{idx+1}" if len(images) > 1 else ""
        filename = f"{order_no}_{product}_{color}_{row_id}{suffix}{ext}"
        save_path = output_dir / filename

        try:
            download_image(url, save_path)
            print(f"  ✅ 已保存：{filename}")
            results.append({"file": str(save_path), "status": "ok"})
        except Exception as e:
            print(f"  ❌ 下载失败：{filename} → {e}")
            results.append({"file": filename, "status": "error", "reason": str(e)})

    return {"record_id": record.get("record_id"), "images": results}


def main(file_id=FILE_ID, sheet_id=SHEET_ID, output_dir=OUTPUT_DIR):
    print(f"[开始] file_id={file_id}  sheet_id={sheet_id}")
    print(f"[输出目录] {output_dir}")

    records = fetch_records(file_id, sheet_id)
    print(f"[读取] 共 {len(records)} 条记录\n")

    output_dir = Path(output_dir)
    stats = {"ok": 0, "skip": 0, "error": 0}

    for rec in records:
        result = process_record(rec, output_dir)
        status = result.get("status")
        if status == "skip":
            print(f"  ⏭ 跳过 {result['record_id']}：{result['reason']}")
            stats["skip"] += 1
        else:
            for img in result.get("images", []):
                if img["status"] == "ok":
                    stats["ok"] += 1
                else:
                    stats["error"] += 1

    print(f"\n[完成] 成功={stats['ok']}  跳过={stats['skip']}  失败={stats['error']}")


if __name__ == "__main__":
    # 支持命令行传参覆盖默认值
    # 用法：python download_sheet_images.py [file_id] [sheet_id] [output_dir]
    fid   = sys.argv[1] if len(sys.argv) > 1 else FILE_ID
    sid   = sys.argv[2] if len(sys.argv) > 2 else SHEET_ID
    odir  = sys.argv[3] if len(sys.argv) > 3 else OUTPUT_DIR
    main(fid, sid, odir)
