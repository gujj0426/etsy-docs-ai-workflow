#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
archive_compress_outlet.py
==========================
出库明细「归档 + 合并压缩」定时脚本
每月1日自动执行，将「3、美国仓库出库明细」中3个月以前的数据：
  1. 备份到「出库明细-历史归档」工作表（保留全部字段）
  2. 原始明细按 [产品名称, 型号, 颜色, 产品变量] 四维合并，数量累加
  3. 删除原始3个月前的明细行，写入合并后的汇总行

执行方式：
  python3 archive_compress_outlet.py [--dry-run] [--file-id FILE_ID] [--archive-months N]

参数：
  --dry-run          只打印计划，不实际修改数据
  --file-id          目标文件ID（默认：KFoUkmaZFqLP）
  --archive-months   归档几个月以前的数据（默认：3）
  --source-sheet     源工作表sheet_id（默认：tWOjoH）
  --backup-sheet-title 备份工作表标题（默认：出库明细-历史归档）
"""

import argparse
import sys
import json
import time
import requests
import traceback
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# ─────────────────────── 配置 ──────────────────────────────────────────
CONFIG_FILE = "/Users/mac/Desktop/etsy/运营文档/config/tdocs_openapi_v2.json"

DEFAULT_FILE_ID  = "KFoUkmaZFqLP"           # 正本
DEFAULT_SHEET_ID = "tWOjoH"                  # 3、美国仓库出库明细-可心填
BACKUP_SHEET_TITLE = "出库明细-历史归档"
ARCHIVE_MONTHS = 3

API_BASE = "https://docs.qq.com"

# 分组 key 列（4维度）
GROUP_KEYS = ["产品名称", "型号", "颜色", "产品变量"]

# 数量字段
QTY_FIELD = "数量"

# 日期字段
DATE_FIELD = "出库日期"

BATCH_SIZE = 50   # MCP/API 单次操作最大行数
# ─────────────────────────────────────────────────────────────────────

tz_cn = timezone(timedelta(hours=8))


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def make_headers(cfg):
    return {
        "Access-Token": cfg["access_token"],
        "Client-Id":    cfg["client_id"],
        "Open-Id":      cfg["open_id"],
        "Content-Type": "application/json",
    }


def api_post(path, body, cfg):
    """通用 Open API v2 POST"""
    url = f"{API_BASE}{path}"
    resp = requests.post(url, headers=make_headers(cfg), json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    ret = data.get("ret", data.get("code", 0))
    if ret != 0:
        raise RuntimeError(f"API error ret={ret} msg={data.get('msg','')}: {data}")
    return data


def api_get(path, params, cfg):
    url = f"{API_BASE}{path}"
    resp = requests.get(url, headers=make_headers(cfg), params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    ret = data.get("ret", data.get("code", 0))
    if ret != 0:
        raise RuntimeError(f"API error ret={ret} msg={data.get('msg','')}: {data}")
    return data


def fmt_file_id(file_id):
    """Open API fileID 需加 300000000$ 前缀"""
    if not file_id.startswith("300000000$"):
        return f"300000000${file_id}"
    return file_id


def parse_date_ts(raw_value):
    """
    解析出库日期字段。
    raw 可能是:
      - 13位毫秒字符串 "1767110400000"
      - 已是秒级整数
      - None / 空
    返回 date 对象，或 None
    """
    if not raw_value:
        return None
    try:
        ts = int(raw_value)
        if ts > 1e12:
            ts = ts // 1000
        dt = datetime.fromtimestamp(ts, tz=tz_cn)
        return dt.date()
    except Exception:
        return None


def get_all_records(file_id, sheet_id, cfg):
    """
    分页读取全部记录，返回 list of dict:
    [{"record_id": "r...", "fields": {"字段名": 值, ...}}, ...]
    """
    fid = fmt_file_id(file_id)
    path = f"/openapi/smartbook/v2/files/{fid}/sheets/{sheet_id}"
    all_records = []
    offset = 0
    limit = 100

    while True:
        body = {"getRecords": {"offset": offset, "limit": limit}}
        data = api_post(path, body, cfg)
        # Open API v2 响应路径：data["data"]["getRecords"]["records"]
        records_raw = data["data"]["getRecords"]["records"]

        for r in records_raw:
            record_id = r.get("recordID")
            values = r.get("values", {})
            # 统一提取成字符串/数字
            fields = {}
            for field_name, fv in values.items():
                fields[field_name] = extract_field_value(field_name, fv)
            all_records.append({"record_id": record_id, "fields": fields})

        if len(records_raw) < limit:
            break
        offset += limit
        time.sleep(0.2)  # 避免触发频率限制

    return all_records


def extract_field_value(field_name, fv):
    """
    从 Open API v2 getRecords 返回值中提取可读值。
    支持 text/select/number/date 等多种类型。
    字段格式（实测确认）：
      - singleSelect: [{'id': '...', 'text': '选项文字', 'style': N}]
      - 多选（multi-select）: [{'id': '...', 'text': '选项1', ...}, ...]
      - number: int/float 直接返回
      - dateTime: 字符串 '1767110400000'（13位毫秒）
      - text: str
      - 图片/附件: list of dict
    """
    if fv is None:
        return None

    # singleSelect / multi-select: 返回 [{...}]，需要提取 text
    if isinstance(fv, list):
        if fv and isinstance(fv[0], dict):
            texts = [item.get("text", "") for item in fv if isinstance(item, dict)]
            if texts:
                return ",".join(texts)
        return str(fv)

    if isinstance(fv, (int, float)):
        return fv

    if isinstance(fv, str):
        return fv

    if isinstance(fv, dict):
        # number 类型（少见，备用）
        if "number" in fv:
            return fv["number"]
        return str(fv)

    return fv


def get_all_records_mcp_style(file_id, sheet_id, cfg):
    """
    备用：用 MCP list_records 兼容格式读取（直接调用 Open API，但解析 MCP 兼容格式）
    实际上我们统一用 Open API v2，这里只是 fallback
    """
    return get_all_records(file_id, sheet_id, cfg)


def get_sheet_list(file_id, cfg):
    """获取文件的所有工作表"""
    fid = fmt_file_id(file_id)
    path = f"/openapi/smartbook/v2/files/{fid}/sheets"
    data = api_post(path, {"getSheets": {}}, cfg)
    return data.get("getSheets", {}).get("sheets", [])


def create_backup_sheet(file_id, cfg, title=BACKUP_SHEET_TITLE):
    """
    在文件中创建备份工作表（如已存在则直接返回其 sheet_id）
    """
    fid = fmt_file_id(file_id)
    # 先检查是否存在
    sheets = get_sheet_list(file_id, cfg)
    for s in sheets:
        if s.get("title") == title:
            print(f"  备份表已存在：{title}（sheet_id={s['sheetID']}）")
            return s["sheetID"]

    # 创建新表
    path = f"/openapi/smartbook/v2/files/{fid}/sheets"
    body = {"addSheets": {"sheets": [{"title": title}]}}
    data = api_post(path, body, cfg)
    new_sheets = data.get("addSheets", {}).get("sheets", [])
    if new_sheets:
        sid = new_sheets[0]["sheetID"]
        print(f"  创建备份表成功：{title}（sheet_id={sid}）")
        return sid
    raise RuntimeError("创建备份表失败")


def get_sheet_fields(file_id, sheet_id, cfg):
    """获取工作表字段列表"""
    fid = fmt_file_id(file_id)
    path = f"/openapi/smartbook/v2/files/{fid}/sheets/{sheet_id}"
    data = api_post(path, {"getFields": {"offset": 0, "limit": 200}}, cfg)
    return data.get("getFields", {}).get("fields", [])


def add_fields_to_backup(file_id, backup_sheet_id, source_fields, cfg):
    """
    将源表字段复制到备份表（仅文本/数字类型，图片等跳过）
    """
    fid = fmt_file_id(file_id)
    path = f"/openapi/smartbook/v2/files/{fid}/sheets/{backup_sheet_id}"
    existing = get_sheet_fields(file_id, backup_sheet_id, cfg)
    existing_titles = {f["title"] for f in existing}

    fields_to_add = []
    for f in source_fields:
        title = f.get("title", "")
        ftype = f.get("type", "text")
        if title in existing_titles:
            continue
        # 只同步简单类型，复杂类型（公式、关联等）降级为 text
        simple_types = {"text", "number"}
        mapped_type = "text" if ftype not in simple_types else ftype
        fields_to_add.append({"title": title, "type": mapped_type})

    if not fields_to_add:
        print("  备份表字段已完整，无需新增")
        return

    body = {"addFields": {"fields": fields_to_add}}
    api_post(path, body, cfg)
    print(f"  备份表新增 {len(fields_to_add)} 个字段")


def write_records_to_backup(file_id, backup_sheet_id, records, cfg, dry_run=False):
    """
    将记录写入备份工作表（分批）
    records: list of {"record_id": ..., "fields": {...}}
    """
    if not records:
        print("  无需备份（无符合条件的记录）")
        return

    fid = fmt_file_id(file_id)
    path = f"/openapi/smartbook/v2/files/{fid}/sheets/{backup_sheet_id}"

    total = len(records)
    written = 0

    for i in range(0, total, BATCH_SIZE):
        batch = records[i:i+BATCH_SIZE]
        api_records = []
        for r in batch:
            values = {}
            for fname, fval in r["fields"].items():
                if fval is None:
                    continue
                if isinstance(fval, (int, float)):
                    values[fname] = fval
                else:
                    values[fname] = str(fval)
            api_records.append({"values": values})

        if dry_run:
            print(f"  [DRY-RUN] 将写入备份表 {len(batch)} 条记录（批次 {i//BATCH_SIZE+1}）")
        else:
            body = {"addRecords": {"records": api_records}}
            api_post(path, body, cfg)
            written += len(batch)
            print(f"  已备份 {written}/{total} 条记录...")
            time.sleep(0.3)

    if not dry_run:
        print(f"  ✅ 备份完成，共写入 {total} 条记录")


def delete_records_batch(file_id, sheet_id, record_ids, cfg, dry_run=False):
    """分批删除记录"""
    if not record_ids:
        return

    fid = fmt_file_id(file_id)
    path = f"/openapi/smartbook/v2/files/{fid}/sheets/{sheet_id}"
    total = len(record_ids)
    deleted = 0

    for i in range(0, total, BATCH_SIZE):
        batch = record_ids[i:i+BATCH_SIZE]
        if dry_run:
            print(f"  [DRY-RUN] 将删除 {len(batch)} 条原始记录（批次 {i//BATCH_SIZE+1}）")
        else:
            body = {"deleteRecords": {"recordIDs": batch}}
            api_post(path, body, cfg)
            deleted += len(batch)
            print(f"  已删除 {deleted}/{total} 条原始记录...")
            time.sleep(0.3)


def add_merged_records(file_id, sheet_id, merged_records, cfg, dry_run=False):
    """
    写入合并后的汇总行
    merged_records: list of {"产品名称": ..., "型号": ..., "颜色": ..., "产品变量": ..., "数量": N, "备注": "..."}
    """
    if not merged_records:
        return

    fid = fmt_file_id(file_id)
    path = f"/openapi/smartbook/v2/files/{fid}/sheets/{sheet_id}"
    total = len(merged_records)
    written = 0

    for i in range(0, total, BATCH_SIZE):
        batch = merged_records[i:i+BATCH_SIZE]
        api_records = []
        for r in batch:
            values = {}
            for k, v in r.items():
                if v is None:
                    continue
                values[k] = v
            api_records.append({"values": values})

        if dry_run:
            print(f"  [DRY-RUN] 将写入合并汇总 {len(batch)} 条记录（批次 {i//BATCH_SIZE+1}）")
            for r in batch[:3]:
                print(f"    示例: {r}")
        else:
            body = {"addRecords": {"records": api_records}}
            api_post(path, body, cfg)
            written += len(batch)
            print(f"  已写入合并行 {written}/{total}...")
            time.sleep(0.3)


def compute_cutoff_date(months=3):
    """
    计算截止日期：今天往前 N 个月的第一天
    例：今天是 2026-04-30，N=3，截止日期 = 2026-01-01（含）
    即：出库日期 < 2026-01-01（不含当月及之后）的数据才被归档
    """
    today = datetime.now(tz=tz_cn).date()
    # 往前 N 个月
    year = today.year
    month = today.month - months
    while month <= 0:
        month += 12
        year -= 1
    # 当月第一天
    cutoff = today.replace(year=year, month=month, day=1)
    return cutoff


def run(args):
    print(f"\n{'='*60}")
    print(f"出库明细归档压缩 {'[DRY-RUN 模式]' if args.dry_run else '[正式执行]'}")
    print(f"目标文件: {args.file_id}")
    print(f"源工作表: {args.source_sheet}")
    print(f"归档月数: {args.archive_months} 个月前")
    print(f"{'='*60}")

    cfg = load_config()

    # 1. 计算截止日期
    cutoff = compute_cutoff_date(args.archive_months)
    print(f"\n[1] 截止日期: {cutoff}（早于此日期的出库记录将被归档压缩）")

    # 2. 读取全部记录
    print(f"\n[2] 读取源工作表全部记录...")
    all_records = get_all_records(args.file_id, args.source_sheet, cfg)
    print(f"    共读取 {len(all_records)} 条记录")

    # 3. 筛选出需要归档的记录（出库日期 < cutoff）
    to_archive = []
    to_keep = []
    no_date_count = 0

    for r in all_records:
        raw_date = r["fields"].get(DATE_FIELD)
        d = parse_date_ts(raw_date)
        if d is None:
            no_date_count += 1
            to_keep.append(r)
            continue
        if d < cutoff:
            to_archive.append(r)
        else:
            to_keep.append(r)

    print(f"    需归档（{cutoff} 前）: {len(to_archive)} 条")
    print(f"    保留（{cutoff} 后）:  {len(to_keep)} 条")
    if no_date_count > 0:
        print(f"    无出库日期（保留）: {no_date_count} 条")

    if not to_archive:
        print("\n⚠️  没有需要归档的数据，脚本退出。")
        return

    # 4. 获取/创建备份工作表
    print(f"\n[3] 准备备份工作表「{args.backup_sheet_title}」...")
    if not args.dry_run:
        backup_sheet_id = create_backup_sheet(args.file_id, cfg, args.backup_sheet_title)
    else:
        backup_sheet_id = "BACKUP_SHEET_ID_PLACEHOLDER"
        print(f"  [DRY-RUN] 将创建/使用备份表「{args.backup_sheet_title}」")

    # 5. 备份到备份表
    print(f"\n[4] 备份 {len(to_archive)} 条记录到备份工作表...")
    write_records_to_backup(args.file_id, backup_sheet_id, to_archive, cfg, dry_run=args.dry_run)

    # 6. 对需归档数据做合并压缩
    print(f"\n[5] 按 [{', '.join(GROUP_KEYS)}] 合并，数量累加...")
    merged = defaultdict(lambda: {"数量": 0, "归档区间": "", "记录条数": 0})
    dates_by_group = defaultdict(list)

    for r in to_archive:
        f = r["fields"]
        key = tuple(str(f.get(k) or "").strip() for k in GROUP_KEYS)
        merged[key]["数量"] += int(f.get(QTY_FIELD) or 0)
        merged[key]["记录条数"] += 1
        d = parse_date_ts(f.get(DATE_FIELD))
        if d:
            dates_by_group[key].append(d)

    # 构建合并后的记录列表
    merged_records = []
    for key, agg in merged.items():
        row = {}
        for i, k in enumerate(GROUP_KEYS):
            row[k] = key[i] if key[i] else None
        row[QTY_FIELD] = agg["数量"]

        # 设置归档日期范围备注（写到出库日期字段，用区间字符串）
        dates = dates_by_group[key]
        if dates:
            min_d = min(dates)
            max_d = max(dates)
            if min_d == max_d:
                row[DATE_FIELD] = str(min_d)
            else:
                row[DATE_FIELD] = f"{min_d} ~ {max_d}"
        else:
            row[DATE_FIELD] = f"< {cutoff}"

        # 添加归档标记
        row["备注"] = f"[归档合并] 原 {agg['记录条数']} 条 → 合并于 {datetime.now(tz=tz_cn).strftime('%Y-%m-%d')}"
        merged_records.append(row)

    print(f"    合并后: {len(to_archive)} 条 → {len(merged_records)} 条（压缩率 {100*(1-len(merged_records)/len(to_archive)):.1f}%）")

    # 打印合并结果示例
    print("    示例（前5条）：")
    for r in merged_records[:5]:
        print(f"      {r.get('产品名称','')}/{r.get('型号','')}/{r.get('颜色','')}/{r.get('产品变量','')} → 数量={r.get('数量',0)}")

    # 7. 删除源表中已归档的原始明细行
    print(f"\n[6] 删除源表中 {len(to_archive)} 条原始明细行...")
    record_ids_to_delete = [r["record_id"] for r in to_archive]
    delete_records_batch(args.file_id, args.source_sheet, record_ids_to_delete, cfg, dry_run=args.dry_run)

    # 8. 写入合并汇总行到源表
    print(f"\n[7] 向源表写入 {len(merged_records)} 条合并汇总行...")
    add_merged_records(args.file_id, args.source_sheet, merged_records, cfg, dry_run=args.dry_run)

    # 9. 完成报告
    print(f"\n{'='*60}")
    print(f"✅ 归档压缩完成！")
    print(f"   原始明细行: {len(to_archive)} 条")
    print(f"   合并汇总行: {len(merged_records)} 条")
    print(f"   节省行数:   {len(to_archive) - len(merged_records)} 条")
    print(f"   备份工作表: {args.backup_sheet_title}")
    if args.dry_run:
        print(f"   ⚠️  以上为 DRY-RUN 模式，未实际修改任何数据")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="出库明细归档压缩脚本")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不修改数据")
    parser.add_argument("--file-id", default=DEFAULT_FILE_ID, help=f"目标文件ID（默认：{DEFAULT_FILE_ID}）")
    parser.add_argument("--source-sheet", default=DEFAULT_SHEET_ID, help=f"源工作表ID（默认：{DEFAULT_SHEET_ID}）")
    parser.add_argument("--backup-sheet-title", default=BACKUP_SHEET_TITLE, help=f"备份工作表标题（默认：{BACKUP_SHEET_TITLE}）")
    parser.add_argument("--archive-months", type=int, default=ARCHIVE_MONTHS, help=f"归档几个月以前的数据（默认：{ARCHIVE_MONTHS}）")
    args = parser.parse_args()

    try:
        run(args)
    except Exception as e:
        print(f"\n❌ 脚本执行失败: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
