#!/usr/bin/env python3
"""
直接使用原始 HTTP API 调用 UpdateTriggerStatus
"""
import json
import hmac
import hashlib
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

from tencent_env import get_tencent_secret_pair

SECRET_ID, SECRET_KEY = get_tencent_secret_pair()


def sign(key, msg):
    """TC3 签名"""
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

def call_api(action, params):
    """调用腾讯云 API"""
    timestamp = int(time.time())
    date = datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d')
    
    payload = json.dumps(params)
    
    # TC3 签名
    http_request_method = 'POST'
    canonical_uri = '/'
    canonical_querystring = ''
    canonical_headers = f'content-type:application/json\nhost:scf.tencentcloudapi.com\nx-tc-action:{action.lower()}\n'
    signed_headers = 'content-type;host;x-tc-action'
    hashed_request_payload = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    canonical_request = f'{http_request_method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{hashed_request_payload}'
    
    algorithm = 'TC3-HMAC-SHA256'
    credential_scope = f'{date}/scf/tc3_request'
    hashed_canonical_request = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
    string_to_sign = f'{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}'
    
    secret_date = sign(('TC3' + SECRET_KEY).encode('utf-8'), date)
    secret_service = sign(secret_date, 'scf')
    secret_signing = sign(secret_service, 'tc3_request')
    signature = hmac.new(secret_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    
    authorization = f'{algorithm} Credential={SECRET_ID}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}'
    
    headers = {
        'Authorization': authorization,
        'Content-Type': 'application/json',
        'Host': 'scf.tencentcloudapi.com',
        'X-TC-Action': action,
        'X-TC-Timestamp': str(timestamp),
        'X-TC-Version': '2018-04-16',
        'X-TC-Region': 'ap-shanghai'
    }
    
    url = 'https://scf.tencentcloudapi.com/'
    resp = requests.post(url, headers=headers, data=payload)
    return resp.json()

print("=" * 70)
print("直接调用 UpdateTriggerStatus API (原始 HTTP)")
print("=" * 70)
print()

# 尝试不同的参数组合
test_cases = [
    {
        "name": "标准参数 (Enable=0)",
        "params": {
            "FunctionName": "etsy-ai-workflow",
            "Namespace": "default",
            "TriggerName": "workday-every-10min",
            "Type": "timer",
            "Enable": "0"
        }
    },
    {
        "name": "Enable=1 (禁用)",
        "params": {
            "FunctionName": "etsy-ai-workflow",
            "Namespace": "default",
            "TriggerName": "workday-every-10min",
            "Type": "timer",
            "Enable": "1"
        }
    },
    {
        "name": "不带 Type 参数",
        "params": {
            "FunctionName": "etsy-ai-workflow",
            "Namespace": "default",
            "TriggerName": "workday-every-10min",
            "Enable": "0"
        }
    }
]

for i, test in enumerate(test_cases, 1):
    print(f"[{i}] {test['name']}...")
    result = call_api("UpdateTriggerStatus", test['params'])
    
    if 'Response' in result:
        resp_data = result['Response']
        if 'RequestId' in resp_data:
            print(f"  ✓ 成功! RequestId: {resp_data['RequestId']}")
        else:
            error = resp_data.get('Error', {})
            print(f"  ✗ 失败: {error.get('Code')} - {error.get('Message')}")
    else:
        print(f"  ✗ API 调用失败: {result}")
    print()

# 验证最终状态
print("[验证] 检查触发器最终状态...")
result = call_api("ListTriggers", {
    "FunctionName": "etsy-ai-workflow",
    "Namespace": "default"
})

if 'Response' in result:
    resp_data = result['Response']
    if 'Triggers' in resp_data:
        triggers = resp_data['Triggers']
        for t in triggers:
            if t.get('TriggerName') == 'workday-every-10min':
                enable = t.get('Enable')
                status_str = "✓ 启用 (0)" if enable == "0" else "✗ 禁用 (1)"
                print(f"  触发器状态: {status_str}")
                print(f"  TriggerDesc: {t.get('TriggerDesc')}")
                break

print()
print("=" * 70)
