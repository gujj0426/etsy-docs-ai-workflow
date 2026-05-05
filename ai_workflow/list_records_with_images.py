#!/usr/bin/env python3
"""
从 workFlowTest 查询有客户原图的记录
"""
import json
import os
import requests

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "tdocs_openapi_v2.json")
with open(CONFIG_PATH) as f:
    cfg = json.load(f)

ACCESS_TOKEN = cfg["access_token"]
CLIENT_ID    = cfg["client_id"]
OPEN_ID      = cfg["open_id"]
FILE_ID      = cfg["storage_file_id_v2"]
SHEET_ID     = cfg["workFlowTest"]["sheet_id"]

url = f"https://docs.qq.com/openapi/smartbook/v2/files/{FILE_ID}/sheets/{SHEET_ID}"
headers = {
    "Access-Token": ACCESS_TOKEN,
    "Client-Id":    CLIENT_ID,
    "Open-Id":      OPEN_ID,
    "Content-Type": "application/json",
}

# 只查前10条，看哪些有客户原图
payload = {
    "pageSize": 10,
    "pageToken": ""
}

print(f"[REQUEST] GET records from {SHEET_ID}")
resp = requests.post(url, headers=headers, json=payload, timeout=30)
data = resp.json()

if data.get("ret") != 0:
    print(f"[FAIL] {data}")
else:
    records = data.get("data", {}).get("records", [])
    print(f"[INFO] 共 {len(records)} 条记录\n")
    for r in records:
        rid = r.get("recordID", "?")
        vals = r.get("values", {})
        # 打印关键字段
        order = vals.get("订单编号", ["?"])[0].get("text", "?") if vals.get("订单编号") else "无"
        style = vals.get("设计风格", ["?"])[0].get("text", "?") if vals.get("设计风格") else "无"
        color = vals.get("颜色", ["?"])[0].get("text", "?") if vals.get("颜色") else "无"
        img_field = vals.get("客户原图")
        has_img = "✅ 有图" if img_field else "❌ 无图"
        print(f"  recordID={rid}  订单={order}  风格={style}  颜色={color}  {has_img}")
        if img_field:
            print(f"    客户原图: {json.dumps(img_field, ensure_ascii=False)[:200]}")
