#!/usr/bin/env python3
"""
启用 SCF 定时器触发器 - 修复版
根据之前踩坑经验：
1. Enable 是 int 类型，0=启用，1=禁用
2. Type 参数必须传（'timer'）
3. TriggerDesc 不要传 Timezone 参数
"""

import os
import sys
import json

# 添加当前目录到路径
_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _root)

from tencent_env import get_tencent_secret_pair
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.scf.v20180416 import scf_client, models

# 腾讯云凭证（从 config 目录读取）
CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config')
config_file = os.path.join(CONFIG_DIR, 'tencentcloud.json')

if os.path.exists(config_file):
    with open(config_file, 'r') as f:
        config = json.load(f)
    secret_id = config.get('secret_id')
    secret_key = config.get('secret_key')
else:
    secret_id, secret_key = get_tencent_secret_pair()

# 函数配置
FUNCTION_NAME = 'etsy-ai-workflow'
NAMESPACE = 'default'
TRIGGER_NAME = 'SCF-timer-1777721150'
REGION = 'ap-shanghai'

def enable_trigger():
    try:
        # 创建认证和客户端
        cred = credential.Credential(secret_id, secret_key)
        client = scf_client.ScfClient(cred, REGION)
        
        # 方法1：使用 UpdateTriggerStatus
        print("尝试启用触发器（UpdateTriggerStatus）...")
        req = models.UpdateTriggerStatusRequest()
        req.FunctionName = FUNCTION_NAME
        req.Namespace = NAMESPACE
        req.TriggerName = TRIGGER_NAME
        req.Qualifier = '$LATEST'
        req.Type = 'timer'  # 必须传 Type
        req.Enable = '0'  # '0'=启用，'1'=禁用（string 类型！）
        
        print(f"请求参数: FunctionName={req.FunctionName}, TriggerName={req.TriggerName}, Enable={req.Enable}, Type={req.Type}")
        
        resp = client.UpdateTriggerStatus(req)
        print("✅ 触发器启用成功！")
        print(resp.to_json_string(indent=2))
        return True
        
    except TencentCloudSDKException as err:
        print(f"❌ UpdateTriggerStatus 失败: {err}")
        print(f"错误码: {err.code if hasattr(err, 'code') else 'N/A'}")
        print(f"错误信息: {err.message if hasattr(err, 'message') else str(err)}")
        
        # 如果 UpdateTriggerStatus 不行，尝试 UpdateFunctionConfiguration 或其他方法
        print("\n尝试方法2：使用 UpdateTrigger...")
        try:
            req2 = models.UpdateTriggerRequest()
            req2.FunctionName = FUNCTION_NAME
            req2.Namespace = NAMESPACE
            req2.TriggerName = TRIGGER_NAME
            req2.Qualifier = '$LATEST'
            req2.Type = 'timer'
            req2.Enable = '0'  # string 类型
            
            resp2 = client.UpdateTrigger(req2)
            print("✅ 方法2成功！")
            print(resp2.to_json_string(indent=2))
            return True
        except TencentCloudSDKException as err2:
            print(f"❌ 方法2也失败: {err2}")
            return False

def check_trigger_status():
    """检查触发器当前状态"""
    try:
        cred = credential.Credential(secret_id, secret_key)
        client = scf_client.ScfClient(cred, REGION)
        
        req = models.ListTriggersRequest()
        req.FunctionName = FUNCTION_NAME
        req.Namespace = NAMESPACE
        
        resp = client.ListTriggers(req)
        result = json.loads(resp.to_json_string())
        
        if result.get('TotalCount', 0) > 0:
            trigger = result['Triggers'][0]
            enable_status = trigger.get('Enable')
            print(f"\n当前触发器状态:")
            print(f"  名称: {trigger.get('TriggerName')}")
            print(f"  Enable 值: {enable_status} ({'禁用' if enable_status == 1 else '启用'})")
            print(f"  类型: {trigger.get('Type')}")
            print(f"  Cron: {trigger.get('TriggerDesc')}")
            return enable_status
        else:
            print("未找到触发器")
            return None
            
    except TencentCloudSDKException as err:
        print(f"检查状态失败: {err}")
        return None

if __name__ == '__main__':
    print("=" * 60)
    print("SCF 触发器启用工具（修复版）")
    print("=" * 60)
    
    # 先检查当前状态
    print("\n1. 检查当前触发器状态...")
    current_status = check_trigger_status()
    
    if current_status == 0:
        print("\n✅ 触发器已经是启用状态，无需操作")
        sys.exit(0)
    
    print("\n2. 尝试启用触发器...")
    success = enable_trigger()
    
    if success:
        print("\n3. 验证最终结果...")
        check_trigger_status()
    else:
        print("\n❌ 所有方法都失败了，请检查 API 权限或参数")
        sys.exit(1)
