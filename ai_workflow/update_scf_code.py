#!/usr/bin/env python3
"""
Update SCF function code - Fixed version
修复内容：
1. 使用 glob 动态匹配最新 scf_deploy_v*.zip（避免硬编码旧版本）
2. 优先使用 redeploy_v7.py（COS 中转，支持大文件）
3. 如果 redeploy_v7.py 成功，不再重复调用 UpdateFunctionCode
4. 如果失败，回退到 base64 方式
"""

import json, base64, sys, glob, subprocess

_SCRIPT_DIR = __import__("pathlib").Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

from tencent_env import get_tencent_secret_pair
from tencentcloud.scf.v20180416 import scf_client
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.scf.v20180416.models import UpdateFunctionCodeRequest

SECRET_ID, SECRET_KEY = get_tencent_secret_pair()

# ============================================================================
# Step 1: 找到最新的部署包（避免硬编码旧版本）
# ============================================================================
zip_candidates = sorted(glob.glob('/Users/mac/Desktop/etsy/运营文档/scf_deploy_v*.zip'))
if not zip_candidates:
    raise FileNotFoundError("❌ 找不到 scf_deploy_v*.zip，请先运行 scf_deployment_packager.py 生成部署包")

zip_path = zip_candidates[-1]  # 最新版本
print(f"✅ 使用部署包: {zip_path}")

# ============================================================================
# Step 2: 优先使用 redeploy_v7.py（COS 中转方式）
# ============================================================================
print("\n尝试方式1: 使用 redeploy_v7.py (COS 中转)...")
result = subprocess.run(
    [sys.executable, '/Users/mac/Desktop/etsy/运营文档/ai_workflow/redeploy_v7.py'],
    capture_output=True,
    text=True,
    timeout=300
)

print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)

if result.returncode == 0:
    print("✅ redeploy_v7.py 执行成功，代码已部署到 SCF")
    print("=" * 60)
    print("部署完成！请检查 SCF 控制台确认 ModTime 已更新")
    sys.exit(0)
else:
    print("⚠️ redeploy_v7.py 失败，尝试方式2（base64 直接上传）...")

# ============================================================================
# Step 3: 回退方案 - base64 方式（仅适用于 < 50MB 的包）
# ============================================================================
print("\n尝试方式2: base64 直接上传...")

with open(zip_path, 'rb') as f:
    zip_b64 = base64.b64encode(f.read()).decode('utf-8')

print(f"Zip base64 length: {len(zip_b64)}")

if len(zip_b64) > 50 * 1024 * 1024:
    print("❌ 部署包太大，无法通过 base64 方式上传（限制 50MB）")
    print("请检查 redeploy_v7.py 为什么失败，或使用更小的部署包")
    sys.exit(1)

# Create SCF client
cred = credential.Credential(SECRET_ID, SECRET_KEY)
hp = HttpProfile()
hp.endpoint = "scf.tencentcloudapi.com"
profile = ClientProfile()
profile.httpProfile = hp
client = scf_client.ScfClient(cred, "ap-shanghai", profile)

# Update function code
req = UpdateFunctionCodeRequest()
req.FunctionName = "etsy-ai-workflow"
req.Namespace = "default"
req.Code = {"ZipFile": zip_b64}

resp = client.UpdateFunctionCode(req)
print("✅ UpdateFunctionCode 成功！")
print(resp.to_json_string(indent=2))
print("\n" + "=" * 60)
print("部署完成！请检查 SCF 控制台确认 ModTime 已更新")
