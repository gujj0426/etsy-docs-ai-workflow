#!/usr/bin/env python3
"""
腾讯文档 Open API v2 — 完整验证脚本
测试目标：
  1. 读取 workFlowTest 触发行
  2. 提取 imageUrl，下载图片
  3. 确认完整链路可用
"""

import json
import os
import re
import time
import zipfile
import urllib.request
import urllib.error
from datetime import date, timedelta, timezone as tz, datetime as dt
from pathlib import Path
from urllib.parse import unquote

# ── 凭证 ──────────────────────────────────────────────
TOKEN     = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjbHQiOiJjNmEzNDBlMTg3MzU0YWY4OTgwMTE4Y2VmOWQzZWJiZiIsInR5cCI6MSwiZXhwIjoxNzc5NTE2NzYzLjgzNjQxMzksImlhdCI6MTc3NjkyNDc2My44MzY0MTM5LCJzdWIiOiI0ZDJmZTJkODNkZDQ0N2I5ODI1MzVkOWQ2YmExNGMzNyJ9.Vj3LVTfVl6iQAG_1QEZVIHwxip-CABAEt-h8xdZaf_E"
CLIENT_ID = "c6a340e187354af8980118cef9d3ebbf"
OPEN_ID   = "4d2fe2d83dd447b982535d9d6ba14c37"
OA2_FILE  = "300000000$KFoUkmaZFqLP"
SHEET_ID  = "tbfaTE"
CST = tz(timedelta(hours=8))

# ── 触发条件 ──────────────────────────────────────────
TRIGGER_STYLES = {"宠物头像(见附图)", "人物头像(见附图)"}
LOOKBACK_DAYS   = 3
OUTPUT_DIR      = Path(__file__).parent / "verify_output"
# 设具体日期可扫描历史，None = 今天
TEST_DATE       = None  # None=今天，或 "2026-04-25"

# ── API 头 ─────────────────────────────────────────────
def api_headers():
    return {
        "Access-Token": TOKEN,
        "Client-Id":    CLIENT_ID,
        "Open-Id":      OPEN_ID,
        "Content-Type": "application/json",
    }

def api_post(path, payload):
    url  = f"https://docs.qq.com{path}"
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=data, headers=api_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

# ── 日期解析 ───────────────────────────────────────────
def parse_ts_ms(raw):
    """解析腾讯文档毫秒时间戳"""
    if not raw:
        return None
    try:
        ms = int(str(raw))
        if ms > 1e15:
            ms //= 1000
        if 1e9 < ms < 2e10:
            return dt.fromtimestamp(ms, CST).date()
    except:
        pass
    return None

# ── 字段解析 ───────────────────────────────────────────
def get_text(values, key):
    items = values.get(key, [])
    if isinstance(items, list):
        return "".join(i.get("text", "") for i in items)
    if isinstance(items, str):
        return items
    return ""

def get_single_select(values, key):
    items = values.get(key, [])
    if isinstance(items, list) and items:
        return items[0].get("text", "")
    return ""

def get_images(values, key):
    imgs = values.get(key, [])
    if not isinstance(imgs, list):
        return []
    result = []
    for img in imgs:
        if not isinstance(img, dict):
            continue
        img_url = img.get("imageUrl") or ""
        if not img_url:
            continue
        # 去掉尺寸参数，保留原图
        clean_url = img_url.split("?")[0] if "?" in img_url else img_url
        result.append({
            "id":   img.get("id", ""),
            "url":  clean_url,
            "title": img.get("title", ""),
        })
    return result

# ── 过滤触发行 ─────────────────────────────────────────
def fetch_and_filter():
    target_date = TEST_DATE or str(dt.now(CST).date())
    tgt_date = dt.strptime(target_date, "%Y-%m-%d").date()
    start    = tgt_date - timedelta(days=LOOKBACK_DAYS)

    print(f"=== 拉取 workFlowTest ({start} ~ {tgt_date}) ===")

    all_records = []
    offset = 0
    limit  = 100

    while True:
        result = api_post(
            f"/openapi/smartbook/v2/files/{OA2_FILE}/sheets/{SHEET_ID}",
            {"getRecords": {"offset": offset, "limit": limit}}
        )
        if result.get("ret") != 0:
            raise RuntimeError(f"API 失败 ret={result.get('ret')} msg={result.get('msg')}")

        block = result.get("data", {}).get("getRecords", {})
        records = block.get("records", [])
        all_records.extend(records)
        has_more = block.get("hasMore", False)

        print(f"  offset={offset} |本页 {len(records)} 条|累计 {len(all_records)} 条|hasMore={has_more}")

        if not has_more:
            break
        offset += limit

    print(f"共 {len(all_records)} 条记录，开始筛选...")

    triggered = []
    for rec in all_records:
        values  = rec.get("values", {})
        audit   = get_single_select(values, "审单完成")
        outdate = parse_ts_ms(values.get("出库日期"))
        style   = get_single_select(values, "设计风格")

        is_trigger = (
            audit == "Y"
            and outdate is not None
            and start < outdate <= tgt_date
            and style in TRIGGER_STYLES
        )

        customer_imgs = get_images(values, "客户原图")
        if not customer_imgs:
            continue

        order_no = get_text(values, "订单编号")
        triggered.append({
            "record_id": rec.get("recordId", ""),
            "order_no":  re.sub(r'[\\/:*?"<>|]', "_", order_no.strip()),
            "product":   get_single_select(values, "产品名称"),
            "style":     style,
            "color":     get_single_select(values, "颜色"),
            "outdate":   str(outdate),
            "customer_imgs": customer_imgs,
            "ai_imgs":   get_images(values, "AI生成粗略图"),
            "preview_imgs": get_images(values, "回单图-预览"),
            "eps_imgs":   get_images(values, "回单图-eps"),
        })
        print(f"  ✅ 触发行 {rec.get('recordId')} | {order_no} | {style} | 出库{outdate}")

    print(f"\n共触发 {len(triggered)} 条")
    return triggered

# ── 下载图片 ───────────────────────────────────────────
REFERRER = "https://docs.qq.com/"

def download_img(url, save_path):
    """带 Referer 头下载图片"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Referer":   REFERRER,
        "Origin":    "https://docs.qq.com",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(resp.read())

# ── 主验证流程 ─────────────────────────────────────────
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("腾讯文档 Open API v2 — 完整链路验证")
    print("=" * 60)

    # Step 1: 读取并筛选
    triggered = fetch_and_filter()

    if not triggered:
        print("\n⚠️ 没有触发行（检查日期范围或设计风格）")
        return

    # Step 2: 下载图片
    total_ok = 0
    total_fail = 0

    for rec in triggered:
        order_dir = OUTPUT_DIR / rec["order_no"]
        order_dir.mkdir(exist_ok=True)

        groups = [
            ("01_客户原图",  rec["customer_imgs"]),
            ("02_AI生成图",  rec["ai_imgs"]),
            ("03_回单预览",  rec["preview_imgs"]),
            ("04_回单EPS",   rec["eps_imgs"]),
        ]

        for group_name, imgs in groups:
            for idx, img in enumerate(imgs):
                url = img["url"]
                title = img.get("title", "")
                ext = Path(title).suffix.lower() if title else ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    ext = ".jpg"

                fname = f"{group_name}_{idx+1}{ext}"
                save_path = order_dir / fname

                if save_path.exists():
                    print(f"  ⏭  已缓存: {fname}")
                    total_ok += 1
                    continue

                try:
                    download_img(url, save_path)
                    size = save_path.stat().st_size
                    print(f"  ✅ {fname} ({size//1024} KB)")
                    total_ok += 1
                except Exception as e:
                    print(f"  ❌ 下载失败 {fname}: {e}")
                    total_fail += 1

    # Step 3: 打包
    print(f"\n=== 打包（共 {total_ok} 张，失败 {total_fail} 张）===")
    if total_ok == 0:
        print("⚠️ 无成功图片，跳过打包")
        return

    zip_name = f"verify_{TEST_DATE or str(date.today())}.zip"
    zip_path = OUTPUT_DIR / zip_name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for img in OUTPUT_DIR.rglob("*.png"):
            if img.name == zip_name:
                continue
            zf.write(img, img.relative_to(OUTPUT_DIR))
        for img in OUTPUT_DIR.rglob("*.jpg"):
            if img.name == zip_name:
                continue
            zf.write(img, img.relative_to(OUTPUT_DIR))
        for img in OUTPUT_DIR.rglob("*.jpeg"):
            if img.name == zip_name:
                continue
            zf.write(img, img.relative_to(OUTPUT_DIR))

    zip_size = zip_path.stat().st_size
    print(f"\n✅ 完成！")
    print(f"   zip: {zip_path}")
    print(f"   大小: {zip_size/1024:.1f} KB")


if __name__ == "__main__":
    main()
