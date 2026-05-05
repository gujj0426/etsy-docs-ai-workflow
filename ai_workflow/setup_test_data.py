#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_test_data.py
==================
向测试用的「库存管理系统-测试」智能表格写入测试数据。
包含：
  - 3个月前的旧数据（应被归档压缩）
  - 近3个月的新数据（不应被动）

测试文件: KcQvwWSDEiLF
测试工作表: flPrIM（3、美国仓出库明细-测试）
"""

import json
import sys
import time
import requests
from datetime import datetime, timezone, timedelta

CONFIG_FILE = "/Users/mac/Desktop/etsy/运营文档/config/tdocs_openapi_v2.json"

TEST_FILE_ID = "KcQvwWSDEiLF"
TEST_SHEET_ID = "flPrIM"

API_BASE = "https://docs.qq.com"
tz_cn = timezone(timedelta(hours=8))


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def make_headers(cfg):
    return {
        "Access-Token": cfg["access_token"],
        "Client-Id": cfg["client_id"],
        "Open-Id": cfg["open_id"],
        "Content-Type": "application/json",
    }


def api_post(path, body, cfg):
    url = f"{API_BASE}{path}"
    resp = requests.post(url, headers=make_headers(cfg), json=body, timeout=30)
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


def date_to_str(y, m, d):
    """返回日期字符串 YYYY-MM-DD"""
    return f"{y:04d}-{m:02d}-{d:02d}"


def build_test_records():
    """
    构建测试数据：
    - 旧数据（4个月前，应被归档）：2025-12-XX
    - 旧数据（3个月前，边界日期）：2026-01-XX
    - 新数据（1个月前，不应被归档）：2026-03-XX
    - 新数据（本月，不应被归档）：2026-04-XX
    
    包含：相同 [产品名称, 型号, 颜色, 产品变量] 的多条记录，用于验证合并效果
    """
    records = []

    # === 旧数据（4个月前 - 2025年12月）应被归档 ===
    # 袖扣 银色 S - 同组3条，合并后应为1条
    records.append({"出库日期": "2025-12-01", "产品名称": "旧款袖扣", "型号": "S", "颜色": "银色", "产品变量": "", "数量": "10", "订单编号": "O001"})
    records.append({"出库日期": "2025-12-08", "产品名称": "旧款袖扣", "型号": "S", "颜色": "银色", "产品变量": "", "数量": "5", "订单编号": "O002"})
    records.append({"出库日期": "2025-12-15", "产品名称": "旧款袖扣", "型号": "S", "颜色": "银色", "产品变量": "", "数量": "3", "订单编号": "O003"})

    # 袖扣 金色 L - 同组2条
    records.append({"出库日期": "2025-12-05", "产品名称": "旧款袖扣", "型号": "L", "颜色": "金色", "产品变量": "", "数量": "8", "订单编号": "O004"})
    records.append({"出库日期": "2025-12-20", "产品名称": "旧款袖扣", "型号": "L", "颜色": "金色", "产品变量": "", "数量": "4", "订单编号": "O005"})

    # 鸭嘴领带夹 银色 L - 同组3条
    records.append({"出库日期": "2025-12-03", "产品名称": "鸭嘴领带夹（薄）", "型号": "L", "颜色": "银色", "产品变量": "", "数量": "50", "订单编号": "O006"})
    records.append({"出库日期": "2025-12-10", "产品名称": "鸭嘴领带夹（薄）", "型号": "L", "颜色": "银色", "产品变量": "", "数量": "30", "订单编号": "O007"})
    records.append({"出库日期": "2025-12-25", "产品名称": "鸭嘴领带夹（薄）", "型号": "L", "颜色": "银色", "产品变量": "", "数量": "20", "订单编号": "O008"})

    # 花卉相盒吊坠 银色 一月 - 2条
    records.append({"出库日期": "2025-12-12", "产品名称": "花卉心形相盒吊坠", "型号": "", "颜色": "银色", "产品变量": "一月", "数量": "2", "订单编号": "O009"})
    records.append({"出库日期": "2025-12-28", "产品名称": "花卉心形相盒吊坠", "型号": "", "颜色": "银色", "产品变量": "一月", "数量": "1", "订单编号": "O010"})

    # === 旧数据（刚好3个月前的1月份）- 也应归档 ===
    records.append({"出库日期": "2026-01-05", "产品名称": "旧款袖扣", "型号": "S", "颜色": "银色", "产品变量": "", "数量": "6", "订单编号": "O011"})
    records.append({"出库日期": "2026-01-15", "产品名称": "双面滑入式领带夹", "型号": "L", "颜色": "银色", "产品变量": "", "数量": "15", "订单编号": "O012"})
    records.append({"出库日期": "2026-01-20", "产品名称": "双面滑入式领带夹", "型号": "L", "颜色": "金色", "产品变量": "", "数量": "8", "订单编号": "O013"})
    records.append({"出库日期": "2026-01-28", "产品名称": "硅胶哑光静音狗牌", "型号": "S", "颜色": "黑色", "产品变量": "", "数量": "12", "订单编号": "O014"})

    # === 新数据（3个月内，不应被归档）===
    # 2026年2月 - 新数据
    records.append({"出库日期": "2026-02-05", "产品名称": "旧款袖扣", "型号": "S", "颜色": "银色", "产品变量": "", "数量": "7", "订单编号": "O015"})
    records.append({"出库日期": "2026-02-14", "产品名称": "鸭嘴领带夹（薄）", "型号": "L", "颜色": "银色", "产品变量": "", "数量": "25", "订单编号": "O016"})
    records.append({"出库日期": "2026-02-20", "产品名称": "双面滑入式领带夹", "型号": "L", "颜色": "银色", "产品变量": "", "数量": "10", "订单编号": "O017"})

    # 2026年3月 - 新数据
    records.append({"出库日期": "2026-03-01", "产品名称": "硅胶哑光静音狗牌", "型号": "M", "颜色": "黑色", "产品变量": "", "数量": "20", "订单编号": "O018"})
    records.append({"出库日期": "2026-03-10", "产品名称": "旧款袖扣", "型号": "L", "颜色": "金色", "产品变量": "", "数量": "9", "订单编号": "O019"})
    records.append({"出库日期": "2026-03-20", "产品名称": "花卉心形相盒吊坠", "型号": "", "颜色": "银色", "产品变量": "三月", "数量": "3", "订单编号": "O020"})

    # 2026年4月 - 近期数据
    records.append({"出库日期": "2026-04-01", "产品名称": "鸭嘴领带夹（薄）", "型号": "L", "颜色": "银色", "产品变量": "", "数量": "40", "订单编号": "O021"})
    records.append({"出库日期": "2026-04-15", "产品名称": "双面滑入式领带夹", "型号": "L", "颜色": "黑色", "产品变量": "", "数量": "5", "订单编号": "O022"})
    records.append({"出库日期": "2026-04-28", "产品名称": "硅胶哑光静音狗牌", "型号": "S", "颜色": "银色", "产品变量": "", "数量": "15", "订单编号": "O023"})

    return records


def write_test_records(cfg):
    fid = fmt_file_id(TEST_FILE_ID)
    path = f"/openapi/smartbook/v2/files/{fid}/sheets/{TEST_SHEET_ID}"
    records = build_test_records()

    print(f"准备写入 {len(records)} 条测试记录...")

    batch_size = 20
    written = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        api_records = []
        for r in batch:
            values = {}
            for k, v in r.items():
                if v is not None and v != "":
                    values[k] = v
            api_records.append({"values": values})

        body = {"addRecords": {"records": api_records}}
        result = api_post(path, body, cfg)
        written += len(batch)
        print(f"  已写入 {written}/{len(records)} 条...")
        time.sleep(0.3)

    print(f"\n✅ 测试数据写入完成！共 {len(records)} 条")
    print(f"\n数据分布预览：")
    old_data = [r for r in records if r["出库日期"] < "2026-02-01"]
    new_data = [r for r in records if r["出库日期"] >= "2026-02-01"]
    print(f"  应被归档（<2026-02-01）: {len(old_data)} 条")
    print(f"  应保留（>=2026-02-01）:  {len(new_data)} 条")
    print(f"\n归档后预期效果（旧数据合并后）：")
    from collections import defaultdict
    groups = defaultdict(int)
    for r in old_data:
        key = (r["产品名称"], r["型号"], r["颜色"], r["产品变量"])
        groups[key] += 1
    print(f"  {len(old_data)} 条旧数据 → 合并为 {len(groups)} 条汇总行")
    for key, count in sorted(groups.items()):
        print(f"    {key}: {count}条合并为1条")


if __name__ == "__main__":
    cfg = load_config()
    write_test_records(cfg)
