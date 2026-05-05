#!/usr/bin/env python3
"""
重新部署 scf_deploy_v8.zip 到 SCF
方式：先上传到 COS，再通过 COS 地址更新函数代码（避免 base64 大小限制）
v8 = v7 去掉 scf_build/ 目录（根除旧版 volcengine SDK）
"""
import sys, os, time, base64, json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from tencent_env import get_tencent_secret_pair

# ── 配置 ──────────────────────────────────────────
SECRET_ID, SECRET_KEY = get_tencent_secret_pair()
REGION      = "ap-shanghai"
BUCKET      = "etsy-ai-images-1405462135"
FUNCTION_NAME = "etsy-ai-workflow"
ZIP_PATH    = "/Users/mac/Desktop/etsy/运营文档/scf_deploy_v9.zip"
COS_KEY     = "scf/scf_deploy_v9.zip"  # COS 中的对象路径

# ── 1. 上传 zip 到 COS ──────────────────────────
def upload_zip_to_cos():
    print("[1/3] 上传 scf_deploy_v9.zip 到 COS ...")
    try:
        from qcloud_cos import CosConfig, CosS3Client
    except ImportError:
        print("  ❌ qcloud_cos SDK 未安装，正在安装...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "cos-python-sdk-v5"])
        from qcloud_cos import CosConfig, CosS3Client

    config = CosConfig(Region=REGION, SecretId=SECRET_ID, SecretKey=SECRET_KEY, Token="")
    client = CosS3Client(config)

    zip_size = os.path.getsize(ZIP_PATH)
    print(f"  文件大小: {zip_size/1024/1024:.1f} MB")

    with open(ZIP_PATH, "rb") as f:
        client.put_object(Bucket=BUCKET, Body=f, Key=COS_KEY, ContentType="application/zip")

    cos_url = f"https://{BUCKET}.cos.{REGION}.myqcloud.com/{COS_KEY}"
    print(f"  ✅ 上传成功: {cos_url}")
    return COS_KEY

# ── 2. 通过 COS 更新 SCF 函数代码 ─────────────
def update_scf_via_cos(cos_key: str):
    print("\n[2/3] 通过 COS 更新 SCF 函数代码 ...")
    from tencentcloud.scf.v20180416 import scf_client, models
    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile

    cred = credential.Credential(SECRET_ID, SECRET_KEY)
    hp = HttpProfile()
    hp.endpoint = "scf.tencentcloudapi.com"
    profile = ClientProfile()
    profile.httpProfile = hp
    client = scf_client.ScfClient(cred, REGION, profile)

    req = models.UpdateFunctionCodeRequest()
    req.FunctionName = FUNCTION_NAME
    req.Namespace   = "default"
    req.CosBucketName = BUCKET
    req.CosObjectName = cos_key

    resp = client.UpdateFunctionCode(req)
    print(f"  ✅ 代码更新成功！")
    print(f"     RequestId: {resp.RequestId}")
    return resp

# ── 3. 验证部署结果 ─────────────────────────────
def verify_deployment():
    print("\n[3/3] 验证部署 ...")
    time.sleep(5)  # 等待函数更新完成

    from tencentcloud.scf.v20180416 import scf_client, models
    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile

    cred = credential.Credential(SECRET_ID, SECRET_KEY)
    hp = HttpProfile()
    hp.endpoint = "scf.tencentcloudapi.com"
    profile = ClientProfile()
    profile.httpProfile = hp
    client = scf_client.ScfClient(cred, REGION, profile)

    req = models.GetFunctionRequest()
    req.FunctionName = FUNCTION_NAME
    req.Namespace   = "default"

    resp = client.GetFunction(req)
    # GetFunctionResponse 的字段直接暴露，不需要 .FunctionInfo
    print(f"  ✅ 函数名:  {resp.FunctionName}")
    print(f"     状态:    {resp.Status}")
    print(f"     Handler: {resp.Handler}")
    print(f"     Runtime: {resp.Runtime}")
    code_info = getattr(resp, 'CodeInfo', None)
    if code_info:
        print(f"     代码来源: {code_info}")
    print(f"     更新时间: {getattr(resp, 'ModTime', 'N/A')}")

# ── 主流程 ────────────────────────────────────────
def main():
    print("=" * 60)
    print("  🚀 部署 v9 到 SCF（修复签名 bug：query string 写入 canonical request）")
    print("=" * 60)

    if not Path(ZIP_PATH).exists():
        print(f"❌ 找不到 {ZIP_PATH}")
        sys.exit(1)

    cos_key = upload_zip_to_cos()
    update_scf_via_cos(cos_key)
    verify_deployment()

    print("\n" + "=" * 60)
    print("  ✅ 部署完成！")
    print(f"  🔧 函数名:  {FUNCTION_NAME}")
    print(f"  🌐 控制台:   https://console.cloud.tencent.com/scf")
    print("=" * 60)

if __name__ == "__main__":
    main()
