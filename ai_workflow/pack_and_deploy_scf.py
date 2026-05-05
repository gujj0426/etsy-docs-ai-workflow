#!/usr/bin/env python3
"""
使用腾讯云官方 API 部署 SCF（不经 MCP；仓库内无腾讯云 MCP Server）。

流程：
  1. zip（默认仅 index.py + scf_pipeline.py，不含密钥文件）
  2. COS PutObject（cos-python-sdk-v5）
  3. SCF UpdateFunctionCode（从 COS 引用，TencentCloud API）

部署账号凭证（上传 zip 到 COS / 更新 SCF）：
  环境变量 TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY
  （或 TENCENT_SECRET_* / COS_SECRET_*），见 tencent_env.py。

云函数运行时请在控制台配置环境变量（勿打进 zip）：
  OA2_ACCESS_TOKEN, OA2_CLIENT_ID, OA2_OPEN_ID
  可选 OA2_STORAGE_FILE_ID（默认已有）
  JIMENG_AK, JIMENG_SK
"""
from __future__ import annotations

import argparse
import io
import sys
import time
import zipfile
from pathlib import Path

_WORKFLOW = Path(__file__).resolve().parent
if str(_WORKFLOW) not in sys.path:
    sys.path.insert(0, str(_WORKFLOW))

from tencent_env import get_tencent_secret_pair
_DOC_ROOT = _WORKFLOW.parent
_CFG_SRC = _DOC_ROOT / "config" / "tdocs_openapi_v2.json"

REGION = "ap-shanghai"
BUCKET = "etsy-ai-images-1405462135"
FUNCTION_NAME = "etsy-ai-workflow"
COS_PREFIX = "scf"

# 云函数需配置的环境变量（打印提示用）
SCF_RUNTIME_ENV_HINT = """
────────────────────────────────────────
请在腾讯云 SCF → etsy-ai-workflow →「环境变量」中配置（示例键名）：
  OA2_ACCESS_TOKEN    腾讯文档 access_token
  OA2_CLIENT_ID       Client-Id
  OA2_OPEN_ID         Open-Id
  OA2_STORAGE_FILE_ID 可选，默认 300000000$KFoUkmaZFqLP
  JIMENG_AK           火山即梦 AK
  JIMENG_SK           火山即梦 SK（与控制台一致，常为 Base64 形态字符串）
────────────────────────────────────────
"""


def _read_tencent_credentials():
    """上传代码包用的腾讯云主账号/子账号密钥（非 OA2）。"""
    return get_tencent_secret_pair()


def _build_zip_bytes(include_config: bool) -> tuple[bytes, list[str]]:
    """打入 zip；默认不带腾讯文档/即梦密钥文件。"""
    arc: list[tuple[Path, str]] = [
        (_WORKFLOW / "index.py", "index.py"),
        (_WORKFLOW / "scf_pipeline.py", "scf_pipeline.py"),
    ]
    for src, _ in arc:
        if not src.is_file():
            raise FileNotFoundError(f"缺少: {src}")

    if include_config:
        if not _CFG_SRC.is_file():
            raise FileNotFoundError(f"选用 --with-config 但未找到: {_CFG_SRC}")
        arc.append((_CFG_SRC, "config/tdocs_openapi_v2.json"))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for src, name in arc:
            zf.write(src, name)
    data = buf.getvalue()
    names = [n for _, n in arc]
    return data, names


def _upload_cos(secret_id: str, secret_key: str, key: str, body: bytes) -> None:
    from qcloud_cos import CosConfig, CosS3Client

    cfg = CosConfig(Region=REGION, SecretId=secret_id, SecretKey=secret_key, Token="")
    client = CosS3Client(cfg)
    client.put_object(Bucket=BUCKET, Body=body, Key=key, ContentType="application/zip")
    print(f"  COS PutObject OK: cos://{BUCKET}/{key}")


def _update_scf_from_cos(secret_id: str, secret_key: str, cos_key: str) -> str:
    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.scf.v20180416 import scf_client, models

    cred = credential.Credential(secret_id, secret_key)
    hp = HttpProfile()
    hp.endpoint = "scf.tencentcloudapi.com"
    profile = ClientProfile()
    profile.httpProfile = hp
    client = scf_client.ScfClient(cred, REGION, profile)

    req = models.UpdateFunctionCodeRequest()
    req.FunctionName = FUNCTION_NAME
    req.Namespace = "default"
    req.CosBucketName = BUCKET
    req.CosObjectName = cos_key

    resp = client.UpdateFunctionCode(req)
    rid = getattr(resp, "RequestId", "") or ""
    print(f"  SCF UpdateFunctionCode OK | RequestId={rid}")
    return rid


def _verify(secret_id: str, secret_key: str) -> None:
    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.scf.v20180416 import scf_client, models

    time.sleep(3)
    cred = credential.Credential(secret_id, secret_key)
    hp = HttpProfile()
    hp.endpoint = "scf.tencentcloudapi.com"
    profile = ClientProfile()
    profile.httpProfile = hp
    client = scf_client.ScfClient(cred, REGION, profile)
    req = models.GetFunctionRequest()
    req.FunctionName = FUNCTION_NAME
    req.Namespace = "default"
    resp = client.GetFunction(req)
    print(f"  GetFunction: Status={resp.Status} | Handler={resp.Handler} | ModTime={getattr(resp, 'ModTime', 'N/A')}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="腾讯云 COS + SCF API 更新函数代码（不含 MCP）",
    )
    ap.add_argument(
        "--with-config",
        action="store_true",
        help="将 config/tdocs_openapi_v2.json 一并打入 zip（不推荐生产；仅调试）",
    )
    ap.add_argument(
        "--cos-key",
        default=f"{COS_PREFIX}/scf_deploy_auto.zip",
        help="COS 对象键（默认 %(default)s）",
    )
    args = ap.parse_args()

    print("=" * 60)
    print(f"  腾讯云 API 部署 → {FUNCTION_NAME} ({REGION})")
    print("  （COS PutObject + SCF UpdateFunctionCode）")
    print("=" * 60)

    zip_body, arcnames = _build_zip_bytes(include_config=args.with_config)
    print(f"  打包: {len(zip_body) / 1024:.1f} KB | 文件: {arcnames}")

    sid, sk = _read_tencent_credentials()

    print("[1/3] COS API 上传 zip ...")
    try:
        _upload_cos(sid, sk, args.cos_key, zip_body)
    except ImportError:
        print("  安装 cos-python-sdk-v5 ...")
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "cos-python-sdk-v5"])
        _upload_cos(sid, sk, args.cos_key, zip_body)

    print("[2/3] SCF API 更新代码 ...")
    _update_scf_from_cos(sid, sk, args.cos_key)

    print("[3/3] SCF API 校验函数 ...")
    _verify(sid, sk)

    print("\n✅ 部署完成。")
    if not args.with_config:
        print(SCF_RUNTIME_ENV_HINT)
    print(
        "控制台: "
        "https://console.cloud.tencent.com/scf/detail?rid=8&ns=default&id=etsy-ai-workflow"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
