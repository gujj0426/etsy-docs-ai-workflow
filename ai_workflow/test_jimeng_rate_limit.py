#!/usr/bin/env python3
"""
测试即梦API是否能够正常访问（检查429限流是否重置）
"""
import json
import os
import time
import hashlib
import hmac
import requests
from datetime import datetime


def _jimeng_ak_sk():
    ak = os.environ.get("JIMENG_AK", "").strip()
    sk = os.environ.get("JIMENG_SK", "").strip()
    if not ak or not sk:
        raise RuntimeError("请设置环境变量 JIMENG_AK、JIMENG_SK")
    return ak, sk


def generate_jimeng_signature(body_str: str) -> dict:
    """生成即梦API签名"""
    access_key_id, secret_key = _jimeng_ak_sk()
    
    # 构造Canonical Request
    method = 'POST'
    path = '/'
    query_string = 'Action=CVSync2AsyncSubmitTask&Version=2022-08-31'
    content_type = 'application/json'
    host = 'visual.volcengineapi.com'
    
    # 时间戳
    x_date = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    date_str = x_date[:8]
    
    # 计算body的SHA256
    body_sha256 = hashlib.sha256(body_str.encode('utf-8')).hexdigest()
    
    # Canonical Request
    canonical_request = '\n'.join([
        method,
        path,
        query_string,
        f'content-type:{content_type}',
        f'host:{host}',
        f'x-content-sha256:{body_sha256}',
        f'x-date:{x_date}',
        '',
        'content-type;host;x-content-sha256;x-date',
        body_sha256
    ])
    
    # 计算Canonical Request的SHA256
    canonical_sha256 = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
    
    # Credential Scope
    credential_scope = f'{date_str}/cn-north-1/cv/request'
    
    # String to Sign
    string_to_sign = '\n'.join([
        'HMAC-SHA256',
        x_date,
        credential_scope,
        canonical_sha256
    ])
    
    # 计算Signing Key（直接用原始SK字符串计算HMAC）
    k_date = hmac.new(secret_key.encode('utf-8'), date_str.encode('utf-8'), hashlib.sha256).digest()
    k_region = hmac.new(k_date, 'cn-north-1'.encode('utf-8'), hashlib.sha256).digest()
    k_service = hmac.new(k_region, 'cv'.encode('utf-8'), hashlib.sha256).digest()
    k_signing = hmac.new(k_service, 'request'.encode('utf-8'), hashlib.sha256).digest()
    
    # 计算Signature
    signature = hmac.new(k_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    
    # Authorization Header
    authorization = f'HMAC-SHA256 Credential={access_key_id}/{credential_scope}, SignedHeaders=content-type;host;x-content-sha256;x-date, Signature={signature}'
    
    headers = {
        'Content-Type': content_type,
        'Host': host,
        'X-Content-Sha256': body_sha256,
        'X-Date': x_date,
        'Authorization': authorization
    }
    
    return headers

def test_jimeng_api():
    """测试即梦API"""
    print("=== 测试即梦API（检查429限流）===\n")
    
    # 构造一个简单的测试请求体
    body = {
        "req_key": "jimeng_t2i_v40",
        "prompt": "测试提示词",
        "seed": 12345,
        "return_url": True
    }
    body_str = json.dumps(body)
    
    # 生成签名
    headers = generate_jimeng_signature(body_str)
    
    # 发送请求
    url = 'https://visual.volcengineapi.com/?Action=CVSync2AsyncSubmitTask&Version=2022-08-31'
    
    print(f"请求URL: {url}")
    print(f"请求头:")
    for key, value in headers.items():
        if key == 'Authorization':
            print(f"  {key}: {value[:50]}...")
        else:
            print(f"  {key}: {value}")
    print()
    
    try:
        resp = requests.post(url, headers=headers, data=body_str, timeout=10)
        
        print(f"HTTP状态码: {resp.status_code}")
        print(f"响应头:")
        for key, value in resp.headers.items():
            print(f"  {key}: {value}")
        print()
        print(f"响应体:")
        
        try:
            resp_json = resp.json()
            print(json.dumps(resp_json, indent=2, ensure_ascii=False))
            
            # 检查是否有429错误
            if resp.status_code == 429:
                print("\n❌ 仍然被限流（HTTP 429）")
                print("需要继续等待...")
                return False
            elif resp.status_code == 200:
                if 'ResponseMetadata' in resp_json:
                    error = resp_json['ResponseMetadata'].get('Error')
                    if error:
                        print(f"\n❌ API返回错误:")
                        print(f"  错误码: {error.get('Code')}")
                        print(f"  错误消息: {error.get('Message')}")
                        return False
                    else:
                        print("\n✅ API调用成功！")
                        return True
            else:
                print(f"\n⚠️ 意外的HTTP状态码: {resp.status_code}")
                return False
                
        except json.JSONDecodeError:
            print(resp.text[:500])
            return False
            
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_jimeng_api()
    
    if success:
        print("\n" + "="*60)
        print("✅ 即梦API可以正常访问，429限流已重置")
        print("SCF函数现在应该能正常工作了")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("❌ 即梦API仍有问题")
        print("需要等待更长时间或进一步排查")
        print("="*60)
