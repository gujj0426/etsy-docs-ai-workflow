#!/usr/bin/env python3
"""
完整链路测试（2026-04-25）：
① 从腾讯文档下载客户原图
② 调用即梦4.0生成AI图（木刻版画风格，黑色宠物）
③ 上传AI图到腾讯文档 Open API v2
④ 回写到 AI生成粗略图 字段

目标记录：rdUAZI（订单4029637598，黑色，宠物头像）
"""
import json
import os
import time
import requests

# ── 配置 ──────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(SCRIPT_DIR, "..", "config", "tdocs_openapi_v2.json")
with open(CONFIG_PATH) as f:
    cfg = json.load(f)

ACCESS_TOKEN = cfg["access_token"]
CLIENT_ID    = cfg["client_id"]
OPEN_ID      = cfg["open_id"]
JIMENG_AK    = cfg["jimeng_ak"]
JIMENG_SK    = cfg["jimeng_sk"]
FILE_ID      = cfg["storage_file_id_v2"]
SHEET_ID     = cfg["workFlowTest"]["sheet_id"]
JIMENG_BASE  = "https://visual.volcengineapi.com"

TARGET_RECORD = "rdUAZI"
CUSTOMER_IMG_ID = "1776907486703-36ff80bb5addc14e"  # 客户原图 image_id

HEADERS = {
    "Access-Token": ACCESS_TOKEN,
    "Client-Id":    CLIENT_ID,
    "Open-Id":      OPEN_ID,
}

TEMP_DIR = os.path.join(SCRIPT_DIR, "temp_imgs")
os.makedirs(TEMP_DIR, exist_ok=True)

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

# ════════════════════════════════════════════════════
# 步骤①：下载客户原图
# ════════════════════════════════════════════════════
log("步骤① 下载客户原图...")

download_url = f"https://docs.qq.com/openapi/resources/v2/images/{CUSTOMER_IMG_ID}"
resp = requests.get(download_url, headers=HEADERS, timeout=30)
print(f"    下载响应: status={resp.status_code}  size={len(resp.content)} bytes  type={resp.headers.get('Content-Type')}")

if resp.status_code == 200 and len(resp.content) > 1000:
    customer_img_path = os.path.join(TEMP_DIR, "rdUAZI_客户原图.jpg")
    with open(customer_img_path, "wb") as f:
        f.write(resp.content)
    log(f"    ✅ 客户原图已保存: {customer_img_path}")
else:
    log(f"    ❌ 下载失败: {resp.status_code} {resp.text[:200]}")
    exit(1)

# ════════════════════════════════════════════════════
# 步骤②：调用即梦4.0生成AI图（黑色宠物 → 木刻版画）
# ════════════════════════════════════════════════════
log("步骤② 调用即梦4.0生成AI图...")

prompt = (
    "将参考图片转换为精细黑白木刻版画风格，用于woodbox激光雕刻。"
    "严格遵守：1. 百分之百精准还原图中的宠物，绝不添加删减或扭曲 "
    "2. 绝对纯净纯黑背景——无任何纹理、无任何颗粒、无任何渐变，背景与主体之间绝对分明，宠物的主体轮廓完全剥离 "
    "3. 毛发/纹理：极细密排线+交叉排线，线条间距极小，线条数量最大化，拒绝稀疏线条 "
    "4. 高对比纯黑白，无灰色中间调，线条粗细对比强烈 "
    "5. 工笔画般的精微细节，拒绝块状涂抹"
)

# 读取图片并转 base64
import base64
with open(customer_img_path, "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

# 提交任务
submit_payload = {
    "req_key": "jimeng_t2i_v40",
    "task_info": {
        "prompt": prompt,
        "image_base64": img_b64,
        "seed": 12345,
        "return_url": 1
    }
}

# AK/SK 签名（简化版，实际用 volcengine SDK 更可靠）
import hashlib, hmac, base64 as b64
def make_sigv4(ak, sk, service, action, params, body_json):
    """生成 volcengine SigV4 签名（简化）"""
    t = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    date = t[:8]
    # 使用 volcengine SDK
    try:
        from volcengine.base.Service import Service
        s = Service()
        s.set_access_key(ak)
        s.set_secret_key(sk)
        s.set_service(service)
        s.set_region("cn-north-1")
        s.set_version("2022-08-02")
        s.set_action(action)
        payload = json.dumps(body_json)
        resp = s.json("POST", "/", {}, payload)
        return resp
    except ImportError:
        log("    ⚠️ volcengine SDK 未安装，使用 requests 直接调用...")
        return None

# 使用 volcengine SDK
try:
    from volcengine.base.Service import Service
    svc = Service()
    svc.set_access_key(JIMENG_AK)
    svc.set_secret_key(JIMENG_SK)
    svc.set_service("cv")
    svc.set_region("cn-north-1")
    svc.set_version("2022-08-02")
    svc.set_action("CVSync2AsyncSubmitTask")
    payload = json.dumps(submit_payload)
    resp_text = svc.json("POST", "/", {}, payload)
    log(f"    提交响应: {resp_text[:500]}")
    resp_data = json.loads(resp_text)
except ImportError as e:
    log(f"    ❌ volcengine SDK 未安装: {e}")
    log("    尝试直接用 requests 调...")
    import urllib.request, urllib.parse
    # 用手动签名
    host = "visual.volcengineapi.com"
    t = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    date_stamp = t[:8]
    algorithm = "HMAC-SHA256"
    credential_scope = f"{date_stamp}/cn-north-1/cv/request"

    # 简单 HMAC-SHA256 (Python原生)
    def hmac_sha256(key, msg):
        return hmac.new(key.encode(), msg.encode(), hashlib.sha256).digest()

    # 生成签名（简化版，不做完整 AWS SigV4）
    signed_headers = "content-type;host;x-date"
    payload_hash = hashlib.sha256(payload.encode()).hexdigest()

    # 直接用 AK/SK 构造 Authorization 头（volcengine 简化版）
    auth_header = f"HMAC-SHA256 Credential={JIMENG_AK}/{credential_scope}, SignedHeaders=content-type;host, Signature=manual"

    direct_headers = {
        "Content-Type": "application/json",
        "Host": host,
        "X-Date": t,
        "X-TC-Access-Key": JIMENG_AK,
        "X-TC-Action": "CVSync2AsyncSubmitTask",
        "X-TC-Version": "2022-08-02",
        "X-TC-Region": "cn-north-1",
    }
    resp = requests.post(
        f"https://{host}/",
        headers=direct_headers,
        data=payload,
        timeout=30
    )
    resp_text = resp.text
    log(f"    直接请求响应: status={resp.status_code} body={resp_text[:500]}")
    resp_data = json.loads(resp_text)

if resp_data.get("code") == 10000:
    task_id = resp_data["data"]["task_id"]
    log(f"    ✅ 任务提交成功: task_id={task_id}")
else:
    log(f"    ❌ 提交失败: {resp_text}")
    exit(1)

# 轮询结果
log("    轮询等待生成结果...")
for i in range(20):
    time.sleep(3)
    poll_payload = json.dumps({"req_key": "jimeng_t2i_v40", "task_id": task_id})
    try:
        from volcengine.base.Service import Service
        svc2 = Service()
        svc2.set_access_key(JIMENG_AK)
        svc2.set_secret_key(JIMENG_SK)
        svc2.set_service("cv")
        svc2.set_region("cn-north-1")
        svc2.set_version("2022-08-02")
        svc2.set_action("CVSync2AsyncGetResult")
        poll_resp = svc2.json("POST", "/", {}, poll_payload)
    except:
        poll_resp = requests.post(
            f"https://{host}/",
            headers=direct_headers,
            data=poll_payload,
            timeout=30
        ).text

    poll_data = json.loads(poll_resp)
    status = poll_data.get("data", {}).get("status", "?")
    log(f"    轮询{i+1}: status={status}")
    if status == "done":
        # 提取图片
        b64_img = poll_data["data"].get("binary_data_base64") or poll_data["data"].get("image_urls", [None])[0]
        if isinstance(b64_img, str) and len(b64_img) > 1000:
            ai_img_bytes = base64.b64decode(b64_img)
            ai_img_path = os.path.join(TEMP_DIR, "rdUAZI_AI生成图.png")
            with open(ai_img_path, "wb") as f:
                f.write(ai_img_bytes)
            log(f"    ✅ AI图已保存: {ai_img_path}  大小: {len(ai_img_bytes)/1024:.1f}KB")
            break
    elif status in ("failed", "error"):
        log(f"    ❌ 生成失败: {poll_resp[:300]}")
        exit(1)
else:
    log("    ❌ 轮询超时")
    exit(1)

# ════════════════════════════════════════════════════
# 步骤③：上传AI图到腾讯文档
# ════════════════════════════════════════════════════
log("步骤③ 上传AI图到腾讯文档...")

upload_url = "https://docs.qq.com/openapi/resources/v2/images"
with open(ai_img_path, "rb") as f:
    files = {"image": f}
    resp = requests.post(upload_url, headers=HEADERS, files=files, timeout=30)

resp_data = resp.json()
if resp_data.get("ret") == 0:
    image_id = resp_data["data"]["imageID"]
    log(f"    ✅ 上传成功: imageID={image_id[:40]}...")
else:
    log(f"    ❌ 上传失败: {resp_data}")
    exit(1)

# ════════════════════════════════════════════════════
# 步骤④：回写到 AI生成粗略图 字段
# ════════════════════════════════════════════════════
log(f"步骤④ 回写到 rdUAZI 的 AI生成粗略图...")

write_url = f"https://docs.qq.com/openapi/smartbook/v2/files/{FILE_ID}/sheets/{SHEET_ID}"
write_payload = {
    "updateRecords": {
        "records": [{
            "recordID": TARGET_RECORD,
            "values": {
                "AI生成粗略图": [{"imageID": image_id}]
            }
        }]
    }
}
write_resp = requests.post(write_url, headers={**HEADERS, "Content-Type": "application/json"}, json=write_payload, timeout=30)
write_data = write_resp.json()

if write_data.get("ret") == 0:
    written = write_data["data"]["updateRecords"]["records"][0]["values"]
    log(f"    ✅ 回写成功!")
    log(f"    返回数据: {json.dumps(written, ensure_ascii=False)[:500]}")
else:
    log(f"    ❌ 回写失败: {write_data}")

log("\n🎉 完整链路测试完成！")
