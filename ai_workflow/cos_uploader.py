#!/usr/bin/env python3
"""
腾讯云 COS 图片上传
支持两种方式（按优先级）：
  1. SDK（cos-python-sdk-v5，已安装时自动使用）
  2. XML API + TC3 V3 签名（纯标准库，无依赖）

用法：
  python3 cos_uploader.py                        # 测试上传
  python3 cos_uploader.py --local 30b2783.jpg  # 上传指定图片
  python3 cos_uploader.py --local xxx.jpg --key ai/20260425/abc.jpg
  python3 cos_uploader.py --xml                 # 强制 XML API
"""

import json
import hmac
import hashlib
import base64
import time
import urllib.parse
import urllib.request
import urllib.error
import sys
import os
import site
from pathlib import Path
from typing import Optional, Union

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from tencent_env import get_tencent_secret_pair

# ─────────────────────────────────────────────
# 配置
# ─────────────────────────────────────────────
BUCKET     = "etsy-ai-images-1405462135"
REGION     = "ap-shanghai"
SECRET_ID, SECRET_KEY = get_tencent_secret_pair()

# ─────────────────────────────────────────────
# SDK 上传（推荐）
# ─────────────────────────────────────────────

def upload_with_sdk(local_path: Path, remote_key: str = None) -> dict:
    """
    使用 cos-python-sdk-v5 上传，需确保 SDK 已安装：
      pip3 install --user cos-python-sdk-v5
    """
    # 尝试多个可能的 SDK 路径
    sdk_paths = [
        "/Users/mac/Library/Python/3.9/lib/python/site-packages",
        site.getusersitepackages(),
    ]
    for p in sdk_paths:
        if p not in sys.path:
            sys.path.insert(0, p)

    try:
        from qcloud_cos import CosConfig, CosS3Client
        import logging
        logging.disable(logging.CRITICAL)
    except ImportError:
        return None  # 未安装

    if remote_key is None:
        remote_key = f"test/{int(time.time())}/{local_path.name}"

    config = CosConfig(
        Region=REGION,
        SecretId=SECRET_ID,
        SecretKey=SECRET_KEY,
        Token="",
    )
    client = CosS3Client(config)

    with open(local_path, "rb") as f:
        resp = client.put_object(
            Bucket=BUCKET,
            Body=f,
            Key=remote_key,
            ContentType=f"image/{local_path.suffix.lstrip('.').lower()}",
        )

    host = f"{BUCKET}.cos.{REGION}.myqcloud.com"
    encoded_key = urllib.parse.quote(remote_key)
    cdn_url = f"https://{host}/{encoded_key}"
    return {"success": True, "url": cdn_url, "key": remote_key}


# ─────────────────────────────────────────────
# XML API 签名工具（纯标准库备份方案）
# ─────────────────────────────────────────────

def hmac_sha256(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()


def generate_v3_signature(method: str, uri: str, host: str,
                           file_bytes: bytes, content_type: str) -> str:
    now_ts = int(time.time())
    now_str = str(now_ts)
    date_str = now_str[:8]
    scope = f"{date_str}/{REGION}/cos3_request"

    payload_hash = hashlib.sha256(file_bytes).hexdigest()
    canonical_request = (
        f"{method}\n{uri}\n\n"
        f"content-length:{len(file_bytes)}\n"
        f"content-type:{content_type}\n"
        f"host:{host}\n\n"
        f"content-length;content-type;host\n"
        f"{payload_hash}"
    )
    cr_hash = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = f"TC3-HMAC-SHA256\n{now_ts}\n{scope}\n{cr_hash}"

    k_date = hmac_sha256(("TC3" + SECRET_KEY).encode("utf-8"), date_str.encode("utf-8"))
    k_region = hmac_sha256(k_date, REGION.encode("utf-8"))
    k_service = hmac_sha256(k_region, b"cos")
    k_signing = hmac_sha256(k_service, b"cos3_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    return (
        f"TC3-HMAC-SHA256 "
        f"Credential={SECRET_ID}/{scope}, "
        f"SignedHeaders=content-length;content-type;host, "
        f"Signature={signature}"
    )


def upload_via_xml_api(local_path: Path, remote_key: str = None) -> dict:
    """
    XML API + TC3 V3 签名，纯标准库无需第三方依赖
    """
    if remote_key is None:
        remote_key = f"test/{int(time.time())}/{local_path.name}"

    file_bytes = local_path.read_bytes()
    host = f"{BUCKET}.cos.{REGION}.myqcloud.com"
    encoded_key = urllib.parse.quote(remote_key)
    url = f"https://{host}/{encoded_key}"

    suffix = local_path.suffix.lstrip(".").lower()
    ct_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
               "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}
    content_type = ct_map.get(suffix, "application/octet-stream")

    authorization = generate_v3_signature("PUT", f"/{encoded_key}", host,
                                            file_bytes, content_type)

    req = urllib.request.Request(
        url, data=file_bytes, method="PUT",
        headers={
            "Host":           host,
            "Authorization":  authorization,
            "Content-Type":  content_type,
            "Content-Length": str(len(file_bytes)),
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status in (200, 204):
                cdn_url = f"https://{host}/{encoded_key}"
                return {"success": True, "url": cdn_url, "key": remote_key}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"success": False, "error": f"HTTP {e.code}", "detail": body[:300]}
    except Exception as e:
        return {"success": False, "error": str(e)}
    return {"success": False, "error": "unknown"}


# ─────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────

def upload_to_cos(local_path: Union[str, Path],
                  remote_key: str = None,
                  force_xml: bool = False) -> dict:
    """
    上传本地图片到腾讯云 COS，返回访问 URL

    Args:
        local_path:  本地图片路径
        remote_key:  COS 远程路径，如 ai/20260425/abc.jpg
        force_xml:    True=强制使用 XML API（无需 SDK）

    Returns:
        {"success": True, "url": "https://...", "key": "..."}
        {"success": False, "error": "错误信息"}
    """
    local = Path(local_path)
    if not local.exists():
        return {"success": False, "error": f"文件不存在: {local}"}

    # 优先 SDK
    if not force_xml:
        result = upload_with_sdk(local, remote_key)
        if result:
            return result

    # XML API
    return upload_via_xml_api(local, remote_key)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="腾讯云 COS 图片上传")
    parser.add_argument("--local", type=str, default=None, help="本地图片路径")
    parser.add_argument("--key",   type=str, default=None, help="COS 远程路径，如 ai/20260425/abc.jpg")
    parser.add_argument("--xml",   action="store_true", help="强制使用 XML API")
    args = parser.parse_args()

    # 默认测试图
    default_img = Path(__file__).parent.parent / "30b27833525bca99ae1dbe58df6b0f4d.jpg"
    local = Path(args.local) if args.local else default_img

    if not local.exists():
        print(f"❌ 文件不存在: {local}")
        return

    remote_key = args.key or f"test/{int(time.time())}/{local.name}"

    print(f"=== 腾讯云 COS 上传 ===")
    print(f"  文件：{local}（{local.stat().st_size // 1024} KB）")
    print(f"  路径：{remote_key}")
    print(f"  Bucket：{BUCKET}")
    print()

    result = upload_to_cos(local, remote_key, force_xml=args.xml)

    if result["success"]:
        print(f"  ✅ 上传成功")
        print(f"  URL: {result['url']}")
    else:
        print(f"  ❌ 失败: {result['error']}")
        if result.get("detail"):
            print(f"  详情: {result['detail']}")


if __name__ == "__main__":
    main()
