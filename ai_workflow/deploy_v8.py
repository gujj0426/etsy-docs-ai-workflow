#!/usr/bin/env python3
"""
部署 v8 到 SCF（通过 COS 中转）
v8 = v7 去掉 scf_build/ 目录（根除旧版 volcengine SDK 代码）
"""
import sys, os, json, time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

from tencent_env import get_tencent_secret_pair

import urllib.request, urllib.error
import hashlib, hmac, base64
from tencentcloud.scf.v20180416 import scf_client, models
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile

# ====== 凭证 ======
SECRET_ID, SECRET_KEY = get_tencent_secret_pair()
REGION     = 'ap-shanghai'
FUNCTION   = 'etsy-ai-workflow'

# ====== COS 配置 ======
COS_BUCKET  = 'etsy-ai-images-1405462135'
COS_KEY     = 'scf/scf_deploy_v8.zip'
COS_DOMAIN  = f'https://etsy-ai-images-1405462135.cos.ap-shanghai.myqcloud.com'

# ====== HMAC-SHA1 签名（上传 COS）======
def cos_sign(method, path, secret_id, secret_key, exp=3600):
    now = int(time.time())
    exp_str = f"{now};{now + exp}"
    sign_str = f"a={secret_id}&k={secret_id}&e={exp_str}&t={now}&r={sign_str}"
    h = hmac.new(secret_key.encode(), sign_str.encode(), hashlib.sha1)
    signature = base64.b64encode(h.digest()).decode()
    return signature

def upload_to_cos(zip_path):
    """上传 ZIP 到 COS，返回 CDN URL"""
    with open(zip_path, 'rb') as f:
        zip_data = f.read()
    content_len = len(zip_data)
    content_sha1 = hashlib.sha1(zip_data).hexdigest()

    sign = cos_sign('PUT', f'/{COS_KEY}', SECRET_ID, SECRET_KEY)
    headers = {
        'Authorization': f'q-sign-algorithm=sha1',
        'x-cos-signature': sign,
        'Content-Type': 'application/zip',
        'Content-Length': str(content_len),
        'x-cos-content-sha1': content_sha1,
    }

    url = f'{COS_DOMAIN}/{COS_KEY}'
    req = urllib.request.Request(url, data=zip_data, headers=headers, method='PUT')
    with urllib.request.urlopen(req, timeout=300) as resp:
        print(f'  ✅ 上传成功: {url}')
        return url

def update_scf_via_cos(cos_url):
    """通过 COS URL 更新 SCF 函数代码"""
    cred = credential.Credential(SECRET_ID, SECRET_KEY)
    hp = HttpProfile()
    hp.endpoint = 'scf.tencentcloudapi.com'
    profile = ClientProfile()
    profile.httpProfile = hp
    client = scf_client.ScfClient(cred, REGION, profile)

    req = models.UpdateFunctionCodeRequest()
    req.FunctionName = FUNCTION
    req.Namespace = 'default'
    req.Code = {'CosBucketObject': cos_url.replace(COS_DOMAIN + '/', '')}
    req.Handler = 'index.scf_handler'

    resp = client.UpdateFunctionCode(req)
    print(f'  ✅ SCF 代码更新成功!')
    print(f'     RequestId: {resp.RequestId}')
    return resp

def verify():
    """验证函数状态"""
    cred = credential.Credential(SECRET_ID, SECRET_KEY)
    hp = HttpProfile()
    hp.endpoint = 'scf.tencentcloudapi.com'
    profile = ClientProfile()
    profile.httpProfile = hp
    client = scf_client.ScfClient(cred, REGION, profile)

    req = models.GetFunctionRequest()
    req.FunctionName = FUNCTION
    req.Namespace = 'default'
    resp = client.GetFunction(req)
    print(f'  函数名:  {resp.FunctionName}')
    print(f'  状态:    {resp.Status}')
    print(f'  Handler: {resp.Handler}')
    print(f'  更新:    {resp.ModTime}')
    print(f'  代码:    {resp.CodeSize} bytes')

if __name__ == '__main__':
    ZIP = '/Users/mac/Desktop/etsy/运营文档/scf_deploy_v8.zip'
    if not os.path.exists(ZIP):
        print(f'❌ 文件不存在: {ZIP}')
        sys.exit(1)

    size_mb = os.path.getsize(ZIP) / 1024 / 1024
    print(f'=' * 60)
    print(f'  🚀 部署 v8 到 SCF（删除 scf_build/，根除旧版 SDK）')
    print(f'  文件: {ZIP} ({size_mb:.1f} MB)')
    print(f'=' * 60)

    cos_url = upload_to_cos(ZIP)
    update_scf_via_cos(cos_url)
    verify()

    print()
    print('=' * 60)
    print('  ✅ v8 部署完成！')
    print('  SCF 将执行根目录 index.py → scf_pipeline.py（纯 HTTP）')
    print('=' * 60)
