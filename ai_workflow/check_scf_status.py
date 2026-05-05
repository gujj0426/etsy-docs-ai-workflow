#!/usr/bin/env python3
"""
检查 SCF 函数和触发器状态
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
FUNCTION_NAME = "etsy-ai-workflow"

def sign(key, msg):
    """TC3 签名辅助函数"""
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

def get_tc3_headers(service, action, payload):
    """生成 TC3 签名 headers"""
    timestamp = int(time.time())
    date = datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d')
    
    # 1. 拼接规范请求串
    http_request_method = 'POST'
    canonical_uri = '/'
    canonical_querystring = ''
    canonical_headers = f'content-type:application/json\nhost:{service}.tencentcloudapi.com\nx-tc-action:{action.lower()}\n'
    signed_headers = 'content-type;host;x-tc-action'
    hashed_request_payload = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    canonical_request = f'{http_request_method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{hashed_request_payload}'
    
    # 2. 拼接待签名字符串
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
        'X-TC-Version': '2022-01-01',
        'X-TC-Region': REGION
    }
    
    return headers

def call_api(service, action, params):
    """调用腾讯云 API"""
    payload = json.dumps(params)
    headers = get_tc3_headers(service, action, payload)
    
    url = f'https://{service}.tencentcloudapi.com/'
    resp = requests.post(url, headers=headers, data=payload)
    return resp.json()

print("=" * 60)
print("SCF 函数和触发器状态检查")
print("=" * 60)

# 1. 检查函数状态
print("\n[1] 检查函数状态...")
result = call_api('scf', 'GetFunction', {'FunctionName': FUNCTION_NAME})

if 'Response' in result:
    resp_data = result['Response']
    if 'FunctionInfo' in resp_data:
        info = resp_data['FunctionInfo']
        print(f"  ✓ 函数名称: {info.get('FunctionName')}")
        print(f"  ✓ 状态: {info.get('Status')}")
        print(f"  ✓ Handler: {info.get('Handler')}")
        print(f"  ✓ 运行时: {info.get('Runtime')}")
        print(f"  ✓ 内存: {info.get('MemorySize')}MB")
    else:
        error = resp_data.get('Error', {})
        print(f"  ✗ 错误: {error.get('Code')} - {error.get('Message')}")

# 2. 列出触发器
print("\n[2] 列出触发器...")
result = call_api('scf', 'ListTriggers', {
    'FunctionName': FUNCTION_NAME,
    'Namespace': 'default'
})

if 'Response' in result:
    resp_data = result['Response']
    if 'Triggers' in resp_data:
        triggers = resp_data['Triggers']
        total = resp_data.get('TotalCount', 0)
        print(f"  ✓ 找到 {total} 个触发器:")
        print()
        
        for i, t in enumerate(triggers, 1):
            print(f"  [{i}] 名称: {t.get('TriggerName')}")
            print(f"      类型: {t.get('Type')}")
            enable = t.get('Enable')
            status_str = "启用 (0)" if enable == "0" else "禁用 (1)"
            print(f"      状态: {status_str}")
            
            # 解析 TriggerDesc
            trigger_desc = t.get('TriggerDesc', '')
            print(f"      TriggerDesc: {trigger_desc[:100]}...")
            
            # 如果是定时触发器，解析 Cron 表达式
            if t.get('Type') == 'timer':
                try:
                    desc_obj = json.loads(trigger_desc)
                    cron = desc_obj.get('cron', '')
                    print(f"      Cron: {cron}")
                except:
                    pass
            print()
    else:
        error = resp_data.get('Error', {})
        print(f"  ✗ 错误: {error.get('Code')} - {error.get('Message')}")
        print(f"  完整响应: {resp_data}")

print("=" * 60)
print("检查完成")
print("=" * 60)
