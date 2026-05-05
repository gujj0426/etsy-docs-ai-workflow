#!/usr/bin/env python3
"""
修复 SCF 触发器的双重编码问题，并正确检查状态
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
    
    secret_date = sign(('TC3' + SECRET_KEY).encode('utf-8'), date)
    secret_service = sign(secret_date, service)
    secret_signing = sign(secret_service, 'tc3_request')
    signature = hmac.new(secret_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    
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
    return resp.json()

FUNCTION_NAME = "etsy-ai-workflow"
TRIGGER_NAME = "workday-every-10min"

# 正确的 Cron 表达式（7位格式）
CORRECT_CRON = "0 0/10 10-17 * * * *"

print("=" * 70)
print("修复 SCF 触发器双重编码 + 确认启用状态")
print("=" * 70)
print()

# 1. 先确认当前真实状态
print("[1] 确认当前状态...")
result = call_api('ListTriggers', {
    "FunctionName": FUNCTION_NAME,
    "Namespace": "default"
})

if 'Response' in result:
    resp_data = result['Response']
    for t in resp_data.get('Triggers', []):
        if t.get('TriggerName') == TRIGGER_NAME:
            enable = t.get('Enable')
            
            # Enable 是 int 类型: 0=启用, 1=禁用
            if enable == 0:
                status_str = "✓ 已启用 (Enable=0)"
            elif enable == 1:
                status_str = "✗ 已禁用 (Enable=1)"
            else:
                status_str = f"⚠️  未知状态 (Enable={enable}, type={type(enable).__name__})"
            
            print(f"  {status_str}")
            print(f"  TriggerDesc: {t.get('TriggerDesc')}")
            
            # 检查双重编码
            trigger_desc = t.get('TriggerDesc', '')
            try:
                desc = json.loads(trigger_desc)
                cron = desc.get('cron', '')
                
                if '\\n' in cron or '\\"' in cron or '{\"cron\"' in cron:
                    needs_fix = True
                    print(f"  ⚠️  Cron 双重编码，需要修复")
                else:
                    needs_fix = False
                    print(f"  ✓ Cron 格式正确: {cron}")
            except:
                needs_fix = True
                print(f"  ⚠️  TriggerDesc 无法解析")
            
            break

print()

# 2. 修复双重编码的 Cron
if needs_fix:
    print("[2] 修复双重编码的 Cron...")
    
    # 关键：直接发送正确的 TriggerDesc JSON 字符串
    # 不要使用 SDK 的 json.dumps，因为 SDK 会自动序列化字符串字段
    # 直接发送 {"cron": "0 0/10 10-17 * * * *"} 作为触发器描述的原始 JSON
    
    # 构造正确的请求体
    params = {
        "FunctionName": FUNCTION_NAME,
        "Namespace": "default",
        "TriggerName": TRIGGER_NAME,
        "Type": "timer",
        # TriggerDesc 应该是 {"cron": "0 0/10 10-17 * * * *"}
        # 注意：API 不需要 JSON 序列化 TriggerDesc，直接传 JSON 对象即可
        # 腾讯云 API 会将其序列化为字符串
        "TriggerDesc": {"cron": CORRECT_CRON}
    }
    
    print(f"  发送 UpdateTrigger...")
    print(f"  TriggerDesc: {json.dumps(params['TriggerDesc'])}")
    
    result = call_api('UpdateTrigger', params)
    
    if 'Response' in result:
        resp_data = result['Response']
        if 'RequestId' in resp_data:
            print(f"  ✓ UpdateTrigger 成功! RequestId: {resp_data['RequestId']}")
        else:
            error = resp_data.get('Error', {})
            print(f"  ✗ UpdateTrigger 失败: {error.get('Code')} - {error.get('Message')}")
    else:
        print(f"  ✗ API 调用失败: {result}")
else:
    print("[2] ✓ Cron 格式正确，无需修复")

print()
time.sleep(3)

# 3. 最终确认
print("[3] 最终确认触发器状态...")
result = call_api('ListTriggers', {
    "FunctionName": FUNCTION_NAME,
    "Namespace": "default"
})

if 'Response' in result:
    resp_data = result['Response']
    for t in resp_data.get('Triggers', []):
        if t.get('TriggerName') == TRIGGER_NAME:
            enable = t.get('Enable')
            trigger_desc = t.get('TriggerDesc', '')
            
            if enable == 0:
                status_str = "✓ 已启用 (Enable=0)"
            elif enable == 1:
                status_str = "✗ 已禁用 (Enable=1)"
            else:
                status_str = f"⚠️  未知状态 (Enable={enable})"
            
            print(f"  触发器状态: {status_str}")
            print(f"  TriggerDesc: {trigger_desc}")
            
            # 解析 Cron
            try:
                desc = json.loads(trigger_desc)
                cron = desc.get('cron', '')
                print(f"  Cron: {cron}")
                
                if '\\n' in cron or '\\"' in cron or '{\"cron\"' in cron:
                    print(f"  ⚠️  仍存在双重编码")
                else:
                    print(f"  ✓ Cron 格式正确")
                    print()
                    print("=" * 70)
                    print("✅ 所有问题已修复!")
                    print("=" * 70)
            except:
                print(f"  (TriggerDesc 无法解析)")
            break

print()
print("=" * 70)
print("完成")
print("=" * 70)