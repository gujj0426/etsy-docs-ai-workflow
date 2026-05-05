#!/usr/bin/env python3
"""
使用 requests 直接发送 HTTP 请求，绕过 SDK
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

def call_api(action, params):
    """TC3 签名 + 发送请求"""
    timestamp = int(time.time())
    date = datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d')
    service = 'scf'
    
    payload = json.dumps(params)
    
    # 1. 规范请求串
    http_method = 'POST'
    canonical_uri = '/'
    canonical_querystring = ''
    canonical_headers = f'content-type:application/json\nhost:{service}.tencentcloudapi.com\nx-tc-action:{action.lower()}\n'
    signed_headers = 'content-type;host;x-tc-action'
    hashed_payload = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    canonical_request = f'{http_method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{hashed_payload}'
    
    # 2. 待签名字符串
    algorithm = 'TC3-HMAC-SHA256'
    credential_scope = f'{date}/{service}/tc3_request'
    hashed_canonical_request = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
    string_to_sign = f'{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}'
    
    # 3. 计算签名
    secret_date = sign(('TC3' + SECRET_KEY).encode('utf-8'), date)
    secret_service = sign(secret_date, service)
    secret_signing = sign(secret_service, 'tc3_request')
    signature = hmac.new(secret_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    
    # 4. 拼接 Authorization
    authorization = f'{algorithm} Credential={SECRET_ID}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}'
    
    headers = {
        'Authorization': authorization,
        'Content-Type': 'application/json',
        'Host': f'{service}.tencentcloudapi.com',
        'X-TC-Action': action,
        'X-TC-Timestamp': str(timestamp),
        'X-TC-Version': '2018-04-16',
        'X-TC-Region': REGION
    }
    
    url = f'https://{service}.tencentcloudapi.com/'
    resp = requests.post(url, headers=headers, data=payload, timeout=30)
    
    result = resp.json()
    
    # 打印请求和响应
    print(f"  [请求] {action}")
    print(f"  [请求体] {payload}")
    print(f"  [状态码] {resp.status_code}")
    
    return result

FUNCTION_NAME = "etsy-ai-workflow"
TRIGGER_NAME = "workday-every-10min"

print("=" * 70)
print("全面诊断 SCF 触发器问题")
print("=" * 70)
print()

# 1. 获取当前触发器详细信息
print("[1] 获取触发器详细信息...")
result = call_api('ListTriggers', {
    "FunctionName": FUNCTION_NAME,
    "Namespace": "default"
})

if 'Response' in result:
    resp_data = result['Response']
    triggers = resp_data.get('Triggers', [])
    for t in triggers:
        if t.get('TriggerName') == TRIGGER_NAME:
            print(f"\n  触发器详情:")
            for k, v in t.items():
                print(f"    {k}: {v}")
            
            # 特别关注 Enable 字段
            enable = t.get('Enable')
            print(f"\n  Enable 字段值: '{enable}' (类型: {type(enable).__name__})")
            print(f"  Enable == '0': {enable == '0'}")
            print(f"  Enable == '1': {enable == '1'}")
            break

print()

# 2. 使用 UpdateTriggerStatus 直接设置 Enable=0
print("[2] 直接设置 Enable=0 (UpdateTriggerStatus)...")
result = call_api('UpdateTriggerStatus', {
    "FunctionName": FUNCTION_NAME,
    "Namespace": "default",
    "TriggerName": TRIGGER_NAME,
    "Type": "timer",
    "Enable": "0"
})

if 'Response' in result:
    resp_data = result['Response']
    if 'RequestId' in resp_data:
        print(f"\n  ✓ API 调用成功!")
        print(f"  RequestId: {resp_data['RequestId']}")
    else:
        error = resp_data.get('Error', {})
        print(f"\n  ✗ API 调用失败!")
        print(f"  错误码: {error.get('Code')}")
        print(f"  错误信息: {error.get('Message')}")

print()
time.sleep(2)

# 3. 再次检查触发器状态
print("[3] 再次检查触发器状态...")
result = call_api('ListTriggers', {
    "FunctionName": FUNCTION_NAME,
    "Namespace": "default"
})

if 'Response' in result:
    resp_data = result['Response']
    triggers = resp_data.get('Triggers', [])
    for t in triggers:
        if t.get('TriggerName') == TRIGGER_NAME:
            enable = t.get('Enable')
            status = "启用" if enable == '0' else "禁用"
            print(f"  触发器 Enable: '{enable}' -> {status}")
            
            # 检查 Cron
            trigger_desc = t.get('TriggerDesc', '')
            try:
                desc = json.loads(trigger_desc)
                cron = desc.get('cron', '')
                print(f"  Cron: {cron}")
                
                # 验证 Cron 格式
                if '\\n' in cron or '{\"cron\"' in cron:
                    print(f"  ⚠️  Cron 被双重编码!")
            except:
                print(f"  TriggerDesc 无法解析: {trigger_desc}")
            break

print()
print("=" * 70)
print("诊断完成")
print("=" * 70)
