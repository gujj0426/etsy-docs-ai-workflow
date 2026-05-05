#!/usr/bin/env python3
"""
使用腾讯云 SDK 调用 UpdateTriggerStatus API
"""
import json
import re
import sys
sys.path.insert(0, '/Users/mac/Desktop/etsy/运营文档/ai_workflow')

from tencentcloud.scf.v20180416 import scf_client
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile

# 读取凭证
with open('/Users/mac/Desktop/etsy/运营文档/ai_workflow/deploy_scf.py') as f:
    content = f.read()
SECRET_ID = re.search(r'SECRET_ID\s*=\s*"([^"]+)"', content).group(1)
SECRET_KEY = re.search(r'SECRET_KEY\s*=\s*"([^"]+)"', content).group(1)

# 创建客户端
cred = credential.Credential(SECRET_ID, SECRET_KEY)
hp = HttpProfile()
hp.endpoint = "scf.tencentcloudapi.com"
profile = ClientProfile()
profile.httpProfile = hp
client = scf_client.ScfClient(cred, "ap-shanghai", profile)

FUNCTION_NAME = "etsy-ai-workflow"
TRIGGER_NAME = "workday-every-10min"

print("=" * 70)
print("调用 UpdateTriggerStatus API")
print("=" * 70)
print()

# 方法1: 使用 UpdateTrigger (更新触发器配置)
print("[方法1] 使用 UpdateTrigger 更新触发器 (包括 Enable 字段)...")
try:
    from tencentcloud.scf.v20180416.models import UpdateTriggerRequest
    
    req = UpdateTriggerRequest()
    req.FunctionName = FUNCTION_NAME
    req.Namespace = "default"
    req.TriggerName = TRIGGER_NAME
    req.Type = "timer"
    req.TriggerDesc = json.dumps({
        "cron": "0 0/10 10-17 * * * *"  # 7位 Cron (秒 分 时 日 月 周 年)
    })
    req.Enable = "0"  # 0=启用, 1=禁用
    
    resp = client.UpdateTrigger(req)
    print(f"  ✓ UpdateTrigger 成功!")
    print(f"  RequestId: {resp.RequestId}")
except Exception as e:
    print(f"  ✗ UpdateTrigger 失败: {e}")

print()

# 方法2: 尝试使用 UpdateTriggerStatus (仅更新状态)
print("[方法2] 检查 SDK 是否有 UpdateTriggerStatus API...")
try:
    # 动态导入 UpdateTriggerStatusRequest
    from tencentcloud.scf.v20180416.models import UpdateTriggerStatusRequest
    
    print("  ✓ SDK 支持 UpdateTriggerStatus API")
    print("  调用 UpdateTriggerStatus...")
    
    req = UpdateTriggerStatusRequest()
    req.FunctionName = FUNCTION_NAME
    req.Namespace = "default"
    req.TriggerName = TRIGGER_NAME
    req.Type = "timer"
    req.Enable = "0"  # 0=启用, 1=禁用
    
    resp = client.UpdateTriggerStatus(req)
    print(f"  ✓ UpdateTriggerStatus 成功!")
    print(f"  RequestId: {resp.RequestId}")
except ImportError:
    print("  ✗ SDK 不支持 UpdateTriggerStatus API (可能需要更新 SDK)")
except Exception as e:
    print(f"  ✗ UpdateTriggerStatus 失败: {e}")

print()

# 验证触发器状态
print("[验证] 检查触发器当前状态...")
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
            status_str = "✓ 启用 (0)" if enable == "0" else "✗ 禁用 (1)"
            print(f"  触发器状态: {status_str}")
            
            trigger_desc = t.get('TriggerDesc', '')
            print(f"  TriggerDesc: {trigger_desc}")
            break
except Exception as e:
    print(f"  ✗ 检查失败: {e}")

print()
print("=" * 70)
