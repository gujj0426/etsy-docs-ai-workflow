#!/usr/bin/env python3
"""
即梦AI 图生图调用脚本
模型：jimeng_i2i_v30（即梦3.0图生图）
认证：HMAC-SHA256 AWS4签名
"""

import hashlib
import hmac
import base64
import json
import time
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlencode
import requests
from requests.exceptions import RequestException


# ==================== 凭证配置（环境变量，与 scf_pipeline 一致）====================
def _jimeng_ak_sk() -> tuple:
    ak = os.environ.get("JIMENG_AK", "").strip()
    sk = os.environ.get("JIMENG_SK", "").strip()
    if not ak or not sk:
        raise RuntimeError("请设置环境变量 JIMENG_AK、JIMENG_SK（与云函数/本地 config 一致）")
    return ak, sk

# ==================== 提示词模板 ====================
# 木刻版画最佳提示词（2026-04-18 实测验证，适用于黑色狗牌激光雕刻宠物头像）
PROMPT_WOODCUT_BEST = (
    "将参考图片转换为精细黑白木刻版画风格，用于woodbox激光雕刻。"
    "严格遵守：1. 完整保留原始主体的所有细节特征，包括轮廓、质感、神态 "
    "2. 纯黑背景，无任何背景元素残留，主体完全剥离 "
    "3. 毛发/纹理：超精细单根线条 "
    "4. 高对比纯黑白，无灰色中间调，线条粗细对比强烈 "
    "5. 工笔画般的精微细节，拒绝块状涂抹"
)
WOODCUT_SEED = 12345  # 固定 seed 复现最佳效果

# ==================== API常量 ====================
HOST = "visual.volcengineapi.com"
ENDPOINT = "https://visual.volcengineapi.com"
REGION = "cn-north-1"
SERVICE = "cv"
ACTION = "CVProcess"
VERSION = "2022-08-31"


class VolcEngineSigner:
    """火山引擎 AWS4 签名"""

    def __init__(self, ak, sk, region, service):
        self.ak = ak
        self.sk = sk
        self.region = region
        self.service = service

    def _sha256(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _hmac_sha256(self, key: bytes, content: str) -> bytes:
        return hmac.new(key, content.encode("utf-8"), hashlib.sha256).digest()

    def _signing_key(self, short_date: str) -> bytes:
        k_date = self._hmac_sha256(self.sk.encode("utf-8"), short_date)
        k_region = self._hmac_sha256(k_date, self.region)
        k_service = self._hmac_sha256(k_region, self.service)
        return self._hmac_sha256(k_service, "request")

    def _url_encode(self, s: str) -> str:
        from urllib.parse import quote
        return quote(s, safe="")


def build_signed_request(signer: VolcEngineSigner, body: dict) -> dict:
    """构建带签名的请求头"""
    now = datetime.now(timezone.utc)
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    short_date = x_date[:8]

    body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
    body_hash = signer._sha256(body_bytes)
    content_type = "application/json"

    # Query string
    query_params = {"Action": ACTION, "Version": VERSION}
    canonical_querystring = "&".join(
        f"{signer._url_encode(k)}={signer._url_encode(v)}"
        for k, v in sorted(query_params.items())
    )

    # Canonical request
    canonical_request = (
        f"POST\n/\n{canonical_querystring}\n"
        f"host:{HOST}\n"
        f"x-date:{x_date}\n"
        f"x-content-sha256:{body_hash}\n"
        f"content-type:{content_type}\n\n"
        f"host;x-date;x-content-sha256;content-type\n"
        f"{body_hash}"
    )

    # String to sign
    hashed_canonical = signer._sha256(canonical_request.encode("utf-8"))
    credential_scope = f"{short_date}/{signer.region}/{signer.service}/request"
    string_to_sign = f"HMAC-SHA256\n{x_date}\n{credential_scope}\n{hashed_canonical}"

    # Signature
    signing_key = signer._signing_key(short_date)
    signature = hmac.new(
        signing_key,
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    authorization = (
        f"HMAC-SHA256 Credential={signer.ak}/{credential_scope}, "
        f"SignedHeaders=host;x-date;x-content-sha256;content-type, "
        f"Signature={signature}"
    )

    url = f"{ENDPOINT}/?{canonical_querystring}"
    headers = {
        "Content-Type": content_type,
        "Host": HOST,
        "X-Date": x_date,
        "X-Content-Sha256": body_hash,
        "Authorization": authorization,
    }

    return url, headers, body_bytes


def call_jimeng_i2i(image_path: str, prompt: str, output_path: str = None,
                    seed: int = None) -> dict:
    """
    调用即梦图生图

    Args:
        image_path: 客户原图路径
        prompt: 图片描述/prompt
        output_path: 保存生成图的路径（可选）
        seed: 随机种子（固定值可复现结果）

    Returns:
        API响应结果 dict
    """
    # 读取并转base64
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    body = {
        "req_key": "jimeng_i2i_v30",
        "prompt": prompt,
        "binary_data_base64": [image_b64],
        "return_url": True,
    }
    if seed is not None:
        body["seed"] = seed

    ak, sk = _jimeng_ak_sk()
    signer = VolcEngineSigner(ak, sk, REGION, SERVICE)
    url, headers, body_bytes = build_signed_request(signer, body)

    print(f"[即梦] 请求发送中...")
    print(f"[即梦] prompt: {prompt}")

    try:
        resp = requests.post(url, headers=headers, data=body_bytes, timeout=120)
        resp.raise_for_status()
        result = resp.json()
    except RequestException as e:
        return {"error": str(e), "success": False}

    # 解析结果
    if result.get("code") == 10000 or result.get("status") == 10000:
        image_urls = result.get("data", {}).get("image_urls", [])
        if image_urls:
            print(f"[即梦] ✅ 生成成功！耗时: {result.get('time_elapsed', 'N/A')}")
            print(f"[即梦] 图片URL: {image_urls[0]}")

            # 下载图片
            if output_path:
                download_image(image_urls[0], output_path)
                print(f"[即梦] 图片已保存: {output_path}")

            return {
                "success": True,
                "image_url": image_urls[0],
                "image_urls": image_urls,
                "request_id": result.get("request_id"),
                "time_elapsed": result.get("time_elapsed"),
            }
        else:
            print(f"[即梦] ❌ 未返回图片URL: {result}")
            return {"success": False, "raw": result}
    else:
        print(f"[即梦] ❌ 调用失败: {result.get('message', result)}")
        return {"success": False, "raw": result}


def download_image(url: str, output_path: str):
    """下载图片到本地"""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(resp.content)


# ==================== 主程序 ====================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="即梦AI 图生图调用脚本")
    parser.add_argument("image", help="原图路径")
    parser.add_argument("prompt", nargs="?", default=None, help="提示词（省略则用默认）")
    parser.add_argument("output", nargs="?", default=None, help="输出路径")
    parser.add_argument("--seed", type=int, default=None, help="随机种子（如省略则不固定）")
    parser.add_argument("--woodcut", action="store_true",
                        help="使用木刻版画最佳提示词 + seed=12345")
    args = parser.parse_args()

    if args.woodcut:
        prompt = PROMPT_WOODCUT_BEST
        seed = args.seed if args.seed is not None else WOODCUT_SEED
        output = args.output or "woodcut_output.png"
    else:
        prompt = args.prompt or "专业产品展示图，白色背景，高清摄影"
        seed = args.seed
        output = args.output

    if not os.path.exists(args.image):
        print(f"[错误] 图片不存在: {args.image}")
        sys.exit(1)

    print(f"[即梦] 调用参数: seed={seed}, prompt={prompt[:80]}...")
    result = call_jimeng_i2i(args.image, prompt, output, seed=seed)
    print(json.dumps(result, ensure_ascii=False, indent=2))
