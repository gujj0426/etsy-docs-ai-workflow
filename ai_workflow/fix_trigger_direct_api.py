#!/usr/bin/env python3
"""
直接调用腾讯云 API，绕过 SDK 的双重编码问题
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

def sign(key, msg):
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

def tc3_sign(secret_id, secret_key, service, action, region, payload):
    """TC3 签名"""
    timestamp = int(time.time())
    date = datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d')
    
    http_method = 'POST'
    canonical_uri = '/'
    canonical_querystring = ''
    canonical_headers = f'content-type:application/json\nhost:{service}.tencentcloudapi.com\nx-tc-action:{action.lower()}\n'
    signed_headers = 'content-type;host;x-tc-action'
    hashed_payload = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    canonical_request = f'{http_method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{hashed_payload}'
    
    algorithm = 'TC3-HMAC-SHA256'
    credential_scope = f'{date}/{service}/tc3_request'
    hashed_canonical_request = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
    string_to_sign = f'{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}'
    
    secret_date = sign(('TC3' + secret_key).encode('utf-8'), date)
    secret_service = sign(secret_date, service)
    secret_signing = sign(secret_service, 'tc3_request')
    signature = hmac.new(secret_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    
    authorization = f'{algorithm} Credential={secret_id}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}'
    
    headers = {
        'Authorization': authorization,
        'Content-Type': 'application/json',
        'Host': f'{service}.tencentcloudapi.com',
        'X-TC-Action': action,
        'X-TC-Timestamp': str(timestamp),
        'X-TC-Version': '2018-04-16',
        'X-TC-Region': region
    }
    
    return headers

def call_api(service, action, region, params):
    """调用腾讯云 API"""
    payload = json.dumps(params)
    headers = tc3_sign(SECRET_ID, SECRET_KEY, service, action, region, payload)
    
    url = f'https://{service}.tencentcloudapi.com/'
    resp = requests.post(url, headers=headers, data=payload)
    return resp.json()

FUNCTION_NAME = "etsy-ai-workflow"
TRIGGER_NAME = "workday-every-10min"
CORRECT_CRON = "0 0/10 10-17 * * * *"

print("=" * 70)
print("直接 API 调用：修复 TriggerDesc + 启用触发器")
print("=" * 70)
print()

# 1. 使用原始 API 更新触发器配置
# 关键：TriggerDesc 作为 JSON 对象的字符串形式
print("[1] 使用 UpdateTrigger 更新触发器配置...")
print("    传入的 TriggerDesc: 原始 JSON 对象 (不是双重编码)")

# 直接用 JSON 对象，SDK 会怎么处理？
# 实际上 API 只接受字符串。但如果我们用 HTTP 直接发，
# TriggerDesc 会被当作普通字符串...

# 正确做法：TriggerDesc 本身应该是 JSON 字符串
# API 文档说 TriggerDesc 格式为 {"cron": "..."}
# 所以我们传 {"cron": "0 0/10 10-17 * * * *"} 作为 TriggerDesc 的值

params = {
    "FunctionName": FUNCTION_NAME,
    "Namespace": "default",
    "TriggerName": TRIGGER_NAME,
    "Type": "timer",
    "TriggerDesc": json.dumps({"cron": CORRECT_CRON}),  # 正确
    "Enable": "0"
}

print(f"    TriggerDesc 原始值: {params['TriggerDesc']}")

result = call_api('scf', 'UpdateTrigger', REGION, params)

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

# 2. 使用原始 API 启用触发器
print("[2] 使用 UpdateTriggerStatus 启用触发器...")

params = {
    "FunctionName": FUNCTION_NAME,
    "Namespace": "default",
    "TriggerName": TRIGGER_NAME,
    "Type": "timer",
    "Enable": "0"
}

result = call_api('scf', 'UpdateTriggerStatus', REGION, params)

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
time.sleep(3)

# 3. 最终验证
print("[3] 最终验证...")
result = call_api('scf', 'ListTriggers', REGION, {
    "FunctionName": FUNCTION_NAME,
    "Namespace": "default"
})

if 'Response' in result:
    resp_data = result['Response']
    if 'Triggers' in resp_data:
        for t in resp_data['Triggers']:
            if t.get('TriggerName') == TRIGGER_NAME:
                enable = t.get('Enable')
                trigger_desc = t.get('TriggerDesc', '')
                status = "✓ 启用 (0)" if enable == "0" else "✗ 禁用 (1)"
                print(f"  触发器状态: {status}")
                print(f"  TriggerDesc: {trigger_desc}")
                
                # 解析 Cron
                try:
                    desc = json.loads(trigger_desc)
                    cron = desc.get('cron', '')
                    print(f"  Cron 表达式: {cron}")
                    
                    # 检查双重编码
                    if '\\n' in cron or '{\"cron\"' in cron:
                        print(f"  ⚠️  双重编码!")
                    else:
                        print(f"  ✓ 格式正确")
                except:
                    pass
                break

print()
print("=" * 70)
