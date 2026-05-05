#!/usr/bin/env python3
"""
AI 产品图全流程测试
====================
通过 Open API v2 读取 workFlowTest → 下载客户原图 → 即梦4.0生图 → 回写腾讯文档

触发条件（与生产一致）：
  - 审单完成 = "Y"
  - 出库日期 ∈ [今天-3天, 今天]
  - 设计风格 ∈ {宠物头像(见附图), 人物头像(见附图)}
  - AI生成粗略图 为空（幂等）

2026-04-30
"""

import os
import sys
import json
import time
import base64
import datetime
import urllib.request
import urllib.error
from pathlib import Path
from dataclasses import dataclass, field

# ─────────────────────────────────────────────
# 配置
# ─────────────────────────────────────────────
CONFIG_FILE = Path(__file__).parent.parent / "config" / "tdocs_openapi_v2.json"
WORKFLOW_SHEET_ID = "tbfaTE"   # workFlowTest

@dataclass
class Config:
    access_token: str
    client_id: str
    open_id: str
    smartbook_base: str
    storage_file_id_v2: str
    jimeng_ak: str
    jimeng_sk: str

def load_config() -> Config:
    with open(CONFIG_FILE) as f:
        d = json.load(f)
    return Config(
        access_token=d["access_token"],
        client_id=d["client_id"],
        open_id=d["open_id"],
        smartbook_base=d["smartbook_base"],
        storage_file_id_v2=d["storage_file_id_v2"],
        jimeng_ak=d["jimeng_ak"],
        jimeng_sk=d["jimeng_sk"],
    )

def api_headers(cfg: Config):
    return {
        "Access-Token": cfg.access_token,
        "Client-Id": cfg.client_id,
        "Open-Id": cfg.open_id,
        "Content-Type": "application/json",
    }

def api_call(url, payload=None, headers=None, method="GET", retries=5):
    """调用腾讯文档 Open API v2，自动重试速率限制（ret=9998）"""
    if headers is None:
        headers = {}
    headers["Accept"] = "application/json"
    for attempt in range(retries):
        try:
            if payload and method == "POST":
                data = json.dumps(payload).encode()
                req = urllib.request.Request(url, data=data, method=method, headers=headers)
            else:
                req = urllib.request.Request(url, method=method, headers=headers)
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read())
            # 速率限制：等待后重试
            if result.get("ret") == 9998:
                wait = 2 ** attempt + 1
                print(f"    ⏳ 速率限制，等待 {wait}s 后重试（第{attempt+1}/{retries}次）...")
                time.sleep(wait)
                continue
            return result
        except urllib.error.HTTPError as e:
            return {"ret": e.code, "msg": e.read().decode()[:300]}
        except Exception as e:
            return {"ret": -1, "msg": str(e)}
    # 最后一次也失败则抛异常
    raise RuntimeError(f"API 调用失败（已达最大重试次数）: {url}")


# ─────────────────────────────────────────────
# Prompt 模板（v2 最终确认版）
# ─────────────────────────────────────────────
def build_prompt(style: str, color: str) -> str:
    if style == "宠物头像(见附图)":
        if color == "黑色":
            return (
                "将参考图片转换为精细黑白木刻版画风格，用于woodbox激光雕刻。"
                "严格遵守：1. 百分之百精准还原图中的宠物，绝不添加删减或扭曲 "
                "2. 绝对纯净纯黑背景——无任何纹理、无任何颗粒、无任何渐变，背景与主体之间绝对分明，宠物的主体轮廓完全剥离 "
                "3. 毛发/纹理：极细密排线+交叉排线，线条间距极小，线条数量最大化，拒绝稀疏线条 "
                "4. 高对比纯黑白，无灰色中间调，线条粗细对比强烈 "
                "5. 工笔画般的精微细节，拒绝块状涂抹"
            )
        else:
            return (
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
            return (
                "将参考图片转换为精细黑白木刻版画风格，用于woodbox激光雕刻。"
                "严格遵守：1. 百分之百精准还原图中的人物，绝不添加删减或扭曲 "
                "2. 绝对纯净纯黑背景——无任何纹理、无任何颗粒、无任何渐变，背景与主体之间绝对分明，人物的主体轮廓完全剥离 "
                "3. 重点区域（五官、面部轮廓、手部、发型）：极细密排线+交叉排线，线条间距极小，线条数量最大化，拒绝稀疏线条 "
                "4. 高对比纯黑白，无灰色中间调，线条粗细对比强烈 "
                "5. 工笔画般的精微细节，拒绝块状涂抹"
            )
        else:
            return (
                "将参考图片转换为精微素描手绘风格，用于woodbox激光雕刻。"
                "严格遵守：1. 百分之百精准还原图中的人物 "
                "2. 完整保留原始人物主体的所有细节特征，包括轮廓、质感、神态 "
                "3. 白色底，黑白线稿，精微素描手绘风格，无任何背景元素残留，人物的主体轮廓完全剥离 "
                "4. 重点区域（五官、面部轮廓、手部）线条极密集 "
                "5. 高对比纯黑白，无灰色中间调，线条粗细对比强烈 "
                "6. 工笔画般的精微细节，拒绝块状涂抹"
            )
    return "精细黑白线稿，高对比，纯线条，无背景"


# ─────────────────────────────────────────────
# Step 1: 读取触发行
# ─────────────────────────────────────────────
def fetch_trigger_records(cfg: Config, lookback_days: int = 3, skip_audit: bool = False):
    tz_cn = datetime.timezone(datetime.timedelta(hours=8))
    today = datetime.datetime.now(tz=tz_cn)
    date_3ago = today - datetime.timedelta(days=lookback_days)
    date_3ago_ts = int(datetime.datetime(date_3ago.year, date_3ago.month, date_3ago.day, tzinfo=tz_cn).timestamp() * 1000)
    today_end_ts = int(datetime.datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=tz_cn).timestamp() * 1000)

    url = f"{cfg.smartbook_base}/{cfg.storage_file_id_v2}/sheets/{WORKFLOW_SHEET_ID}"
    try:
        result = api_call(url, payload={"offset": 0, "limit": 100},
                          headers=api_headers(cfg), method="POST")
    except RuntimeError as e:
        raise RuntimeError(f"读取 workFlowTest 失败: {e}")

    # Open API v2 返回结构：data.records[] + data.total
    records = result.get("data", {}).get("records", [])
    total = result.get("data", {}).get("total", 0)
    print(f"[Step1] 共读取 {len(records)} 条记录（API返回 total={total}）")

    triggered = []
    for rec in records:
        vals = rec.get("values", {})

        # 审单完成（--force 模式跳过此检查）
        shendan = vals.get("审单完成", [])
        s_text = shendan[0].get("text", "") if isinstance(shendan, list) and shendan else ""
        if not skip_audit:
            if s_text != "Y":
                continue
        else:
            # 强制模式：只跳过空值，允许跳过审单检查（测试用）
            if s_text and s_text != "Y":
                continue

        # 出库日期（范围检查，单位统一为毫秒）
        out_ts = int(float(vals.get("出库日期", 0)))
        if out_ts < date_3ago_ts or out_ts > today_end_ts:
            continue

        # 设计风格
        style_raw = vals.get("设计风格", [])
        style = style_raw[0].get("text", "") if isinstance(style_raw, list) and style_raw else ""
        if style not in ["宠物头像(见附图)", "人物头像(见附图)"]:
            continue

        # AI生成粗略图（幂等：已有图则跳过）
        ai_imgs = vals.get("AI生成粗略图", [])
        if isinstance(ai_imgs, list) and len(ai_imgs) > 0 and ai_imgs[0].get("imageUrl"):
            print(f"  ⏭ 跳过 {rec.get('recordID')}：已有AI图，跳过幂等检查")
            continue

        # 客户原图
        raw_imgs = vals.get("客户原图", [])
        img_list = []
        for img in raw_imgs:
            img_list.append({
                "id": img.get("id", ""),
                "title": img.get("title", ""),
                "url": img.get("imageUrl", ""),
            })

        def get_text(val):
            if isinstance(val, list) and len(val) > 0:
                return val[0].get("text", "") if isinstance(val[0], dict) else str(val[0])
            if isinstance(val, dict):
                return val.get("text", "")
            return ""

        triggered.append({
            "record_id": rec.get("recordID"),
            "订单编号": get_text(vals.get("订单编号")),
            "产品名称": get_text(vals.get("产品名称")),
            "型号": get_text(vals.get("型号")),
            "颜色": get_text(vals.get("颜色")),
            "设计风格": style,
            "设计师": get_text(vals.get("设计师")),
            "出库日期": datetime.datetime.fromtimestamp(out_ts / 1000, tz=tz_cn).strftime("%Y-%m-%d") if out_ts else "",
            "客户原图": img_list,
        })

    print(f"[Step1] 触发记录数: {len(triggered)}")
    return triggered


# ─────────────────────────────────────────────
# Step 2: 下载客户原图
# ─────────────────────────────────────────────
def download_customer_image(url: str, save_path: Path) -> bool:
    headers = {
        "Referer": "https://docs.qq.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        save_path.write_bytes(data)
        print(f"    下载完成: {save_path.name} ({len(data)//1024}KB)")
        return True
    except Exception as e:
        print(f"    下载失败: {e}")
        return False


# ─────────────────────────────────────────────
# Step 3: 即梦4.0生成 AI 图
# ─────────────────────────────────────────────
def generate_ai_image(local_img_path: Path, color: str, style: str, order_no: str, cfg: Config) -> Path:
    from volcengine.visual.VisualService import VisualService

    client = VisualService()
    client.set_ak(cfg.jimeng_ak)
    client.set_sk(cfg.jimeng_sk)

    prompt = build_prompt(style, color)
    print(f"    Prompt({color}/{style}): {prompt[:60]}...")

    with open(local_img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    # 提交任务（seed=12345 固定，复现最佳效果）
    body = {
        "req_key": "jimeng_t2i_v40",
        "prompt": prompt,
        "binary_data_base64": [img_b64],
        "return_url": True,
        "seed": 12345,
    }
    resp = client.cv_sync2async_submit_task(body)
    if resp.get("code") != 10000:
        raise RuntimeError(f"提交失败: {resp}")
    task_id = resp["data"]["task_id"]
    print(f"    任务ID: {task_id}，轮询中...")

    # 轮询结果
    start = time.time()
    poll_interval = 5
    while True:
        elapsed = time.time() - start
        if elapsed > 300:
            raise TimeoutError(f"任务 {task_id} 超过 300s")
        result = client.cv_sync2async_get_result({"task_id": task_id, "req_key": "jimeng_t2i_v40"})
        status = result.get("data", {}).get("status", "")
        print(f"    [{int(elapsed)}s] 状态: {status}")
        if status == "done":
            break
        elif status in ("failed", "not_found"):
            raise RuntimeError(f"任务失败: {result}")
        time.sleep(poll_interval)

    # 保存图片
    output_dir = Path(__file__).parent / "generated_images"
    output_dir.mkdir(exist_ok=True)
    paths = save_ai_image(result, output_dir, prefix=f"{order_no}_AI")
    return paths[0] if paths else None


def save_ai_image(result: dict, output_dir: Path, prefix: str) -> list:
    paths = []
    data = result.get("data", {})
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    urls = data.get("image_urls") or []
    b64s = data.get("binary_data_base64") or []

    for i, url in enumerate(urls):
        if url:
            fname = f"{prefix}_{i+1:02d}_{ts}.png"
            path = download_url(url, output_dir / fname)
            if path:
                paths.append(path)

    for i, b64 in enumerate(b64s):
        if b64:
            idx = len(urls) + i
            fname = f"{prefix}_{idx+1:02d}_{ts}.png"
            path = output_dir / fname
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(b64))
            paths.append(path)
            print(f"    ✅ 保存: {path.name}")

    return paths


def download_url(url: str, save_path: Path) -> Path:
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(data)
        print(f"    ✅ 保存: {save_path.name} ({len(data)//1024}KB)")
        return save_path
    except Exception as e:
        print(f"    ❌ 保存失败 {save_path}: {e}")
        return None


# ─────────────────────────────────────────────
# Step 4: 上传 AI 图到腾讯文档
# ─────────────────────────────────────────────
def upload_image_to_tdocs(image_path: Path, cfg: Config) -> str:
    import hashlib, uuid

    img_bytes = image_path.read_bytes()
    img_name = image_path.name
    boundary = "----FormBoundary" + uuid.uuid4().hex[:16]
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{img_name}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + img_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        "https://docs.qq.com/openapi/resources/v2/images",
        data=body,
        headers={
            "Access-Token": cfg.access_token,
            "Client-Id": cfg.client_id,
            "Open-Id": cfg.open_id,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode())

    if result.get("ret") != 0:
        raise RuntimeError(f"图片上传失败: {result}")
    image_id = result["data"]["imageID"]
    print(f"    上传成功: imageID={image_id}")
    return image_id


# ─────────────────────────────────────────────
# Step 5: 回写腾讯文档
# ─────────────────────────────────────────────
def write_ai_image_field(record_id: str, image_id: str, cfg: Config) -> dict:
    url = f"{cfg.smartbook_base}/{cfg.storage_file_id_v2}/sheets/{WORKFLOW_SHEET_ID}"
    payload = {
        "action": 2,
        "updateRecords": {
            "records": [{
                "recordID": record_id,
                "values": {"AI生成粗略图": [{"imageID": image_id}]}
            }]
        }
    }
    result = api_call(url, payload=payload, headers=api_headers(cfg), method="POST")
    ok = result.get("ret") == 0
    print(f"    [{'✅' if ok else '❌'}] 回写AI图: {result.get('msg', '成功') if ok else result}")
    return result


def mark_uploaded(record_id: str, cfg: Config) -> dict:
    url = f"{cfg.smartbook_base}/{cfg.storage_file_id_v2}/sheets/{WORKFLOW_SHEET_ID}"
    payload = {
        "action": 2,
        "updateRecords": {
            "records": [{"recordID": record_id, "values": {"已上传": "Y"}}]
        }
    }
    result = api_call(url, payload=payload, headers=api_headers(cfg), method="POST")
    ok = result.get("ret") == 0
    print(f"    [{'✅' if ok else '❌'}] 回写已上传: {result.get('msg', '成功') if ok else result}")
    return result


# ─────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI 产品图全流程测试")
    parser.add_argument("--force", action="store_true", help="跳过审单完成检查（测试用）")
    args = parser.parse_args()

    print("=" * 60)
    print("AI 产品图全流程测试" + (" [FORCE 模式]" if args.force else ""))
    print("=" * 60)

    cfg = load_config()
    print(f"✅ 配置加载完成（file_id: {cfg.storage_file_id_v2}）\n")

    # ── Step 1: 读取触发行 ──────────────────────
    print("▶ Step 1/5: 读取 workFlowTest 触发行")
    records = fetch_trigger_records(cfg, skip_audit=args.force)

    if not records:
        print("\n⚠️  无触发行（可能今日无新单，或审单尚未完成）")
        print("   请确认 workFlowTest 中有 审单完成=Y、出库日期在近3天、设计风格为宠物/人物头像的记录")
        return

    for rec in records:
        print(f"\n{'─' * 50}")
        print(f"  订单编号: {rec['订单编号']}")
        print(f"  产品/型号: {rec['产品名称']} / {rec['型号']}")
        print(f"  颜色: {rec['颜色']} | 风格: {rec['设计风格']}")
        print(f"  出库日期: {rec['出库日期']} | 设计师: {rec['设计师']}")
        print(f"  record_id: {rec['record_id']}")
        has_img = len(rec['客户原图']) > 0 and rec['客户原图'][0].get('url')
        print(f"  客户原图: {'有' if has_img else '❌ 无'}")

        if not has_img:
            print("  ⏭ 无客户原图，跳过")
            continue

        # ── Step 2: 下载客户原图 ────────────────
        print("\n▶ Step 2/5: 下载客户原图")
        img_info = rec["客户原图"][0]
        ext = os.path.splitext(img_info.get("title") or "原图.jpg")[1] or ".jpg"
        save_path = Path(__file__).parent / "temp_imgs" / f"{rec['record_id']}_原图{ext}"
        save_path.parent.mkdir(parents=True, exist_ok=True)

        ok = download_customer_image(img_info["url"], save_path)
        if not ok:
            print("  ⏭ 下载失败，跳过")
            continue

        # ── Step 3: 即梦4.0生成 ────────────────
        print("\n▶ Step 3/5: 即梦4.0生成 AI 图（seed=12345）")
        try:
            ai_path = generate_ai_image(
                save_path, rec["颜色"], rec["设计风格"],
                rec["订单编号"] or rec["record_id"], cfg
            )
            if not ai_path or not ai_path.exists():
                print("  ⏭ 生图失败或无输出，跳过")
                continue
        except Exception as e:
            print(f"  ❌ 即梦4.0调用失败: {e}")
            continue

        # ── Step 4: 上传 AI 图 ──────────────────
        print("\n▶ Step 4/5: 上传 AI 图到腾讯文档")
        try:
            image_id = upload_image_to_tdocs(ai_path, cfg)
        except Exception as e:
            print(f"  ❌ 上传失败: {e}")
            continue

        # ── Step 5: 回写腾讯文档 ───────────────
        print("\n▶ Step 5/5: 回写腾讯文档")
        write_ai_image_field(rec["record_id"], image_id, cfg)
        mark_uploaded(rec["record_id"], cfg)

    print(f"\n{'=' * 60}")
    print("✅ 全流程测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
