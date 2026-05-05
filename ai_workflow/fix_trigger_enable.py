#!/usr/bin/env python3
"""
直接调用 UpdateTriggerStatus API 启用触发器
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
REGION = "ap-shanghai"
SERVICE = "scf"
ACTION = "UpdateTriggerStatus"
FUNCTION_NAME = "etsy-ai-workflow"
TRIGGER_NAME = "workday-every-10min"

def sign(key, msg):
    """TC3 签名辅助函数"""
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

def call_tc3_api(action, params):
    """调用腾讯云 API (TC3 签名)"""
    timestamp = int(time.time())
    date = datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d')
    
    # 请求体
    payload = json.dumps(params)
    
    # 1. 拼接规范请求串
    http_request_method = 'POST'
    canonical_uri = '/'
    canonical_querystring = ''
    canonical_headers = f'content-type:application/json\nhost:{SERVICE}.tencentcloudapi.com\nx-tc-action:{action.lower()}\n'
    signed_headers = 'content-type;host;x-tc-action'
    hashed_request_payload = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    canonical_request = f'{http_request_method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{hashed_request_payload}'
    
    # 2. 拼接待签名字符串
    algorithm = 'TC3-HMAC-SHA256'
    credential_scope = f'{date}/{SERVICE}/tc3_request'
    hashed_canonical_request = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
    string_to_sign = f'{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}'
    
    # 3. 计算签名
    secret_date = sign(('TC3' + SECRET_KEY).encode('utf-8'), date)
    secret_service = sign(secret_date, SERVICE)
    secret_signing = sign(secret_service, 'tc3_request')
    signature = hmac.new(secret_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    
    # 4. 拼接 Authorization
    authorization = f'{algorithm} Credential={SECRET_ID}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}'
    
    headers = {
        'Authorization': authorization,
        'Content-Type': 'application/json',
        'Host': f'{SERVICE}.tencentcloudapi.com',
        'X-TC-Action': action,
        'X-TC-Timestamp': str(timestamp),
        'X-TC-Version': '2018-04-16',
        'X-TC-Region': REGION
    }
    
    url = f'https://{SERVICE}.tencentcloudapi.com/'
    resp = requests.post(url, headers=headers, data=payload)
    return resp.json()

print("=" * 70)
print("调用 UpdateTriggerStatus API 启用触发器")
print("=" * 70)
print()

# 调用 UpdateTriggerStatus
params = {
    "FunctionName": FUNCTION_NAME,
    "Namespace": "default",
    "TriggerName": TRIGGER_NAME,
    "Type": "timer",
    "Enable": "0"  # 0=启用, 1=禁用
}

print(f"[调用] UpdateTriggerStatus...")
print(f"  函数: {FUNCTION_NAME}")
print(f"  触发器: {TRIGGER_NAME}")
print(f"  状态: 0 (启用)")
print()

result = call_tc3_api("UpdateTriggerStatus", params)

if 'Response' in result:
    resp_data = result['Response']
    if 'RequestId' in resp_data:
        print(f"✅ API 调用成功!")
        print(f"  RequestId: {resp_data['RequestId']}")
        print()
        
        # 验证触发器状态
        print("[验证] 检查触发器状态...")
        verify_result = call_tc3_api("ListTriggers", {
            "FunctionName": FUNCTION_NAME,
            "Namespace": "default"
        })
        
        if 'Response' in verify_result:
            verify_data = verify_result['Response']
            if 'Triggers' in verify_data:
                triggers = verify_data['Triggers']
                for t in triggers:
                    if t.get('TriggerName') == TRIGGER_NAME:
                        enable = t.get('Enable')
                        status_str = "✓ 启用 (0)" if enable == "0" else "✗ 禁用 (1)"
                        print(f"  触发器状态: {status_str}")
                        break
    else:
        error = resp_data.get('Error', {})
        print(f"✗ API 调用失败!")
        print(f"  错误码: {error.get('Code')}")
        print(f"  错误信息: {error.get('Message')}")
        print(f"  完整响应: {resp_data}")
else:
    print(f"✗ API 调用失败!")
    print(f"  响应: {result}")

print()
print("=" * 70)
