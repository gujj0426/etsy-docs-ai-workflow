#!/usr/bin/env python3
"""
修复 SCF 触发器：修复 TriggerDesc 双重编码 + 正确启用触发器
使用腾讯云 SDK 直接操作
"""
import json
import sys
import time
_SCRIPT_DIR = __import__("pathlib").Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

from tencent_env import get_tencent_secret_pair
from tencentcloud.scf.v20180416 import scf_client
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile

SECRET_ID, SECRET_KEY = get_tencent_secret_pair()

# 创建客户端
cred = credential.Credential(SECRET_ID, SECRET_KEY)
hp = HttpProfile()
hp.endpoint = "scf.tencentcloudapi.com"
profile = ClientProfile()
profile.httpProfile = hp
client = scf_client.ScfClient(cred, "ap-shanghai", profile)

FUNCTION_NAME = "etsy-ai-workflow"
TRIGGER_NAME = "workday-every-10min"

# 正确的 Cron 表达式 (7位: 秒 分 时 日 月 周 年)
CORRECT_CRON_STR = "0 0/10 10-17 * * * *"

print("=" * 70)
print("修复触发器配置")
print("=" * 70)
print()

# 1. 诊断当前状态
print("[1] 诊断当前触发器状态...")
try:
    from tencentcloud.scf.v20180416.models import ListTriggersRequest
    
    req = ListTriggersRequest()
    req.FunctionName = FUNCTION_NAME
    req.Namespace = "default"
    resp = client.ListTriggers(req)
    result = json.loads(resp.to_json_string())
    
    triggers = result.get('Triggers', [])
    for t in triggers:
        if t.get('TriggerName') == TRIGGER_NAME:
            enable = t.get('Enable')
            trigger_desc = t.get('TriggerDesc', '')
            print(f"  当前状态: {'禁用 (1)' if enable == '1' else '启用 (0)'}")
            print(f"  当前 TriggerDesc: {trigger_desc}")
            
            # 解析 TriggerDesc
            try:
                desc_obj = json.loads(trigger_desc)
                cron = desc_obj.get('cron', '')
                print(f"  解析后的 Cron: {cron}")
                
                # 检查是否双重编码
                if '\\n' in cron or '{\"cron\"' in cron:
                    print(f"  ⚠️  TriggerDesc 双重编码! 需要修复")
                else:
                    print(f"  ✓ TriggerDesc 格式正确")
            except:
                print(f"  ⚠️  TriggerDesc 无法解析")
            break
except Exception as e:
    print(f"  ✗ 诊断失败: {e}")
    sys.exit(1)

print()

# 2. 修复 TriggerDesc (不使用 json.dumps，直接传字符串)
print("[2] 修复 TriggerDesc (传入原始 JSON 字符串)...")
try:
    from tencentcloud.scf.v20180416.models import UpdateTriggerRequest
    
    req = UpdateTriggerRequest()
    req.FunctionName = FUNCTION_NAME
    req.Namespace = "default"
    req.TriggerName = TRIGGER_NAME
    req.Type = "timer"
    
    # 关键：直接传入字符串，不使用 json.dumps
    # SDK 会将其作为 TriggerDesc 字段的值（已经是 JSON 字符串）
    req.TriggerDesc = '{"cron":"' + CORRECT_CRON_STR + '"}'
    req.Enable = "0"
    
    print(f"  传入的 TriggerDesc: {req.TriggerDesc}")
    
    resp = client.UpdateTrigger(req)
    print(f"  ✓ UpdateTrigger 成功!")
    print(f"  RequestId: {resp.RequestId}")
except Exception as e:
    print(f"  ✗ UpdateTrigger 失败: {e}")

print()
time.sleep(3)

# 3. 使用 UpdateTriggerStatus 启用触发器
print("[3] 使用 UpdateTriggerStatus 启用触发器...")
try:
    from tencentcloud.scf.v20180416.models import UpdateTriggerStatusRequest
    
    req = UpdateTriggerStatusRequest()
    req.FunctionName = FUNCTION_NAME
    req.Namespace = "default"
    req.TriggerName = TRIGGER_NAME
    req.Type = "timer"
    req.Enable = "0"
    
    resp = client.UpdateTriggerStatus(req)
    print(f"  ✓ UpdateTriggerStatus 成功!")
    print(f"  RequestId: {resp.RequestId}")
except Exception as e:
    print(f"  ✗ UpdateTriggerStatus 失败: {e}")

print()
time.sleep(3)

# 4. 最终验证
print("[4] 最终验证触发器状态...")
try:
    req = ListTriggersRequest()
    req.FunctionName = FUNCTION_NAME
    req.Namespace = "default"
    resp = client.ListTriggers(req)
    result = json.loads(resp.to_json_string())
    
    triggers = result.get('Triggers', [])
    for t in triggers:
        if t.get('TriggerName') == TRIGGER_NAME:
            enable = t.get('Enable')
            trigger_desc = t.get('TriggerDesc', '')
            status_str = "✓ 启用 (0)" if enable == "0" else "✗ 禁用 (1)"
            
            # 解析 Cron
            try:
                desc_obj = json.loads(trigger_desc)
                cron = desc_obj.get('cron', '')
                print(f"  触发器状态: {status_str}")
                print(f"  TriggerDesc: {trigger_desc}")
                print(f"  Cron: {cron}")
            except:
                print(f"  触发器状态: {status_str}")
                print(f"  TriggerDesc: {trigger_desc}")
            break
except Exception as e:
    print(f"  ✗ 验证失败: {e}")

print()
print("=" * 70)
