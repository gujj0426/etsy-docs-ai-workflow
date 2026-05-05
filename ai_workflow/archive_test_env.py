#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
archive_test_env.py
===================
归档压缩功能完整测试脚本。

⚠️ 重要说明 ⚠️
--------------
腾讯文档 Open API v2 不支持通过 API 创建新的智能表格文件。
测试环境需要手动在腾讯文档 UI 中创建，步骤如下：

【手动创建测试表步骤】
1. 打开 https://docs.qq.com/desktop
2. 新建空白智能表格，命名为「归档压缩-测试勿删」
3. 创建工作表「3、美国仓出库明细-测试」
4. 按以下字段名和类型手动创建字段：

   字段名         类型          说明
   ─────────────────────────────────
   产品名称       单选          备选：旧款袖扣、鸭嘴领带夹（薄）、双面滑入式领带夹、硅胶哑光静音狗牌、花卉心形相盒吊坠
   型号           多选          备选：S、M、L
   颜色           单选          备选：银色、金色、玫瑰金、黑色
   产品变量       单选          备选：（空）、一月、二月、三月
   数量           数字
   出库日期       日期
   订单编号       文本

5. 记下新的 file_id 和 sheet_id，填入本脚本下方的 TEST_FILE_ID / TEST_SHEET_ID

执行方式：
  python3 archive_test_env.py [--setup] [--write-test-data] [--run-archive] [--cleanup]

参数：
  --setup           向测试表添加正确类型的字段（如果UI创建后字段不对）
  --write-test-data 写入测试数据（23条，跨2025-12到2026-04）
  --run-archive     运行归档压缩（dry-run）
  --cleanup         清理测试数据（删除测试工作表中的所有记录）
"""

import argparse
import json
import sys
import time
import requests
import traceback
from datetime import datetime, timezone, timedelta
from collections import defaultdict

CONFIG_FILE = "/Users/mac/Desktop/etsy/运营文档/config/tdocs_openapi_v2.json"
API_BASE = "https://docs.qq.com"
tz_cn = timezone(timedelta(hours=8))

# ───────────────── 填写测试环境参数 ──────────────────────────────
# ⚠️ 手动创建测试表后，在此填入测试表的 file_id 和 sheet_id
TEST_FILE_ID = "KcQvwWSDEiLF"   # 测试文件 file_id
TEST_SHEET_ID = "flPrIM"         # 测试工作表 sheet_id（创建后替换）
# ────────────────────────────────────────────────────────────────

DEFAULT_FILE_ID = "KFoUkmaZFqLP"
DEFAULT_SHEET_ID = "tWOjoH"
ARCHIVE_MONTHS = 3
BATCH_SIZE = 50


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def make_headers(cfg):
    return {
        "Access-Token": cfg["access_token"],
        "Client-Id":    cfg["client_id"],
        "Open-Id":      cfg["open_id"],
        "Content-Type":  "application/json",
    }


def api_post(path, body, cfg, timeout=30):
    url = f"{API_BASE}{path}"
    resp = requests.post(url, headers=make_headers(cfg), json=body, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    ret = data.get("ret", data.get("code", 0))
    if ret != 0:
        raise RuntimeError(f"API error ret={ret} msg={data.get('msg','')}: {data}")
    return data


def fmt_file_id(file_id):
    if not file_id.startswith("300000000$"):
        return f"300000000${file_id}"
    return file_id


def get_sheet_list(file_id, cfg):
    fid = fmt_file_id(file_id)
    path = f"/openapi/smartbook/v2/files/{fid}/sheets"
    data = api_post(path, {"getSheets": {}}, cfg)
    return data.get("getSheets", {}).get("sheets", [])


def get_sheet_fields(file_id, sheet_id, cfg):
    fid = fmt_file_id(file_id)
    path = f"/openapi/smartbook/v2/files/{fid}/sheets/{sheet_id}"
    data = api_post(path, {"getFields": {"offset": 0, "limit": 200}}, cfg)
    return data.get("getFields", {}).get("fields", [])


def setup_test_fields(file_id, sheet_id, cfg):
    """
    向测试工作表添加正确类型的字段。
    注意：此 API 可能不支持所有类型，请优先在 UI 中手动创建字段。
    """
    fid = fmt_file_id(file_id)
    path = f"/openapi/smartbook/v2/files/{fid}/sheets/{sheet_id}"

    existing = get_sheet_fields(file_id, sheet_id, cfg)
    existing_titles = {f["title"] for f in existing}
    print(f"  现有字段: {existing_titles}")

    # 尝试添加各类型字段
    field_defs = [
        {"title": "产品名称", "type": "text"},
        {"title": "型号", "type": "text"},
        {"title": "颜色", "type": "text"},
        {"title": "产品变量", "type": "text"},
        {"title": "数量", "type": "number"},
        {"title": "出库日期", "type": "text"},
        {"title": "订单编号", "type": "text"},
    ]

    # 实际测试发现：Open API v2 的 addFields 对智能表格支持有限
    # 建议直接在 UI 中创建字段
    print("\n⚠️  注意：Open API v2 对智能表格字段类型的支持有限。")
    print("   建议直接在腾讯文档 UI 中手动创建字段，选择正确的类型：")
    print("   - 产品名称/颜色/产品变量：单选（select）")
    print("   - 型号：多选（multi-select）")
    print("   - 数量：数字（number）")
    print("   - 出库日期：日期（date）")
    print("   - 订单编号：文本（text）")
    print("\n   本函数跳过 API 字段创建，仅做信息展示。")

    return existing_titles


def build_test_records():
    """
    构建测试数据。
    截止日期：2026-02-01（archive_months=3）
    - 旧数据（< 2026-02-01）：应被归档
      含重复 key：旧款袖扣+S+银色 → 10+5+3=18
    - 新数据（>= 2026-02-01）：不应被动
    """
    records = []

    # === 旧数据（应被归档，2026-02-01 之前）===
    # 组1：旧款袖扣 S 银色 —— 3条，合并后数量=18
    records.append({"出库日期": "2025-12-01", "产品名称": "旧款袖扣", "型号": "S", "颜色": "银色", "产品变量": "",  "数量": 10, "订单编号": "TEST-O001"})
    records.append({"出库日期": "2025-12-08", "产品名称": "旧款袖扣", "型号": "S", "颜色": "银色", "产品变量": "",  "数量": 5,  "订单编号": "TEST-O002"})
    records.append({"出库日期": "2025-12-15", "产品名称": "旧款袖扣", "型号": "S", "颜色": "银色", "产品变量": "",  "数量": 3,  "订单编号": "TEST-O003"})

    # 组2：鸭嘴领带夹 L 银色 —— 3条，合并后数量=100
    records.append({"出库日期": "2025-12-03",  "产品名称": "鸭嘴领带夹（薄）", "型号": "L", "颜色": "银色", "产品变量": "", "数量": 50, "订单编号": "TEST-O004"})
    records.append({"出库日期": "2025-12-10",  "产品名称": "鸭嘴领带夹（薄）", "型号": "L", "颜色": "银色", "产品变量": "", "数量": 30, "订单编号": "TEST-O005"})
    records.append({"出库日期": "2025-12-25",  "产品名称": "鸭嘴领带夹（薄）", "型号": "L", "颜色": "银色", "产品变量": "", "数量": 20, "订单编号": "TEST-O006"})

    # 组3：旧款袖扣 L 金色 —— 2条，合并后数量=13
    records.append({"出库日期": "2025-12-05",  "产品名称": "旧款袖扣", "型号": "L", "颜色": "金色", "产品变量": "", "数量": 8,  "订单编号": "TEST-O007"})
    records.append({"出库日期": "2025-12-20",  "产品名称": "旧款袖扣", "型号": "L", "颜色": "金色", "产品变量": "", "数量": 5,  "订单编号": "TEST-O008"})

    # 组4：双面滑入式领带夹 L 银色 —— 2条，合并后数量=23
    records.append({"出库日期": "2026-01-05",  "产品名称": "双面滑入式领带夹", "型号": "L", "颜色": "银色", "产品变量": "", "数量": 15, "订单编号": "TEST-O009"})
    records.append({"出库日期": "2026-01-15",  "产品名称": "双面滑入式领带夹", "型号": "L", "颜色": "银色", "产品变量": "", "数量": 8,  "订单编号": "TEST-O010"})

    # 组5：硅胶哑光静音狗牌 S 黑色 —— 1条，单独
    records.append({"出库日期": "2026-01-28",  "产品名称": "硅胶哑光静音狗牌", "型号": "S", "颜色": "黑色", "产品变量": "", "数量": 12, "订单编号": "TEST-O011"})

    # === 新数据（不应被归档，2026-02-01 及之后）===
    records.append({"出库日期": "2026-02-05",  "产品名称": "旧款袖扣",         "型号": "S", "颜色": "银色", "产品变量": "", "数量": 7,  "订单编号": "TEST-O012"})
    records.append({"出库日期": "2026-02-14",  "产品名称": "鸭嘴领带夹（薄）",  "型号": "L", "颜色": "银色", "产品变量": "", "数量": 25, "订单编号": "TEST-O013"})
    records.append({"出库日期": "2026-02-20",  "产品名称": "双面滑入式领带夹", "型号": "L", "颜色": "银色", "产品变量": "", "数量": 10, "订单编号": "TEST-O014"})
    records.append({"出库日期": "2026-03-01",  "产品名称": "硅胶哑光静音狗牌", "型号": "M", "颜色": "黑色", "产品变量": "", "数量": 20, "订单编号": "TEST-O015"})
    records.append({"出库日期": "2026-03-10",  "产品名称": "旧款袖扣",         "型号": "L", "颜色": "金色", "产品变量": "", "数量": 9,  "订单编号": "TEST-O016"})
    records.append({"出库日期": "2026-04-01",  "产品名称": "鸭嘴领带夹（薄）",  "型号": "L", "颜色": "银色", "产品变量": "", "数量": 40, "订单编号": "TEST-O017"})
    records.append({"出库日期": "2026-04-15",  "产品名称": "双面滑入式领带夹", "型号": "L", "颜色": "黑色", "产品变量": "", "数量": 5,  "订单编号": "TEST-O018"})

    return records


def write_test_records(file_id, sheet_id, cfg, dry_run=False):
    records = build_test_records()
    fid = fmt_file_id(file_id)
    path = f"/openapi/smartbook/v2/files/{fid}/sheets/{sheet_id}"

    old = [r for r in records if r["出库日期"] < "2026-02-01"]
    new = [r for r in records if r["出库日期"] >= "2026-02-01"]

    print(f"\n测试数据规划（截止日期=2026-02-01）：")
    print(f"  应归档（旧数据）: {len(old)} 条")
    print(f"  应保留（新数据）: {len(new)} 条")
    print(f"  归档前: {len(old)} 条 → 合并后: 5 条（5组），压缩率 {100*(1-5/len(old)):.0f}%")

    if dry_run:
        print("\n[DRY-RUN] 以下为将写入的测试数据：")
        for r in records:
            flag = "【归档】" if r["出库日期"] < "2026-02-01" else "【保留】"
            print(f"  {flag} {r['出库日期']} | {r['产品名称']} | {r['型号']} | {r['颜色']} | 数量={r['数量']}")
        return

    print(f"\n写入 {len(records)} 条测试记录...")
    written = 0
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i+BATCH_SIZE]
        api_records = []
        for r in batch:
            values = {}
            for k, v in r.items():
                if v is not None and v != "":
                    values[k] = v
            api_records.append({"values": values})

        body = {"addRecords": {"records": api_records}}
        api_post(path, body, cfg)
        written += len(batch)
        print(f"  已写入 {written}/{len(records)} 条...")
        time.sleep(0.3)

    print(f"\n✅ 测试数据写入完成！")


def cleanup_test_records(file_id, sheet_id, cfg):
    """删除测试表中的所有记录"""
    fid = fmt_file_id(file_id)
    path = f"/openapi/smartbook/v2/files/{fid}/sheets/{sheet_id}"

    # 读取全部记录
    all_records = []
    offset = 0
    limit = 100
    while True:
        body = {"getRecords": {"offset": offset, "limit": limit}}
        data = api_post(path, body, cfg)
        records_raw = data["data"]["getRecords"]["records"]
        for r in records_raw:
            all_records.append(r["recordID"])
        if len(records_raw) < limit:
            break
        offset += limit
        time.sleep(0.2)

    if not all_records:
        print("  测试表已为空，无需清理")
        return

    print(f"  删除 {len(all_records)} 条记录...")
    deleted = 0
    for i in range(0, len(all_records), BATCH_SIZE):
        batch = all_records[i:i+BATCH_SIZE]
        body = {"deleteRecords": {"recordIDs": batch}}
        api_post(path, body, cfg)
        deleted += len(batch)
        print(f"  已删除 {deleted}/{len(all_records)} 条...")
        time.sleep(0.3)

    print("  ✅ 清理完成")


def validate_archive_logic(file_id, sheet_id, cfg):
    """
    对测试数据进行 dry-run 验证归档逻辑。
    """
    from ai_workflow.archive_compress_outlet import (
        compute_cutoff_date, get_all_records, parse_date_ts,
        GROUP_KEYS, QTY_FIELD, DATE_FIELD
    )
    from collections import defaultdict

    cutoff = compute_cutoff_date(ARCHIVE_MONS := 3)
    print(f"\n[验证] 截止日期: {cutoff}")

    all_records = get_all_records(file_id, sheet_id, cfg)
    print(f"[验证] 共读取 {len(all_records)} 条记录")

    to_archive = []
    to_keep = []
    for r in all_records:
        d = parse_date_ts(r["fields"].get(DATE_FIELD))
        if d is None:
            to_keep.append(r)
        elif d < cutoff:
            to_archive.append(r)
        else:
            to_keep.append(r)

    print(f"[验证] 需归档: {len(to_archive)} 条 | 保留: {len(to_keep)} 条")

    # 合并
    merged = defaultdict(lambda: {"数量": 0, "记录条数": 0})
    for r in to_archive:
        f = r["fields"]
        key = tuple(str(f.get(k) or "").strip() for k in GROUP_KEYS)
        merged[key]["数量"] += int(f.get(QTY_FIELD) or 0)
        merged[key]["记录条数"] += 1

    print(f"\n[验证] 合并结果: {len(to_archive)} 条 → {len(merged)} 条")
    for key, agg in sorted(merged.items()):
        print(f"  {' / '.join(str(k) for k in key)} → 数量={agg['数量']}（原{agg['记录条数']}条）")

    # 对比预期
    expected_groups = {
        ("旧款袖扣", "S", "银色", ""):       18,
        ("鸭嘴领带夹（薄）", "L", "银色", ""): 100,
        ("旧款袖扣", "L", "金色", ""):        13,
        ("双面滑入式领带夹", "L", "银色", ""): 23,
        ("硅胶哑光静音狗牌", "S", "黑色", ""): 12,
    }

    errors = []
    for key, exp_qty in expected_groups.items():
        act_qty = merged.get(key, {}).get("数量", -1)
        if act_qty != exp_qty:
            errors.append(f"  ❌ {key}: 期望数量={exp_qty}, 实际={act_qty}")
        else:
            print(f"  ✅ {key}: 数量={act_qty} ✓")

    if errors:
        print("\n合并验证失败：")
        for e in errors:
            print(e)
        return False
    else:
        print(f"\n✅ 合并逻辑验证通过！{len(to_archive)} 条 → {len(merged)} 条（压缩率 {100*(1-len(merged)/len(to_archive)):.0f}%）")
        return True


def main():
    parser = argparse.ArgumentParser(description="归档压缩功能测试脚本")
    parser.add_argument("--setup", action="store_true", help="设置测试环境（添加字段）")
    parser.add_argument("--write-test-data", action="store_true", help="写入测试数据")
    parser.add_argument("--run-archive", action="store_true", help="运行归档压缩（dry-run）")
    parser.add_argument("--cleanup", action="store_true", help="清理测试数据")
    parser.add_argument("--validate", action="store_true", help="验证归档逻辑")
    parser.add_argument("--file-id", default=TEST_FILE_ID, help=f"测试文件ID（默认：{TEST_FILE_ID}）")
    parser.add_argument("--sheet-id", default=TEST_SHEET_ID, help=f"测试工作表ID（默认：{TEST_SHEET_ID}）")
    args = parser.parse_args()

    if not any(vars(args).get(k) for k in ["setup", "write_test_data", "run_archive", "cleanup", "validate"]):
        print(__doc__)
        print("\n用法示例：")
        print("  1. 手动在腾讯文档 UI 创建测试表后：")
        print("     python3 archive_test_env.py --setup")
        print("  2. 写入测试数据：")
        print("     python3 archive_test_env.py --write-test-data")
        print("  3. 验证归档逻辑（dry-run）：")
        print("     python3 archive_test_env.py --validate")
        print("  4. 实际运行归档（正式执行）：")
        print("     python3 ai_workflow/archive_compress_outlet.py --dry-run --file-id YOUR_TEST_FILE_ID --source-sheet YOUR_TEST_SHEET_ID")
        return

    cfg = load_config()

    try:
        if args.setup:
            print(f"\n{'='*60}")
            print("设置测试环境")
            print(f"{'='*60}")
            setup_test_fields(args.file_id, args.sheet_id, cfg)

        if args.write_test_data:
            print(f"\n{'='*60}")
            print("写入测试数据")
            print(f"{'='*60}")
            write_test_records(args.file_id, args.sheet_id, cfg)

        if args.validate:
            print(f"\n{'='*60}")
            print("验证归档逻辑")
            print(f"{'='*60}")
            ok = validate_archive_logic(args.file_id, args.sheet_id, cfg)
            sys.exit(0 if ok else 1)

        if args.cleanup:
            print(f"\n{'='*60}")
            print("清理测试数据")
            print(f"{'='*60}")
            cleanup_test_records(args.file_id, args.sheet_id, cfg)

        if args.run_archive:
            print(f"\n{'='*60}")
            print("运行归档压缩（dry-run）")
            print(f"{'='*60}")
            from ai_workflow import archive_compress_outlet
            import sys
            sys.argv = [
                "archive_compress_outlet.py",
                "--dry-run",
                "--file-id", args.file_id,
                "--source-sheet", args.sheet_id,
            ]
            archive_compress_outlet.run(archive_compress_outlet.parser.parse_args(sys.argv[1:]))

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
