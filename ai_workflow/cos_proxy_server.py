#!/usr/bin/env python3
"""
本地 COS 上传中转服务器（含 AI 生图集成）
浏览器插件 POST 图片到本服务器，服务器通过 COS SDK 上传到腾讯云，
并提供腾讯文档写入、AI 触发等能力。

启动：python3 cos_proxy_server.py
插件上传地址：http://localhost:8765/upload
"""
import http.server, json, sys, base64, time, cgi, threading, os, hashlib, uuid
from pathlib import Path

from tencent_env import get_tencent_secret_pair

import site
for p in ["/Users/mac/Library/Python/3.9/lib/python/site-packages", site.getusersitepackages()]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from qcloud_cos import CosConfig, CosS3Client
    import logging; logging.disable(logging.CRITICAL)
    HAS_SDK = True
except ImportError:
    HAS_SDK = False

# ── 凭证 ──────────────────────────────────────────────
BUCKET      = "etsy-ai-images-1405462135"
REGION      = "ap-shanghai"
PORT        = 8765

SCRIPT_DIR  = Path(__file__).parent

if str(SCRIPT_DIR.resolve()) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.resolve()))

# 加载腾讯文档 Open API v2 凭证（config/ 在 ai_workflow/ 的上一级目录）
TDX_CFG = {}
CONFIG_PATH = SCRIPT_DIR.parent / "config" / "tdocs_openapi_v2.json"
if CONFIG_PATH.exists():
    with open(CONFIG_PATH) as f:
        TDX_CFG = json.load(f)

OA2_TOKEN   = TDX_CFG.get("access_token", "")
OA2_CLIENT  = TDX_CFG.get("client_id", "")
OA2_OPENID  = TDX_CFG.get("open_id", "")
OA2_FILEID  = TDX_CFG.get("storage_file_id_v2", "300000000$KFoUkmaZFqLP")
JIMENG_AK   = TDX_CFG.get("jimeng_ak", "")
JIMENG_SK   = TDX_CFG.get("jimeng_sk", "")
SHEET_ID    = TDX_CFG.get("workFlowTest", {}).get("sheet_id", "tbfaTE")

# COS SDK client
sdk_client = None
if HAS_SDK:
    _cos_sid, _cos_sk = get_tencent_secret_pair()
    sdk_client = CosS3Client(CosConfig(
        Region=REGION,
        SecretId=_cos_sid,
        SecretKey=_cos_sk,
        Token='',
    ))
    print("✅ COS SDK 就绪")

# ── 即梦4.0 Prompt ────────────────────────────────────
PROMPTS = {
    "黑色_宠物头像": (
        "将参考图片转换为精细黑白木刻版画风格，用于woodbox激光雕刻。"
        "严格遵守：1. 百分之百精准还原图中宠物的五官、轮廓、毛发纹理，绝不添加、删减或扭曲任何原有特征 "
        "2. 绝对纯净纯黑背景——无任何纹理、无任何颗粒、无任何渐变，背景与主体之间绝对分明，宠物主体完全剥离无残留 "
        "3. 主体（宠物）为纯白线稿，毛发/皮肤：极细密排线+交叉排线，线条间距极小，线条数量最大化，拒绝稀疏线条 "
        "4. 高对比纯黑白，无灰色中间调，重点区域（五官、毛发轮廓、身体边缘）线条极密集 "
        "5. 工笔画般的精微细节，拒绝块状涂抹"
    ),
    "黑色_人物头像": (
        "将参考图片转换为精细黑白木刻版画风格，用于woodbox激光雕刻。"
        "严格遵守：1. 百分之百精准还原图中的人物五官、轮廓、神态，绝不添加、删减或扭曲任何原有特征 "
        "2. 绝对纯净纯黑背景——无任何纹理、无任何颗粒、无任何渐变，背景与主体之间绝对分明，人物主体完全剥离无残留 "
        "3. 主体（人物）为纯白线稿，肤质/五官/头发：极细密排线+交叉排线，线条间距极小，线条数量最大化，拒绝稀疏线条 "
        "4. 高对比纯黑白，无灰色中间调，重点区域（五官、面部轮廓、手部）线条极密集 "
        "5. 工笔画般的精微细节，拒绝块状涂抹"
    ),
    "非黑色_宠物头像": (
        "将参考图片转换为精微素描手绘风格，用于woodbox激光雕刻。"
        "严格遵守：1. 百分之百精准还原图中的宠物 "
        "2. 完整保留原始宠物主体的所有细节特征，包括轮廓、质感、神态 "
        "3. 白色底，黑白线稿，精微素描手绘风格，无任何背景元素残留，宠物的主体轮廓完全剥离 "
        "4. 毛发/纹理：超精细单根线条 "
        "5. 高对比纯黑白，无灰色中间调，线条粗细对比强烈 "
        "6. 工笔画般的精微细节，拒绝块状涂抹"
    ),
    "非黑色_人物头像": (
        "将参考图片转换为精微素描手绘风格，用于woodbox激光雕刻。"
        "严格遵守：1. 百分之百精准还原图中的人物 "
        "2. 完整保留原始人物主体的所有细节特征，包括轮廓、质感、神态 "
        "3. 白色底，黑白线稿，精微素描手绘风格，无任何背景元素残留，人物的主体轮廓完全剥离 "
        "4. 五官/皮肤：超精细单根线条 "
        "5. 高对比纯黑白，无灰色中间调，线条粗细对比强烈 "
        "6. 工笔画般的精微细节，拒绝块状涂抹"
    ),
}

# ── 工具函数 ──────────────────────────────────────────
def get_prompt(style: str, color: str) -> str:
    style_key = style.replace("(见附图)", "").strip()
    key = f"黑色_{style_key}" if color in ("黑色", "black", "Black") else f"非黑色_{style_key}"
    return PROMPTS.get(key, PROMPTS.get("非黑色_宠物头像"))

def tdx_headers() -> dict:
    return {
        "Access-Token": OA2_TOKEN,
        "Client-Id":    OA2_CLIENT,
        "Open-Id":      OA2_OPENID,
        "Content-Type": "application/json",
    }

def tdx_api_post(path: str, payload: dict, timeout: int = 30) -> dict:
    """调用腾讯文档 Open API v2"""
    import urllib.request, urllib.error
    url  = f"https://docs.qq.com{path}"
    body = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=body,
        headers=tdx_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def upload_image_to_tdocs(image_bytes: bytes, filename: str = "img.png") -> str:
    """上传图片到腾讯文档，返回 imageID"""
    import urllib.request, urllib.error
    ext = filename.rsplit(".", 1)[-1].lower()
    ct_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
              "gif": "image/gif", "webp": "image/webp"}
    ct = ct_map.get(ext, "image/png")
    boundary = "----FormBoundary" + uuid.uuid4().hex[:16]
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        f"Content-Type: {ct}\r\n\r\n"
    ).encode() + image_bytes + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        "https://docs.qq.com/openapi/resources/v2/images",
        data=body,
        headers={
            "Access-Token": OA2_TOKEN,
            "Client-Id":    OA2_CLIENT,
            "Open-Id":      OA2_OPENID,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode())
    if result.get("ret") != 0:
        raise RuntimeError(f"TDX 图片上传失败：{result}")
    return result["data"]["imageID"]

def download_bytes(url: str) -> bytes:
    """下载图片字节"""
    import urllib.request, urllib.error
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://docs.qq.com/",
        "Origin": "https://docs.qq.com",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()

def jimeng_generate(image_b64_list: list, prompt: str) -> dict:
    """调用即梦4.0 CV 视觉服务，轮询等待结果"""
    try:
        from volcengine.visual.VisualService import VisualService
    except ImportError:
        raise RuntimeError("volcengine SDK 未安装！请运行: pip3 install volcengine")

    client = VisualService()
    client.set_ak(JIMENG_AK)
    client.set_sk(JIMENG_SK)

    body = {
        "req_key": "jimeng_t2i_v40",
        "prompt": prompt,
        "binary_data_base64": image_b64_list,
        "return_url": True,
        "seed": 12345,
    }
    submit = client.cv_sync2async_submit_task(body)
    if submit.get("code") != 10000:
        raise RuntimeError(f"即梦提交失败：{submit}")
    task_id = submit["data"]["task_id"]
    print(f"    即梦任务ID: {task_id}")

    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > 300:
            raise TimeoutError(f"任务 {task_id} 超过 300s")
        result = client.cv_sync2async_get_result({
            "task_id": task_id, "req_key": "jimeng_t2i_v40"})
        status = result.get("data", {}).get("status", "")
        print(f"    状态: {status} ({elapsed:.0f}s)")
        if status == "done":
            print(f"    ✅ 即梦完成，耗时 {elapsed:.0f}s")
            return result
        elif status in ("failed", "not_found"):
            raise RuntimeError(f"即梦任务失败：{result}")
        time.sleep(3)

def write_field(record_id: str, field_name: str, value: dict) -> bool:
    """写入字段值到腾讯文档"""
    payload = {
        "action": 2,
        "updateRecords": {
            "records": [{
                "recordID": record_id,
                "values": {field_name: value}
            }]
        }
    }
    url = f"/openapi/smartbook/v2/files/{OA2_FILEID}/sheets/{SHEET_ID}"
    result = tdx_api_post(url, payload)
    ok = result.get("ret") == 0
    if ok:
        print(f"    ✅ 回写成功: {field_name} → record={record_id}")
    else:
        print(f"    ❌ 回写失败: {result}")
    return ok


# ── HTTP Handler ───────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {fmt % args}")

    def send_cors(self, code=200):
        self.send_response(code)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_cors(200)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def send_json(self, code: int, data: dict):
        self.send_cors(code)
        self.send_header('Content-Type', 'application/json')
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ── /upload: 上传图片到 COS ──────────────────────────
    def do_POST_upload(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(length)
            content_type = self.headers.get('Content-Type', '')

            if 'application/json' in content_type:
                data = json.loads(raw.decode('utf-8'))
                filename = data.get('filename', f'img_{int(time.time())}.jpg')
                image_data = base64.b64decode(data['imageBase64'])
            else:
                raise ValueError(f'Unsupported Content-Type: {content_type}')

            today = time.strftime('%Y%m%d')
            object_key = f'ai/{today}/{int(time.time()*1000)}_{filename}'
            host = f'{BUCKET}.cos.{REGION}.myqcloud.com'
            cdn_url = f'https://{host}/{object_key}'

            if sdk_client:
                resp = sdk_client.put_object(
                    Bucket=BUCKET, Body=image_data, Key=object_key,
                    ContentType='image/jpeg',
                )
                print(f"  SDK上传成功: {object_key} → {resp.get('ETag','OK')}")
            else:
                print("  ⚠️ SDK 不可用，跳过实际上传")

            self.send_json(200, {
                'success': True,
                'cdnUrl': cdn_url,
                'objectKey': object_key,
            })

        except Exception as e:
            print(f"  ❌ {e}")
            self.send_json(500, {'success': False, 'error': str(e)})

    # ── /write_tdocs: 写入 CDN URL 到客户原图字段 ─────────
    def do_POST_write_tdocs(self):
        """
        请求体: {record_id, cdnUrl, style, color}
        作用: 将 CDN URL 上传到 TDX 并写入"客户原图"字段
        """
        try:
            length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(length).decode('utf-8'))

            record_id = data.get('record_id')
            cdn_url   = data.get('cdnUrl')
            if not record_id or not cdn_url:
                raise ValueError("缺少 record_id 或 cdnUrl")

            print(f"[write_tdocs] record={record_id} url={cdn_url[:60]}...")

            # 方案：从 CDN 下载图片 → 上传到 TDX → 获取 imageID → 写入字段
            img_bytes = download_bytes(cdn_url)
            fname = cdn_url.split('/')[-1].split('?')[0] or "customer.jpg"
            image_id = upload_image_to_tdocs(img_bytes, fname)

            ok = write_field(record_id, "客户原图", [{"imageID": image_id}])
            self.send_json(200, {'success': ok, 'imageID': image_id, 'cdnUrl': cdn_url})

        except Exception as e:
            print(f"[write_tdocs] ❌ {e}")
            self.send_json(500, {'success': False, 'error': str(e)})

    # ── /trigger_ai: 触发 AI 生图 ────────────────────────
    def do_POST_trigger_ai(self):
        """
        请求体: {record_id, style, color}
        作用: 读取该行的客户原图 → 即梦4.0生图 → 回写"AI生成粗略图"
        """
        try:
            length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(length).decode('utf-8'))

            record_id = data.get('record_id')
            style     = data.get('style', '宠物头像(见附图)')
            color     = data.get('color', '')

            if not record_id:
                raise ValueError("缺少 record_id")

            print(f"[trigger_ai] record={record_id} style={style} color={color}")

            # ① 读取该记录的客户原图 URL
            result = tdx_api_post(
                f"/openapi/smartbook/v2/files/{OA2_FILEID}/sheets/{SHEET_ID}",
                {"getRecords": {"offset": 0, "limit": 100}}
            )
            if result.get("ret") != 0:
                raise RuntimeError(f"读取记录失败: {result}")

            records = result.get("data", {}).get("getRecords", {}).get("records", [])
            target = None
            for rec in records:
                if rec.get("recordID") == record_id:
                    target = rec.get("values", {})
                    break

            if not target:
                raise RuntimeError(f"未找到 record_id={record_id} 的记录")

            # 提取客户原图 URL（image_value[].imageUrl）
            customer_imgs = target.get("客户原图", [])
            if not isinstance(customer_imgs, list) or not customer_imgs:
                raise RuntimeError("客户原图字段为空")
            img_item = customer_imgs[0]
            img_url = img_item.get("imageUrl", "")
            if not img_url:
                raise RuntimeError("客户原图 imageUrl 为空")

            print(f"  客户原图 URL: {img_url[:60]}...")

            # ② 下载原图
            img_bytes = download_bytes(img_url)
            print(f"  原图大小: {len(img_bytes)//1024} KB")

            # ③ 即梦4.0 生图
            img_b64 = base64.b64encode(img_bytes).decode()
            prompt  = get_prompt(style, color)
            print(f"  Prompt({len(prompt)}字): {prompt[:50]}...")
            jm_result = jimeng_generate([img_b64], prompt)

            # 提取生成图
            gen_b64_list = jm_result.get("data", {}).get("binary_data_base64") or []
            if not gen_b64_list:
                urls = jm_result.get("data", {}).get("image_urls") or []
                if urls:
                    gen_bytes = download_bytes(urls[0])
                else:
                    raise RuntimeError("即梦响应无图片数据")
            else:
                gen_bytes = base64.b64decode(gen_b64_list[0])

            print(f"  AI图大小: {len(gen_bytes)//1024} KB")

            # ④ 上传到 TDX
            ai_fname = f"{record_id}_AI.png"
            ai_image_id = upload_image_to_tdocs(gen_bytes, ai_fname)
            print(f"  TDX imageID: {ai_image_id[:20]}...")

            # ⑤ 回写 AI生成粗略图
            ok = write_field(record_id, "AI生成粗略图", [{"imageID": ai_image_id}])

            self.send_json(200, {
                'success': ok,
                'aiImageID': ai_image_id,
                'recordID': record_id,
            })

        except Exception as e:
            print(f"[trigger_ai] ❌ {e}")
            self.send_json(500, {'success': False, 'error': str(e)})

    def do_POST(self):
        path = self.path.split('?')[0].rstrip('/')
        if path == '/upload':
            self.do_POST_upload()
        elif path == '/write_tdocs':
            self.do_POST_write_tdocs()
        elif path == '/trigger_ai':
            self.do_POST_trigger_ai()
        else:
            self.send_json(404, {'error': f'未知端点: {self.path}'})

    def do_GET(self):
        if self.path == '/health':
            self.send_json(200, {
                'status': 'ok',
                'sdk': HAS_SDK,
                'tdx_configured': bool(OA2_TOKEN),
                'jimeng_configured': bool(JIMENG_AK),
            })
        else:
            self.send_json(404, {'error': '只支持 POST 请求'})


if __name__ == '__main__':
    print(f"""
╔════════════════════════════════════════════════════╗
║  📦 COS 上传中转服务器（含 AI 生图集成）          ║
║                                                    ║
║  POST http://localhost:{PORT}/upload        上传图片到COS  ║
║  POST http://localhost:{PORT}/write_tdocs   写入客户原图   ║
║  POST http://localhost:{PORT}/trigger_ai    触发AI生图   ║
║  GET  http://localhost:{PORT}/health        健康检查       ║
║                                                    ║
║  按 Ctrl+C 停止                                   ║
╚════════════════════════════════════════════════════╝
""")
    server = http.server.HTTPServer(('', PORT), Handler)
    print(f"🚀 启动成功，监听 http://localhost:{PORT}")
    server.serve_forever()
