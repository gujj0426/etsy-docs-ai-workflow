#!/usr/bin/env python3
"""
workFlowTest AI 图生图自动化工作流
通过腾讯文档 Open API v2 读取触发行，调用即梦4.0生图

依赖: requests / urllib (内置)
"""

import json, datetime, urllib.request, os, time

# ============================================================
# 认证配置（请从 config/tdocs_openapi_v2.json 加载）
# ============================================================
# 配置文件路径（统一在 config/ 目录）
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "tdocs_openapi_v2.json")

def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)

def mcp_headers(cfg):
    return {
        "Access-Token": cfg["access_token"],
        "Client-Id": cfg["client_id"],
        "Open-Id": cfg["open_id"],
    }

def api_call(url, payload=None, headers=None, method="GET"):
    """通用 API 调用"""
    if headers is None:
        headers = {}
    headers["Accept"] = "application/json"
    if payload and method == "POST":
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
    else:
        req = urllib.request.Request(url, method=method, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"ret": e.code, "msg": e.read().decode()[:200]}

# ============================================================
# Step 1: 读取 workFlowTest 触发行
# ============================================================
def get_trigger_records():
    """
    返回满足触发条件的记录列表
    触发条件：
      - 审单完成 = "Y"
      - 出库日期 在 [今天-3天, 今天]
      - 设计风格 in ["宠物头像(见附图)", "人物头像(见附图)"]
    """
    cfg = load_config()
    file_id = cfg["storage_file_id_v2"]   # "300000000$KFoUkmaZFqLP"
    sheet_id = cfg["workFlowTest"]["sheet_id"]  # "tbfaTE"

    url = f"{cfg['smartbook_base']}/{file_id}/sheets/{sheet_id}"
    result = api_call(
        url,
        payload={"getRecords": {"offset": 0, "limit": 100}},
        headers=mcp_headers(cfg),
        method="POST"
    )

    records = result.get("data", {}).get("getRecords", {}).get("records", [])
    total = result.get("data", {}).get("getRecords", {}).get("total", 0)

    # 腾讯文档时间戳是毫秒 UTC+8，需要用 timezone 正确解析
    tz_cn = datetime.timezone(datetime.timedelta(hours=8))
    today = datetime.datetime.now(tz=tz_cn)
    date_3ago = today - datetime.timedelta(days=3)
    today_ts = int(today.timestamp() * 1000)
    # 范围: [今天-3天 00:00, 今天 23:59:59]
    date_3ago_ts = int(datetime.datetime(date_3ago.year, date_3ago.month, date_3ago.day, tzinfo=tz_cn).timestamp() * 1000)
    today_end_ts = int(datetime.datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=tz_cn).timestamp() * 1000)

    trigger = []
    for rec in records:
        vals = rec.get("values", {})

        # 审单完成
        shendan = vals.get("审单完成", [])
        if isinstance(shendan, list) and shendan:
            if shendan[0].get("text", "") != "Y":
                continue
        else:
            continue

        # 出库日期
        out_ts = int(float(vals.get("出库日期", 0)))
        if out_ts < date_3ago_ts or out_ts > today_end_ts:
            continue

        # 设计风格
        style_raw = vals.get("设计风格", [])
        style = style_raw[0].get("text", "") if isinstance(style_raw, list) and style_raw else ""
        if style not in ["宠物头像(见附图)", "人物头像(见附图)"]:
            continue

        # 解析图片
        imgs = vals.get("客户原图", [])
        img_list = []
        for img in imgs:
            img_list.append({
                "id": img.get("id", ""),
                "title": img.get("title", ""),
                "url": img.get("imageUrl", ""),
            })

        def get_text(val):
            """安全获取文本字段值"""
            if isinstance(val, list) and len(val) > 0:
                return val[0].get("text", "") if isinstance(val[0], dict) else str(val[0])
            if isinstance(val, dict):
                return val.get("text", "")
            return ""

        trigger.append({
            "record_id": rec["recordID"],           # 行唯一标识（腾讯文档row id，用于定位回传）
            "订单编号": get_text(vals.get("订单编号")),  # 订单编号列的值（用于展示/归档名）
            "产品名称": get_text(vals.get("产品名称")),
            "型号": get_text(vals.get("型号")),
            "颜色": get_text(vals.get("颜色")),
            "设计风格": style,
            "字体": get_text(vals.get("字体")),
            "设计师": get_text(vals.get("设计师")),
            "出库日期": datetime.datetime.fromtimestamp(out_ts / 1000).strftime("%Y-%m-%d") if out_ts else "",
            "客户原图": img_list,
        })

    return trigger


# ============================================================
# Step 2: 下载客户原图
# ============================================================
def download_image(url, save_path):
    """下载腾讯文档图片到本地（需要 Referer 头）"""
    cfg = load_config()
    headers = {
        **mcp_headers(cfg),
        "Referer": "https://docs.qq.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        with open(save_path, "wb") as f:
            f.write(resp.read())
    print(f"  下载完成: {save_path} ({os.path.getsize(save_path)//1024}KB)")


# ============================================================
# Step 3: 调用即梦4.0生成图片（复用 seedream_ark.py）
# ============================================================
def generate_ai_image(local_img_path, color, style, order_no):
    """调用即梦4.0生成AI粗略图"""
    try:
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from seedream_ark import JimengV2Client
    except ImportError:
        print("  [跳过] seedream_ark.py 未找到，跳过 AI 生图")
        return None

    cfg = load_config()

    # Prompt 路由（Prompt 模板实测最终确认版，2026-04-30 v2 合并版）
    if style == "宠物头像(见附图)":
        if color == "黑色":
            prompt = (
                "将参考图片转换为精细黑白木刻版画风格，用于woodbox激光雕刻。"
                "严格遵守：1. 百分之百精准还原图中的宠物，绝不添加删减或扭曲 "
                "2. 绝对纯净纯黑背景——无任何纹理、无任何颗粒、无任何渐变，背景与主体之间绝对分明，宠物的主体轮廓完全剥离 "
                "3. 毛发/纹理：极细密排线+交叉排线，线条间距极小，线条数量最大化，拒绝稀疏线条 "
                "4. 高对比纯黑白，无灰色中间调，线条粗细对比强烈 "
                "5. 工笔画般的精微细节，拒绝块状涂抹"
            )
        else:
            prompt = (
                "将参考图片转换为精微素描手绘风格，用于woodbox激光雕刻。"
                "严格遵守：1. 百分之百精准还原图中的宠物 "
                "2. 完整保留原始宠物主体的所有细节特征，包括轮廓、质感、神态 "
                "3. 白色底，黑白线稿，精微素描手绘风格，无任何背景元素残留，宠物的主体轮廓完全剥离 "
                "4. 毛发/纹理：超精细单根线条 "
                "5. 高对比纯黑白，无灰色中间调，线条粗细对比强烈 "
                "6. 工笔画般的精微细节，拒绝块状涂抹"
            )
    elif style == "人物头像(见附图)":
        if color == "黑色":
            prompt = (
                "将参考图片转换为精细黑白木刻版画风格，用于woodbox激光雕刻。"
                "严格遵守：1. 百分之百精准还原图中的人物，绝不添加删减或扭曲 "
                "2. 绝对纯净纯黑背景——无任何纹理、无任何颗粒、无任何渐变，背景与主体之间绝对分明，人物的主体轮廓完全剥离 "
                "3. 重点区域（五官、面部轮廓、手部、发型）：极细密排线+交叉排线，线条间距极小，线条数量最大化，拒绝稀疏线条 "
                "4. 高对比纯黑白，无灰色中间调，线条粗细对比强烈 "
                "5. 工笔画般的精微细节，拒绝块状涂抹"
            )
        else:
            prompt = (
                "将参考图片转换为精微素描手绘风格，用于woodbox激光雕刻。"
                "严格遵守：1. 百分之百精准还原图中的人物 "
                "2. 完整保留原始人物主体的所有细节特征，包括轮廓、质感、神态 "
                "3. 白色底，黑白线稿，精微素描手绘风格，无任何背景元素残留，人物的主体轮廓完全剥离 "
                "4. 重点区域（五官、面部轮廓、手部）线条极密集 "
                "5. 高对比纯黑白，无灰色中间调，线条粗细对比强烈 "
                "6. 工笔画般的精微细节，拒绝块状涂抹"
            )
    else:
        prompt = "精细黑白线稿，高对比，纯线条，无背景"

    client = JimengV2Client(
        ak=cfg.get("jimeng_ak", os.environ.get("JIMENG_AK", "")),
        sk=cfg.get("jimeng_sk", os.environ.get("JIMENG_SK", ""))
    )

    # 读取本地图片并转为 base64
    with open(local_img_path, "rb") as f:
        img_bytes = f.read()
    import base64
    img_b64 = base64.b64encode(img_bytes).decode()

    # 所有类型统一使用固定 seed=12345 提高稳定性（2026-04-30 确认）
    extra = {"seed": 12345}

    # 调用即梦4.0（同步生成，轮询等待）
    task_id = client.submit(prompt=prompt, binary_data_base64=[img_b64], **extra)
    print(f"  任务ID: {task_id}，等待生成...")
    
    # 轮询直到完成
    import time as _time
    max_wait = 300
    start = _time.time()
    poll_interval = 5
    while True:
        elapsed = _time.time() - start
        if elapsed > max_wait:
            raise TimeoutError(f"任务 {task_id} 超过 {max_wait}s 未完成")
        result = client.get_result(task_id)
        status = result.get("data", {}).get("status", "")
        print(f"  状态: {status} ({int(elapsed)}s)")
        if status == "done":
            break
        elif status in ("failed", "not_found"):
            raise RuntimeError(f"任务失败: {result}")
        _time.sleep(poll_interval)

    # 使用 save_result 保存图片
    from seedream_ark import save_result
    from pathlib import Path
    output_dir = Path(__file__).parent / "generated_images"
    paths = save_result(result, output_dir=output_dir, prefix=f"{order_no}_AI")
    img_path_local = str(paths[0]) if paths else ""
    print(f"  图片已保存: {img_path_local}")
    return {"local_path": img_path_local, "result": result}


# ============================================================
# 主流程
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Step 1: 读取 workFlowTest 触发行")
    print("=" * 60)

    records = get_trigger_records()
    print(f"\n触发记录数: {len(records)}")

    for rec in records:
        print(f"\n{'─' * 50}")
        print(f"行ID(record_id): {rec['record_id']} | 订单编号: {rec['订单编号']}")
        print(f"产品: {rec['产品名称']} | 型号: {rec['型号']} | 颜色: {rec['颜色']}")
        print(f"设计风格: {rec['设计风格']} | 设计师: {rec['设计师']}")
        print(f"出库日期: {rec['出库日期']}")

        # 下载客户原图（用 record_id 唯一命名）
        for img in rec["客户原图"]:
            ext = os.path.splitext(img["title"])[1] if img["title"] else ".jpg"
            save_path = os.path.join(os.path.dirname(__file__), "temp_imgs", f"{rec['record_id']}_原图{ext}")
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            try:
                download_image(img["url"], save_path)
            except Exception as e:
                print(f"  下载失败: {e}")

        # 生成 AI 图片
        if rec["客户原图"]:
            ext = os.path.splitext(rec["客户原图"][0]["title"])[1] if rec["客户原图"][0]["title"] else ".jpg"
            img_path = os.path.join(os.path.dirname(__file__), "temp_imgs", f"{rec['record_id']}_原图{ext}")
            if os.path.exists(img_path):
                gen_result = generate_ai_image(img_path, rec["颜色"], rec["设计风格"], rec["record_id"])
                if gen_result and gen_result.get("local_path"):
                    print(f"  AI图已保存: {gen_result['local_path']}")
