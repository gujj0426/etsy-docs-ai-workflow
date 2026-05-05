#!/usr/bin/env python3
"""
AI 产品图生成 · 生产脚本（SCF 版）
=====================================

全链路：
  腾讯文档 Open API v2 → 下载客户原图 → 即梦4.0 图生图 → 回写「AI生成粗略图」

⚠️ 重要：
  - 禁止使用 MCP 工具，全部通过 requests 调用 Open API v2
  - MCP 返回的图片格式是 CDC ID（无法下载），Open API v2 返回 imageUrl（可直接下载）
  - 图片字段回写：[{"imageID": image_id}]（数组 + imageID，非 imageIDValue）

触发条件（AI 生图流程①）：
  ① 出库日期 ∈ [今天-3天, 今天] 区间
  ② 设计风格 ∈ {宠物头像(见附图), 人物头像(见附图)}
  ③ AI生成粗略图 为空（幂等标记，未生成才触发）

⚠️ workFlowTest 中「AI生成粗略图」列若不存在，脚本会跳过该记录并提示警告

部署到腾讯云 SCF + EventBridge 定时触发（10:00-17:00 每10分钟）
"""

import json, os, re, sys, time, base64, logging, urllib.request, urllib.error, hashlib, hmac
from datetime import date, timedelta, timezone as tz, datetime as dt
from pathlib import Path
from typing import Optional, List, Tuple

# ─────────────────────────────────────────────
# 路径 / 日志
# ─────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).parent.resolve()
_TMP_DIR    = Path(os.environ.get("TMPDIR", "/tmp"))
DATA_DIR    = _TMP_DIR / "scf_ai_workflow"
DATA_DIR.mkdir(parents=True, exist_ok=True)

_log = logging.getLogger("ai_workflow")
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter(
    "[%(asctime)s] %(levelname)s %(message)s", datefmt="%H:%M:%S"))
_log.addHandler(_handler)
_log.setLevel(logging.INFO)


# ─────────────────────────────────────────────
# 凭证
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# 凭证（优先环境变量，兜底配置文件）
# SCF 部署时建议通过「环境配置」传入，避免配置文件遗漏
# ─────────────────────────────────────────────

# 环境变量名
_E_OA2_TOKEN  = "OA2_ACCESS_TOKEN"
_E_OA2_CLIENT = "OA2_CLIENT_ID"
_E_OA2_OPENID = "OA2_OPEN_ID"
_E_OA2_FILEID = "OA2_STORAGE_FILE_ID"
_E_JIMENG_AK  = "JIMENG_AK"
_E_JIMENG_SK  = "JIMENG_SK"

def _env_or(val: str, fallback: str) -> str:
    """环境变量存在则用之，否则用兜底值（空字符串也视为未设置）"""
    return val if val else fallback

# 腾讯文档凭证
OA2_TOKEN  = os.environ.get(_E_OA2_TOKEN,  "")
OA2_CLIENT = os.environ.get(_E_OA2_CLIENT, "")
OA2_OPENID = os.environ.get(_E_OA2_OPENID, "")
OA2_FILEID = os.environ.get(_E_OA2_FILEID, "300000000$KFoUkmaZFqLP")

# 即梦凭证（有兜底默认值）
JIMENG_AK = os.environ.get(_E_JIMENG_AK, "")
JIMENG_SK = os.environ.get(_E_JIMENG_SK, "")

# 若环境变量未设置，从本地配置文件兜底读取
if not OA2_TOKEN:
    for p in [
        _SCRIPT_DIR / "config" / "tdocs_openapi_v2.json",
        _SCRIPT_DIR.parent / "config" / "tdocs_openapi_v2.json",
        Path("/var/user/config/tdocs_openapi_v2.json"),
        _TMP_DIR / "config" / "tdocs_openapi_v2.json",
    ]:
        if p.exists():
            cfg = json.loads(p.read_text())
            OA2_TOKEN  = OA2_TOKEN  or cfg.get("access_token",  "")
            OA2_CLIENT = OA2_CLIENT or cfg.get("client_id",     "")
            OA2_OPENID = OA2_OPENID or cfg.get("open_id",       "")
            OA2_FILEID = OA2_FILEID or cfg.get("storage_file_id_v2", "300000000$KFoUkmaZFqLP")
            JIMENG_AK  = JIMENG_AK or (cfg.get("jimeng_ak") or "")
            JIMENG_SK  = JIMENG_SK or (cfg.get("jimeng_sk") or "")
            _log.info(f"✓ 腾讯文档凭证从配置文件加载: {p}")
            break
    else:
        _log.warning("⚠ 未找到 tdocs_openapi_v2.json，OA2 凭证可能为空，请配置环境变量")

if not OA2_TOKEN:
    raise FileNotFoundError("腾讯文档 access_token 未设置，请配置 OA2_ACCESS_TOKEN 环境变量或 tdocs_openapi_v2.json")

# 即梦：不在代码中嵌入密钥；SCF 生产环境请配置 JIMENG_AK / JIMENG_SK（或本地 config JSON）
if not JIMENG_AK or not JIMENG_SK:
    _log.warning(
        "⚠ JIMENG_AK / JIMENG_SK 未就绪：云函数请在「环境变量」中配置；本地可在 config/tdocs_openapi_v2.json 填写"
    )

# 工作表
SHEET_ID       = "tbfaTE"    # workFlowTest
TRIGGER_STYLES = {"宠物头像(见附图)", "人物头像(见附图)"}
LOOKBACK_DAYS  = 3

# ─────────────────────────────────────────────
# API 基础
# ─────────────────────────────────────────────

def _headers(extra: dict = None) -> dict:
    h = {
        "Access-Token": OA2_TOKEN,
        "Client-Id":    OA2_CLIENT,
        "Open-Id":      OA2_OPENID,
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def api_post(path: str, payload: dict, timeout: int = 30) -> dict:
    url  = f"https://docs.qq.com{path}"
    body = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=body,
        headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        _log.error(f"HTTP {e.code}: {e.read().decode()[:300]}")
        raise


# ─────────────────────────────────────────────
# 日期解析（UTC+8）
# ─────────────────────────────────────────────

CST = tz(timedelta(hours=8))


def parse_ts_ms(raw) -> Optional[date]:
    """解析腾讯文档毫秒时间戳 → date（UTC+8）"""
    if not raw:
        return None
    try:
        ms = int(str(raw))
        # 毫秒级时间戳（13位，如 1777132800000）→ 转秒
        if ms > 1e12:
            ms //= 1000
        # 秒级时间戳（10位，1e9=2001年 ~ 2e10=2033年）
        if 1e9 < ms < 2e10:
            return dt.fromtimestamp(ms, CST).date()
    except (ValueError, OSError, ArithmeticError):
        pass
    return None


# ─────────────────────────────────────────────
# 字段提取（Open API v2 格式）
# ⚠️ MCP 格式 vs Open API v2 格式区别：
#   - MCP 返回：客户原图在 option_value.items[].id（CDC ID，无法下载）
#   - Open API v2 返回：客户原图在 image_value[].imageUrl（CDN URL，可直接下载）
# ─────────────────────────────────────────────

def get_single_select(values: dict, key: str) -> str:
    """从 values 字典中提取单选值"""
    raw = values.get(key, [])
    if isinstance(raw, list) and raw:
        first = raw[0]
        return first.get("text", "") if isinstance(first, dict) else ""
    return ""


def get_text(values: dict, key: str) -> str:
    """提取富文本值"""
    raw = values.get(key, [])
    if isinstance(raw, list) and raw:
        return "".join(i.get("text", "") for i in raw if isinstance(i, dict))
    if isinstance(raw, str):
        return raw
    return ""


def get_images(values: dict, key: str) -> List[dict]:
    """
    提取图片列表（Open API v2 格式）
    返回: [{"id": str, "url": str, "title": str}, ...]
    imageUrl 已含 CDN 公开地址，直接带 Referer 头下载即可
    """
    imgs = values.get(key, [])
    if not isinstance(imgs, list):
        return []
    result = []
    for img in imgs:
        if not isinstance(img, dict):
            continue
        raw_url = img.get("imageUrl") or ""
        if not raw_url:
            continue
        result.append({
            "id":    img.get("id", ""),
            "url":   raw_url.split("?")[0],
            "title": img.get("title", ""),
        })
    return result


def safe_filename(text: str, max_len: int = 80) -> str:
    if not text:
        return ""
    text = re.sub(r'[\\/:*?"<>|]', "_", str(text).strip())
    text = re.sub(r'_+', "_", text)
    return text.strip("_")[:max_len]


# ─────────────────────────────────────────────
# 读取 workFlowTest 并筛选触发行
# ─────────────────────────────────────────────

def fetch_all_sheet_records_raw() -> Tuple[List[dict], bool]:
    """
    分页拉取 workFlowTest 全部原始记录。
    返回 (records, has_ai_col)，has_ai_col 表示表中是否存在「AI生成粗略图」列。
    """
    all_records = []
    offset = 0
    limit  = 100

    while True:
        result = api_post(
            f"/openapi/smartbook/v2/files/{OA2_FILEID}/sheets/{SHEET_ID}",
            {"getRecords": {"offset": offset, "limit": limit}}
        )
        if result.get("ret") != 0:
            raise RuntimeError(f"读取失败 ret={result.get('ret')} msg={result.get('msg')}")

        block    = result.get("data", {}).get("getRecords", {})
        records  = block.get("records", [])
        all_records.extend(records)
        if not block.get("hasMore"):
            break
        offset += limit
        time.sleep(0.3)

    has_ai_col = any("AI生成粗略图" in rec.get("values", {})
                     for rec in all_records)
    return all_records, has_ai_col


def pipeline_record_from_raw(rec: dict, has_ai_col: bool):
    """
    将 Open API 单条 record 转为 main() 使用的字典。
    无客户原图时返回 None。
    """
    values = rec.get("values", {})
    style = get_single_select(values, "设计风格")
    customer_imgs = get_images(values, "客户原图")
    if not customer_imgs:
        return None
    order_no = safe_filename(get_text(values, "订单编号"))
    outdate = parse_ts_ms(values.get("出库日期"))
    return {
        "record_id":      rec.get("recordID", ""),
        "order_no":       order_no or rec.get("recordID", ""),
        "product":        safe_filename(get_single_select(values, "产品名称")),
        "style":          style,
        "color":          get_single_select(values, "颜色"),
        "font":           safe_filename(get_single_select(values, "字体")),
        "designer":       safe_filename(get_single_select(values, "设计师")),
        "customer_imgs":  customer_imgs,
        "outdate":        str(outdate) if outdate else "",
        "_has_ai_col":    has_ai_col,
    }


def fetch_trigger_records(target_date: date = None) -> List[dict]:
    """
    读取 workFlowTest 中符合 AI 生图触发条件的记录

    触发条件（同时满足）：
      ① 出库日期 ∈ [今天-3天, 今天]
      ② 设计风格 ∈ TRIGGER_STYLES
      ③ AI生成粗略图 为空（幂等，已生成则跳过）

    注意：若表格中「AI生成粗略图」列不存在，该字段在 values 中不存在，
          get_images() 返回空列表，等价于"未生成"→ 正常触发
    """
    if target_date is None:
        target_date = dt.now(CST).date()
    start_date = target_date - timedelta(days=LOOKBACK_DAYS)

    _log.info(f"读取 workFlowTest（{start_date} ~ {target_date}）")

    all_records, has_ai_col = fetch_all_sheet_records_raw()

    _log.info(f"共 {len(all_records)} 条记录，开始筛选...")

    triggered = []
    for rec in all_records:
        values = rec.get("values", {})

        # ① 出库日期（边界：start_date ≤ outdate ≤ target_date）
        outdate = parse_ts_ms(values.get("出库日期"))
        if outdate is None or not (start_date <= outdate <= target_date):
            continue

        # ② 设计风格
        style = get_single_select(values, "设计风格")
        if style not in TRIGGER_STYLES:
            continue

        # ③ AI生成粗略图 为空（幂等）
        ai_imgs = get_images(values, "AI生成粗略图")
        if ai_imgs:
            _log.debug(f"  ⏭ 跳过 {rec.get('recordID')}：AI生成粗略图已有值")
            continue

        record = pipeline_record_from_raw(rec, has_ai_col)
        if not record:
            _log.warning(f"  ⏭ 跳过 {rec.get('recordID')}：无客户原图")
            continue

        order_no = record["order_no"]
        triggered.append(record)
        _log.info(
            f"  ✅ {record['record_id']} | {order_no} | {style} | "
            f"{record['color']} | 出库{outdate}"
        )

    if not has_ai_col:
        _log.warning(
            "⚠️ workFlowTest 中不存在「AI生成粗略图」列！"
            "请在腾讯文档中手动添加此列（image 类型），否则无法回写 AI 图。"
        )

    _log.info(f"共触发 {len(triggered)} 条\n")
    return triggered


# ─────────────────────────────────────────────
# 图片下载（Referer 头绕过 CDN 鉴权）
# ─────────────────────────────────────────────

def download_img(url: str, save_path: Path, timeout: int = 30) -> bytes:
    """带 Referer 头下载图片，返回 bytes"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://docs.qq.com/",
        "Origin":  "https://docs.qq.com",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_bytes(data)
    return data


# ─────────────────────────────────────────────
# 即梦4.0 图生图（CV 视觉服务）
# ─────────────────────────────────────────────

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


def get_prompt(style: str, color: str) -> str:
    # 表格 style 值为 "宠物头像(见附图)" / "人物头像(见附图)"，去掉后缀以匹配 PROMPTS key
    style_key = re.sub(r"\(见附图\)$", "", style.strip())
    key = f"黑色_{style_key}" if color in ("黑色", "black", "Black") else f"非黑色_{style_key}"
    return PROMPTS.get(key, PROMPTS.get("非黑色_宠物头像"))


# ─────────────────────────────────────────────
# 火山引擎 HMAC-SHA256 签名（纯 Python，无需 SDK）
# ─────────────────────────────────────────────

def _hmac_sha256(key: bytes, data: str) -> bytes:
    return hmac.new(key, data.encode(), hashlib.sha256).digest()

def _hmac_sha256_hex(key: bytes, data: str) -> str:
    return hmac.new(key, data.encode(), hashlib.sha256).hexdigest()

def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _volc_sign_and_request(action: str, payload: dict,
                            timeout: int = 30, max_retries: int = 5) -> dict:
    """
    火山引擎视觉服务 HMAC-SHA256 签名请求。
    参考 volcengine SDK SignerV4 实现，纯 Python（无 SDK 依赖）。
    """
    host     = "visual.volcengineapi.com"
    endpoint = f"https://{host}"
    body_str = json.dumps(payload)
    body_bytes = body_str.encode()
    api_ver  = "2022-08-31"
    service  = "cv"
    region   = "cn-north-1"

    # 当前时间（UTC）—— 避免 import datetime，用 time.strftime 防 SDK monkey patch
    now_ts   = int(time.time())
    x_date    = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now_ts))
    date_str  = x_date[:8]

    # x-content-sha256: 请求体body的SHA256 hex digest（必需，根据SDK分析）
    body_sha256 = hashlib.sha256(body_bytes).hexdigest()

    # 1. Canonical Request
    signed_headers_list = ["content-type", "host", "x-content-sha256", "x-date"]
    signed_headers_str  = "\n".join(f"{k}:{v}" for k, v in [
        ("content-type", "application/json"),
        ("host", host),
        ("x-content-sha256", body_sha256),
        ("x-date", x_date),
    ]) + "\n"

    canonical_request = "\n".join([
        "POST",                                    # method
        "/",                                       # path
        f"Action={action}&Version={api_ver}",     # query（必须与 URL 中的参数一致！）
        signed_headers_str,
        ";".join(signed_headers_list),             # signed header names
        body_sha256,                              # hashed payload
    ])

    # 2. String to Sign
    credential_scope = f"{date_str}/{region}/{service}/request"
    string_to_sign   = "\n".join([
        "HMAC-SHA256",
        x_date,
        credential_scope,
        _sha256_hex(canonical_request),
    ])

    # 3. Signing Key
    k1 = _hmac_sha256(JIMENG_SK.encode(), date_str)
    k2 = _hmac_sha256(k1, region)
    k3 = _hmac_sha256(k2, service)
    signing_key = _hmac_sha256(k3, "request")
    signature  = _hmac_sha256_hex(signing_key, string_to_sign)

    # 4. Authorization header
    auth = (
        f"HMAC-SHA256 Credential={JIMENG_AK}/{credential_scope}, "
        f"SignedHeaders={';'.join(signed_headers_list)}, Signature={signature}"
    )

    headers = {
        "Authorization": auth,
        "Content-Type":  "application/json",
        "Host":          host,
        "X-Date":        x_date,
        "X-Content-Sha256": body_sha256,
    }

    url = f"{endpoint}/?Action={action}&Version={api_ver}"

    for attempt in range(max_retries + 1):
        try:
            req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode())
            break
        except urllib.error.HTTPError as e:
            err_body = e.read().decode(errors="replace")
            should_retry = False
            if e.code == 429:
                should_retry = True
            else:
                try:
                    err_json = json.loads(err_body)
                    if err_json.get("code") == 50430 or "Concurrent" in err_json.get("message", ""):
                        should_retry = True
                except Exception:
                    pass
            if should_retry and attempt < max_retries:
                wait_time = 2 ** attempt
                _log.warning(f"  ⚠️ 即梦并发超限（尝试 {attempt+1}/{max_retries+1}），{wait_time}s 后重试...")
                time.sleep(wait_time)
                continue
            raise RuntimeError(f"HTTP {e.code}: {err_body[:300]}")

        except Exception as e:
            if attempt < max_retries:
                wait_time = 2 ** attempt
                _log.warning(f"  ⚠️ 请求异常（尝试 {attempt+1}），{wait_time}s 后重试: {e}")
                time.sleep(wait_time)
                continue
            raise

    # 即梦返回扁平结构：{'code': 10000, 'data': {...}, 'message': ...}
    code = result.get("code")
    if code is not None and str(code) != "10000":
        msg = result.get("message", "")
        raise RuntimeError(f"即梦API错误 [{code}]: {msg}")
    return result


def jimeng_generate(image_b64: list, prompt: str,
                    poll_interval: int = 3, max_wait: int = 600) -> dict:
    """调用即梦4.0 CV 视觉服务（纯 HTTP，无 SDK 依赖）"""
    if not JIMENG_AK or not JIMENG_SK:
        raise RuntimeError(
            "即梦凭证未配置：请在环境变量（或本地 config）中设置 JIMENG_AK、JIMENG_SK"
        )

    body = {
        "req_key": "jimeng_t2i_v40",
        "prompt": prompt,
        "binary_data_base64": image_b64,
        "return_url": True,
        "extra": {"seed": 12345},
    }

    _log.info("  即梦提交中（纯HTTP HMAC-SHA256）...")
    submit = _volc_sign_and_request("CVSync2AsyncSubmitTask", body)

    # 即梦返回扁平结构：{'code': 10000, 'data': {'task_id': '...'}, ...}
    code = submit.get("code")
    if code is not None and str(code) != "10000":
        msg = submit.get("message", "")
        raise RuntimeError(f"即梦提交失败 [{code}]: {msg}")

    task_id = submit.get("data", {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"即梦提交响应中未找到 task_id，响应：{str(submit)[:300]}")
    _log.info(f"  即梦任务ID：{task_id}")

    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > max_wait:
            raise TimeoutError(f"任务 {task_id} 超过 {max_wait}s")

        result = _volc_sign_and_request("CVSync2AsyncGetResult", {
            "task_id": task_id, "req_key": "jimeng_t2i_v40"
        })

        resp_data = result.get("data", {})
        # 实际响应字段全部小写（status / binary_data_base64 / image_urls）
        status = resp_data.get("status", "") or resp_data.get("Status", "")
        if status == "done":
            _log.info(f"  ✅ 即梦完成，耗时 {elapsed:.0f}s")
            return {
                "code": 10000,
                "data": {
                    "status": "done",
                    "binary_data_base64": resp_data.get("binary_data_base64") or resp_data.get("BinaryData") or [],
                    "image_urls": resp_data.get("image_urls") or resp_data.get("ImageUrls") or [],
                }
            }
        elif status in ("failed", "not_found", "Failed"):
            raise RuntimeError(f"即梦任务失败：{result}")
        time.sleep(poll_interval)


def extract_image_b64(result: dict) -> list:
    """从即梦响应中提取 binary_data_base64"""
    data    = result.get("data", {})
    b64_list = data.get("binary_data_base64") or []
    if b64_list:
        return b64_list
    # 兜底：从 image_urls 下载
    urls = data.get("image_urls") or []
    if not urls:
        raise RuntimeError("即梦响应中无图片数据")
    req = urllib.request.Request(urls[0], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return [base64.b64encode(resp.read()).decode()]


# ─────────────────────────────────────────────
# 腾讯文档图片上传（Open API v2 multipart）
# ─────────────────────────────────────────────

def upload_image_to_tdocs(image_bytes: bytes, filename: str = "ai_gen.png") -> str:
    """
    上传图片到腾讯文档，返回 imageID
    关键：multipart field name = "image"（不是 "file"）
    """
    import hashlib, uuid

    boundary = "----FormBoundary" + uuid.uuid4().hex[:16]
    ext      = filename.rsplit(".", 1)[-1].lower()
    ct_map   = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "gif": "image/gif", "webp": "image/webp"}
    ct       = ct_map.get(ext, "image/png")

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
        raise RuntimeError(f"图片上传失败：{result}")
    return result["data"]["imageID"]


# ─────────────────────────────────────────────
# 图片字段回写（Open API v2）
# ⚠️ 格式：[{"imageID": image_id}]（数组 + imageID）
# ⚠️ 不是 imageIDValue（那是旧版错误格式）
# ─────────────────────────────────────────────

def write_ai_image(record_id: str, image_id: str) -> bool:
    """回写 image_id 到「AI生成粗略图」字段"""
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
    url = (f"https://docs.qq.com/openapi/smartbook/v2/files/"
           f"{OA2_FILEID}/sheets/{SHEET_ID}")
    req = urllib.request.Request(url,
        data=json.dumps(payload).encode(),
        headers=_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
    ok = result.get("ret") == 0
    if ok:
        _log.info(f"  ✅ 回写成功 record={record_id}")
    else:
        _log.error(f"  ❌ 回写失败 record={record_id} → {result}")
    return ok


# ─────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────


def fetch_pipeline_record_by_id(record_id: str, force: bool = False):
    """
    按 recordID 拉取单行并构造 pipeline 用字典。
    force=False 时若「AI生成粗略图」已有图则报错；force=True 时用于联调强制覆盖。
    """
    raw_list, has_ai_col = fetch_all_sheet_records_raw()
    for rec in raw_list:
        if rec.get("recordID") != record_id:
            continue
        values = rec.get("values", {})
        if not force:
            ai_imgs = get_images(values, "AI生成粗略图")
            if ai_imgs:
                raise RuntimeError(
                    "该行「AI生成粗略图」已有图片；生产流程会跳过。"
                    "联调请使用 --force 强制再生成并覆盖回写。"
                )
        pr = pipeline_record_from_raw(rec, has_ai_col)
        if not pr:
            raise RuntimeError("该行无「客户原图」，无法走通 pipeline")
        return pr
    raise RuntimeError(f"未找到 recordID={record_id!r}")


def process_pipeline_records(records: List[dict]) -> dict:
    """下载原图 → 即梦生图 → 上传腾讯文档 → 回写「AI生成粗略图」。"""
    stats = {"成功": 0, "失败": 0}

    for i, rec in enumerate(records, 1):
        _log.info(f"\n── [{i}/{len(records)}] {rec['order_no']} ──")

        if not rec.get("_has_ai_col"):
            _log.warning("  ⚠️ 表格中无「AI生成粗略图」列，无法回写，跳过")
            _log.info("  → 请在腾讯文档 workFlowTest 中添加「AI生成粗略图」列（image 类型）")
            stats["失败"] += 1
            continue

        customer_img = rec["customer_imgs"][0]
        ext = Path(customer_img.get("title") or "img").suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
            ext = ".jpg"
        local_path = DATA_DIR / f"{rec['order_no']}_原图{ext}"

        try:
            download_img(customer_img["url"], local_path)
            _log.info(f"  ✅ 原图下载：{local_path.name} "
                      f"({local_path.stat().st_size // 1024} KB)")
        except Exception as e:
            _log.error(f"  ❌ 原图下载失败：{e}")
            stats["失败"] += 1
            continue

        img_bytes = local_path.read_bytes()
        img_b64   = [base64.b64encode(img_bytes).decode()]
        prompt    = get_prompt(rec["style"], rec["color"])
        _log.info(f"  Prompt({len(prompt)}字): {prompt[:60]}...")

        if i > 1:
            _log.info("  等待3秒（避免即梦并发限流）...")
            time.sleep(3)

        try:
            result = jimeng_generate(img_b64, prompt)
            gen_b64_list = extract_image_b64(result)
        except Exception as e:
            _log.error(f"  ❌ 即梦生图失败：{e}")
            stats["失败"] += 1
            try:
                local_path.unlink(missing_ok=True)
            except Exception:
                pass
            continue

        first_bytes = base64.b64decode(gen_b64_list[0])
        gen_fname   = f"{rec['order_no']}_AI_{rec['style']}_{rec['color']}.png"
        try:
            image_id = upload_image_to_tdocs(first_bytes, gen_fname)
            _log.info(f"  ✅ 上传成功 imageID={image_id[:20]}...")
            if write_ai_image(rec["record_id"], image_id):
                stats["成功"] += 1
            else:
                stats["失败"] += 1
        except Exception as e:
            _log.error(f"  ❌ 上传/回写失败：{e}")
            stats["失败"] += 1

        try:
            local_path.unlink(missing_ok=True)
        except Exception:
            pass

    _log.info("\n" + "=" * 60)
    _log.info(
        f"执行完成｜成功 {stats['成功']} 条｜失败 {stats['失败']} 条｜"
        f"总计 {len(records)} 条"
    )
    _log.info("=" * 60)
    return stats


def main():
    now = dt.now(CST)
    _log.info("=" * 60)
    _log.info(f"AI 生图流程 启动 | {now.strftime('%Y-%m-%d %H:%M:%S')} CST")
    _log.info("=" * 60)

    _log.info("[Step 1] 读取 workFlowTest 触发行...")
    try:
        records = fetch_trigger_records()
    except Exception as e:
        _log.error(f"读取失败：{e}")
        return

    if not records:
        _log.info("无触发任务，退出。")
        return

    process_pipeline_records(records)


# ─────────────────────────────────────────────
# SCF 入口
# ─────────────────────────────────────────────

def scf_handler(event, context):
    """腾讯云 SCF EventBridge 触发入口"""
    try:
        main()
        return {"statusCode": 200, "body": "OK"}
    except Exception as e:
        _log.exception(f"SCF 异常：{e}")
        return {"statusCode": 500, "body": str(e)}


# ─────────────────────────────────────────────
# 本地调试
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AI 生图生产脚本")
    parser.add_argument("--date", type=str, default=None,
                        help="基准日期，如 2026-04-27（默认今天）")
    parser.add_argument("--days", type=int, default=3, help="回溯天数")
    args = parser.parse_args()

    if args.days != 3:
        LOOKBACK_DAYS = args.days

    if args.date:
        from datetime import datetime as _datetime
        _tgt = _datetime.strptime(args.date, "%Y-%m-%d").date()
        # 仅预览触发行（不执行生图）
        _log.info(f"[调试模式] 基准日期={_tgt}，回溯{LOOKBACK_DAYS}天")
        records = fetch_trigger_records(_tgt)
        _log.info(f"[调试] 找到 {len(records)} 条触发行")
        for r in records:
            _log.info(f"  {r['record_id']} | {r['order_no']} | "
                      f"{r['style']} | {r['color']} | {r['outdate']}")
        _log.info("（调试模式：仅列出触发行，未执行生图。去掉 --date 参数可运行完整流程）")
    else:
        main()
