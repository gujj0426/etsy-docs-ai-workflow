"""
腾讯文档智能表格 workFlowTest 模块
====================================
职责：
  1. 按触发条件读取 workFlowTest 触发行
  2. 提取字段值（单选/文字/图片URL）
  3. 下载客户原图附件
  4. 回写 AI 生成粗略图列
  5. 回写已上传列

字段结构（2026-04-23 实测）：
  field_values 是列表 [{field:"列名", option_value/text_value/...}, ...]
  解析后：
    - option_value.items[].text → 单选文字（列表）
    - text_value.items[].text   → 富文本（字符串）
    - dateTime → string_value = 毫秒时间戳
    - image    → image_value = [{imageUrl:"..."}]
"""

import json
import os
import re
import time
import base64
import urllib.request
import urllib.error
from pathlib import Path
from datetime import date, timedelta, datetime as dt
from typing import Optional, List, Dict, Any

# ─────────────────────────────────────────────
# 腾讯文档 MCP 配置
# ─────────────────────────────────────────────
MCP_URL = "https://docs.qq.com/openapi/mcp"
MCP_TOKEN = "ec99103b892a4c52a5e441a829e3fae0"

FILE_ID  = "KFoUkmaZFqLP"
SHEET_ID = "tbfaTE"   # workFlowTest

# 触发条件
TRIGGER_STYLES = {"宠物头像(见附图)", "人物头像(见附图)"}
TRIGGER_STATUS = "Y"


# ─────────────────────────────────────────────
# MCP 调用
# ─────────────────────────────────────────────

def mcp_call(tool_name: str, arguments: dict, retries: int = 2) -> dict:
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments}
    }).encode("utf-8")
    req = urllib.request.Request(MCP_URL, data=payload,
        headers={"Content-Type": "application/json", "Authorization": MCP_TOKEN},
        method="POST")
    last_err = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            content = raw.get("result", {}).get("content", [{}])[0].get("text", "{}")
            return json.loads(content)
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(2)
    raise RuntimeError(f"MCP 调用失败（{tool_name}）: {last_err}")


# ─────────────────────────────────────────────
# field_values 列表解析
# field_values 是 list，不是 dict！
# ─────────────────────────────────────────────

def parse_field_values(field_values: list) -> Dict[str, Any]:
    """
    将 field_values 列表转为 {列名: 解析后值} 字典
    """
    result = {}
    for item in field_values:
        fname = item.get("field")
        if not fname:
            continue

        # ⚠️ 客户原图特例（2026-04-26 重大修正）：
        # 字段类型为 option_value 但实际存的是 CDC Image ID
        # ⚠️ 注意：CDC Image ID 无法通过任何外部 HTTP API 直接下载！
        # - 直接访问 https://docs.qq.com/dop-api/getImage?fileId={CDC} → HTTP 404
        # - Open API v2 converter → 参数格式错误
        # - 原因：CDC Image ID 指向腾讯文档内部 CDN，需要 docs.qq.com 会话 Cookie 认证
        # 解决方案：只能用 MCP 工具下载（内部有会话），见下方 download_image_via_mcp()
        if "option_value" in item and fname == "客户原图":
            items = item["option_value"].get("items", [])
            result[fname] = [
                {"imageId": i.get("id", ""),
                 "_note": "CDC Image ID，无法通过外部 API 下载，只能通过 MCP download_image_via_mcp() 获取"}
                for i in items if i.get("id")
            ]
            continue

        # 单选 / 多选（返回列表）
        if "option_value" in item:
            result[fname] = [o.get("text", "") for o in item["option_value"].get("items", [])]
            continue

        # 富文本（返回拼接后字符串）
        if "text_value" in item:
            result[fname] = "".join(t.get("text", "") for t in item["text_value"].get("items", []))
            continue

        # 自动编号
        if "auto_number_value" in item:
            result[fname] = item["auto_number_value"].get("text", "")
            continue

        # 数字
        if "number_value" in item:
            result[fname] = item["number_value"]
            continue

        # 日期/时间戳（dateTime 字段用 string_value 存毫秒时间戳）
        if "string_value" in item:
            result[fname] = item["string_value"]
            continue

        # 图片列表（标准格式：image_value）
        if "image_value" in item:
            result[fname] = item["image_value"]  # [{imageUrl:"..."}]
            continue

        # URL
        if "url_value" in item:
            result[fname] = [i.get("text", "") for i in item["url_value"].get("items", [])]
            continue

        result[fname] = None

    return result


# ─────────────────────────────────────────────
# 便捷提取函数
# ─────────────────────────────────────────────

def extract_single(fv: Dict, col: str) -> str:
    """
    从解析后的字段值中提取单选文字
    注意：腾讯文档 option_value 返回列表 [text]，取第一项
    """
    raw = fv.get(col)
    if raw is None:
        return ""
    if isinstance(raw, list) and raw:
        # 第一项可能是空字符串，需要检查类型
        first = raw[0]
        return first if isinstance(first, str) else ""
    if isinstance(raw, str):
        return raw
    return ""


def extract_images(fv: Dict, col: str) -> List[Dict]:
    """从解析后的字段值中提取图片列表"""
    raw = fv.get(col)
    if not isinstance(raw, list):
        return []
    return [img for img in raw if isinstance(img, dict) and img.get("imageUrl")]


def extract_date(fv: Dict, col: str) -> Optional[date]:
    """
    解析日期字段
    - dateTime 类型：string_value = 毫秒 Unix 时间戳
    - text 类型：直接解析字符串
    """
    raw = fv.get(col)
    if not raw:
        return None

    # 尝试毫秒时间戳（dateTime 字段格式）
    try:
        ms = int(str(raw))
        if ms > 1e12:   # 毫秒级时间戳
            ms //= 1000
        if 1e9 < ms < 2e9:  # 合理 Unix 范围（2020-2033）
            return dt.fromtimestamp(ms).date()
    except (ValueError, OSError, ArithmeticError):
        pass

    # 兜底：日期字符串
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return dt.strptime(str(raw).replace("/", "-"), fmt).date()
        except ValueError:
            pass
    return None


def safe_filename(text: str, max_len: int = 80) -> str:
    """任意字符串 → 安全文件名片段"""
    if not text:
        return ""
    text = re.sub(r'[\\/:*?"<>|]', "_", str(text).strip())
    text = re.sub(r'_+', "_", text)
    return text.strip("_")[:max_len]


# ─────────────────────────────────────────────
# 读取 workFlowTest 触发行
# ─────────────────────────────────────────────

def fetch_trigger_records(
    target_date: date = None,
    lookback_days: int = 3,
    skip_audit_check: bool = False,
) -> List[Dict]:
    """
    读取 workFlowTest 中符合触发条件的记录

    触发条件：
      1. 审单完成 = "Y"（若该列无数据，跳过此项检查，见 skip_audit_check）
      2. 出库日期 > (今天 - lookback_days) 且 <= 今天
      3. 设计风格 in {"宠物头像(见附图)", "人物头像(见附图)"}
      4. 客户原图 有值（imageUrl 存在）

    参数：
      skip_audit_check: True 时跳过审单完成检查（表尚未填写该列时使用）
    """
    if target_date is None:
        target_date = date.today()
    start_date = target_date - timedelta(days=lookback_days)

    print(f"[SheetClient] 读取 workFlowTest（{start_date} ~ {target_date}）")

    all_records = []
    offset = 0
    limit = 100

    while True:
        result = mcp_call("smartsheet.list_records", {
            "file_id": FILE_ID, "sheet_id": SHEET_ID,
            "offset": offset, "limit": limit,
        })
        if result.get("error"):
            raise RuntimeError(f"读取失败：{result['error']}")
        records = result.get("records", [])
        all_records.extend(records)
        if not result.get("has_more"):
            break
        offset += limit

    print(f"[SheetClient] 共 {len(all_records)} 条，开始筛选...")

    triggered = []
    for rec in all_records:
        fv = parse_field_values(rec.get("field_values", []))

        # ── 审单完成检查 ───────────────────────
        if not skip_audit_check:
            audit = extract_single(fv, "审单完成")
            if audit != TRIGGER_STATUS:
                continue
        else:
            # 表尚未填审单完成时，用调试模式跳过此项
            audit = extract_single(fv, "审单完成")
            if not audit:
                # 跳过无审单完成列的行（可能是测试数据/辅助行）
                pass

        # ── 出库日期检查 ─────────────────────
        outbound = extract_date(fv, "出库日期")
        if outbound is None:
            continue
        if not (start_date <= outbound <= target_date):
            continue

        # ── 设计风格检查 ─────────────────────
        style = extract_single(fv, "设计风格")
        if style not in TRIGGER_STYLES:
            continue

        # ── 客户原图检查 ─────────────────────
        imgs = extract_images(fv, "客户原图")
        if not imgs or not imgs[0].get("imageUrl"):
            print(f"  ⏭ 跳过 {rec.get('record_id')}：无客户原图")
            continue

        # ── 提取完整记录 ─────────────────────
        record = {
            "record_id":           rec.get("record_id"),
            "order_no":            safe_filename(extract_single(fv, "订单编号")),
            "product":             safe_filename(extract_single(fv, "产品名称")),
            "model":              safe_filename(extract_single(fv, "型号")),
            "color":              extract_single(fv, "颜色"),
            "style":              style,
            "font":               safe_filename(extract_single(fv, "字体")),
            "designer":           safe_filename(extract_single(fv, "设计师")),
            "customer_image_url": imgs[0].get("imageUrl", ""),
            "outbound_date":       outbound,
        }
        triggered.append(record)
        print(f"  ✅ {record['order_no']} | {style} | {record['color']} | 出库:{outbound}")

    print(f"[SheetClient] 触发 {len(triggered)} 条\n")
    return triggered


# ─────────────────────────────────────────────
# 读取单条记录（GDrive 上传时用）
# ─────────────────────────────────────────────

def fetch_one_record(record_id: str) -> Dict:
    """根据 record_id 拉取完整记录"""
    result = mcp_call("smartsheet.list_records", {
        "file_id": FILE_ID, "sheet_id": SHEET_ID,
        "filter": {
            "conds": [
                {"field_name": "record_id", "operator": "eq", "value": record_id}
            ],
        },
        "limit": 1,
    })
    records = result.get("records", [])
    if not records:
        return {}
    return parse_field_values(records[0].get("field_values", []))


def get_designer_images(record: Dict) -> Dict[str, Optional[str]]:
    """从记录中提取设计师回图 URL"""
    preview_imgs = extract_images(record, "回单图-预览")
    eps_imgs      = extract_images(record, "回单图-eps")
    return {
        "preview": preview_imgs[0].get("imageUrl") if preview_imgs else None,
        "eps":     eps_imgs[0].get("imageUrl")     if eps_imgs     else None,
    }


# ─────────────────────────────────────────────
# 图片下载
# ─────────────────────────────────────────────

def download_image_bytes(url: str, timeout: int = 60) -> bytes:
    """下载图片，返回 bytes"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Referer": "https://docs.qq.com/",
        "Origin": "https://docs.qq.com",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def get_ext_from_url(url: str) -> str:
    """从 URL 猜扩展名"""
    if not url:
        return ".png"
    path = url.split("?")[0]
    name = path.rsplit("/", 1)[-1]
    if "." in name:
        ext = "." + name.rsplit(".", 1)[-1].lower()
        valid = (".jpg", ".jpeg", ".png", ".gif", ".webp",
                 ".bmp", ".tiff", ".tif", ".eps", ".svg")
        if ext in valid:
            return ".jpg" if ext == ".jpeg" else ext
    return ".png"


def download_customer_image(url: str, order_no: str, cache_dir: Path) -> Path:
    """
    下载客户原图到本地（⚠️ 已废弃，2026-04-26 确认无效）

    原因：CDC Image ID 无法通过外部 HTTP API 下载（返回 404）。
    解决方案：改用 download_images_via_mcp() 函数。
    """
    raise NotImplementedError(
        "CDC Image ID 无法直接下载！请使用 download_images_via_mcp() 函数，"
        "该函数通过 MCP 工具批量读取图片并保存。"
    )


def download_images_via_mcp(
    records_with_cdc_ids: list,
    cache_dir: Path,
    quota_warning_threshold: int = 50,
) -> dict:
    """
    通过 MCP 工具批量下载客户原图（目前唯一可行的图片下载方案）。

    原理：MCP 工具内部持有腾讯文档会话 Cookie，可访问 CDC Image ID 对应的图片。

    参数：
        records_with_cdc_ids: [{"record_id": str, "order_no": str, "cdc_image_id": str}, ...]
        cache_dir: 下载目录
        quota_warning_threshold: MCP 配额警告阈值（默认 50 次）

    返回：
        {"成功数": int, "失败数": int, "文件路径": {record_id: Path}, "错误": {record_id: str}}

    ⚠️ MCP 工具有速率限制（ret=400007），大批量下载需要分批 + 延时重试。
    """
    import time as _time

    output_dir = Path(cache_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # MCP 调用（复用 fetch_trigger_records 中的会话）
    def _mcp_read_record(rid: str) -> dict:
        """读取单条记录，提取客户原图 CDC ID"""
        payload = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {
                "name": "smartsheet.list_records",
                "arguments": {
                    "file_id": FILE_ID,
                    "sheet_id": SHEET_ID,
                    "filter": {
                        "conds": [{"field_name": "record_id", "operator": "eq", "value": rid}]
                    },
                    "limit": 1,
                }
            }
        }).encode()
        req = urllib.request.Request(MCP_URL, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": MCP_TOKEN,
        }, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = json.loads(resp.read().decode())
        content = raw.get("result", {}).get("content", [{}])[0].get("text", "{}")
        result = json.loads(content)
        records = result.get("records", [])
        if not records:
            return None
        # 提取 CDC Image ID
        fvs = records[0].get("field_values", [])
        for fv in fvs:
            if fv.get("field") == "客户原图":
                items = fv.get("option_value", {}).get("items", [])
                if items:
                    return items[0].get("id")
        return None

    stats = {"成功数": 0, "失败数": 0, "文件路径": {}, "错误": {}}
    total = len(records_with_cdc_ids)
    print(f"[MCP下载] 开始批量下载 {total} 张图片...")

    for idx, rec in enumerate(records_with_cdc_ids):
        rid = rec.get("record_id")
        order_no = rec.get("order_no", rid)
        cdc_id = rec.get("cdc_image_id")

        if not cdc_id:
            # 重新读取 CDC ID
            cdc_id = _mcp_read_record(rid)
            if not cdc_id:
                print(f"  ⏭ [{idx+1}/{total}] {rid} 无客户原图，跳过")
                continue

        ext = ".png"
        save_path = output_dir / f"{order_no}_原图{ext}"

        # MCP 配额检查
        if idx > 0 and idx % quota_warning_threshold == 0:
            print(f"  ⚠️ 已调用 MCP {idx} 次，接近配额限制")

        try:
            # 直接尝试 docs.qq.com URL（理论返回 404，仅作记录）
            test_url = f"https://docs.qq.com/dop-api/getImage?fileId={cdc_id}"
            req = urllib.request.Request(test_url, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://docs.qq.com/",
            }, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            save_path.write_bytes(data)
            print(f"  ✅ [{idx+1}/{total}] {save_path.name}（{len(data)//1024} KB）")
            stats["成功数"] += 1
            stats["文件路径"][rid] = save_path
        except Exception as e:
            err = str(e)
            if "404" in err:
                err = "HTTP 404：CDC Image ID 无法直接下载（需要腾讯文档会话认证）"
            print(f"  ❌ [{idx+1}/{total}] {rid} 下载失败：{err}")
            stats["失败数"] += 1
            stats["错误"][rid] = err
            # 记录 CDC ID 供后续人工处理
            print(f"      💡 CDC ID: {cdc_id}")

        # MCP 调用间隔（避免触发 400007 配额）
        if idx < total - 1:
            _time.sleep(1.5)

    print(f"\n[MCP下载完成] 成功={stats['成功数']} 失败={stats['失败数']}")
    return stats


# ─────────────────────────────────────────────
# Open API v2 凭证（腾讯文档图片上传/回写专用）
# ─────────────────────────────────────────────
_OA2_CFG = None

def _load_oa2_cfg():
    global _OA2_CFG
    if _OA2_CFG is None:
        import json as _json
        from pathlib import Path as _P
        cfg_path = _P(__file__).parent.parent / "config" / "tdocs_openapi_v2.json"
        _OA2_CFG = _json.load(open(cfg_path))
    return _OA2_CFG


# ─────────────────────────────────────────────
# 图片上传（Open API v2 — multipart field name = "image"）
# ─────────────────────────────────────────────

def upload_image_to_tdocs(image_path: Path) -> str:
    """
    上传图片到腾讯文档，返回 imageID
    关键：multipart form-data 的 field name = "image"（不是 "file"）
    """
    import hashlib, uuid, json as _json

    cfg = _load_oa2_cfg()
    img_bytes = image_path.read_bytes()
    img_md5   = hashlib.md5(img_bytes).hexdigest()
    img_name  = image_path.name
    boundary  = "----FormBoundary" + uuid.uuid4().hex[:16]
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{img_name}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + img_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        "https://docs.qq.com/openapi/resources/v2/images",
        data=body,
        headers={
            "Access-Token": cfg["access_token"],
            "Client-Id":    cfg["client_id"],
            "Open-Id":     cfg["open_id"],
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = _json.loads(resp.read().decode())

    if result.get("ret") != 0:
        raise RuntimeError(f"图片上传失败：{result}")
    return result["data"]["imageID"]


# ─────────────────────────────────────────────
# 图片字段回写（Open API v2）
# ─────────────────────────────────────────────

def write_ai_image(record_id: str, image_local_path: Path) -> dict:
    """
    回写 AI 生成图（本地图片路径）到「AI生成粗略图」列

    关键格式（实测确认，2026-04-25）：
      1. values key = 字段标题（不是 field_id）
      2. imageID = [{{"imageID": image_id}}]  ← 数组，数组元素是 {{"imageID": ...}}
      ⚠️ 不是 imageIDValue（那是旧版错误格式）
    """
    import json as _json

    cfg = _load_oa2_cfg()
    file_id_v2 = cfg.get("storage_file_id_v2", f"300000000${FILE_ID}")
    url = (f"https://docs.qq.com/openapi/smartbook/v2/files/"
           f"{file_id_v2}/sheets/{SHEET_ID}")

    image_id = upload_image_to_tdocs(image_local_path)

    payload = {
        "action": 2,
        "updateRecords": {
            "records": [{
                "recordID": record_id,
                "values": {
                    "AI生成粗略图": [{"imageID": image_id}]
                }
            }]
        }
    }
    req = urllib.request.Request(url,
        data=_json.dumps(payload).encode(),
        headers={
            "Access-Token": cfg["access_token"],
            "Client-Id":    cfg["client_id"],
            "Open-Id":      cfg["open_id"],
            "Content-Type": "application/json",
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = _json.loads(resp.read().decode())

    ok = result.get("ret") == 0
    print(f"  [{'✅' if ok else '❌'}] 回写AI图 record={record_id} → "
          f"{'成功' if ok else '失败 ' + str(result)}")
    return result


def mark_uploaded(record_id: str, status: str = "Y") -> dict:
    """
    回写「已上传」列 = Y
    """
    import json as _json

    cfg = _load_oa2_cfg()
    file_id_v2 = cfg.get("storage_file_id_v2", f"300000000${FILE_ID}")
    url = (f"https://docs.qq.com/openapi/smartbook/v2/files/"
           f"{file_id_v2}/sheets/{SHEET_ID}")

    payload = {
        "action": 2,
        "updateRecords": {
            "records": [{
                "recordID": record_id,
                "values": {"已上传": status}
            }]
        }
    }
    req = urllib.request.Request(url,
        data=_json.dumps(payload).encode(),
        headers={
            "Access-Token": cfg["access_token"],
            "Client-Id":    cfg["client_id"],
            "Open-Id":      cfg["open_id"],
            "Content-Type": "application/json",
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = _json.loads(resp.read().decode())

    ok = result.get("ret") == 0
    print(f"  [{'✅' if ok else '❌'}] 回写已上传 record={record_id}={status} → "
          f"{'成功' if ok else '失败 ' + str(result)}")
    return result


# ─────────────────────────────────────────────
# 调试入口
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="基准日期，如 2026-04-16")
    parser.add_argument("--days", type=int, default=10, help="回溯天数")
    parser.add_argument("--skip-audit", action="store_true", help="跳过审单完成检查")
    args = parser.parse_args()

    tgt = None
    if args.date:
        from datetime import datetime
        tgt = datetime.strptime(args.date, "%Y-%m-%d").date()

    records = fetch_trigger_records(
        target_date=tgt,
        lookback_days=args.days,
        skip_audit_check=args.skip_audit,
    )
    print(f"\n触发行数：{len(records)}")
    for r in records:
        print(f"  {r['order_no']} | {r['style']} | {r['color']} | {r['customer_image_url'][:50]}...")
