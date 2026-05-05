#!/usr/bin/env python3
"""
直接调用 UpdateTriggerStatus API 启用触发器
"""
import json
import re
import sys
sys.path.insert(0, '/Users/mac/Desktop/etsy/运营文档/ai_workflow')

from tencentcloud.scf.v20180416 import scf_client
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.common.abstract_model import AbstractModel

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
print("启用 SCF 触发器")
print("=" * 70)

# 方法1: 使用 UpdateTrigger 更新 Enable 字段
print("\n[方法1] 使用 UpdateTrigger 更新触发器...")
try:
    from tencentcloud.scf.v20180416.models import UpdateTriggerRequest
    
    req = UpdateTriggerRequest()
    req.FunctionName = FUNCTION_NAME
    req.Namespace = "default"
    req.TriggerName = TRIGGER_NAME
    req.Type = "timer"
    req.TriggerDesc = json.dumps({
        "cron": "0 0/10 10-17 * * * *"  # 7位 Cron
    })
    req.Enable = "0"  # 0=启用
    
    resp = client.UpdateTrigger(req)
    print(f"  ✓ UpdateTrigger 成功!")
    print(f"  Response: {resp.to_json_string()}")
except Exception as e:
    print(f"  ✗ UpdateTrigger 失败: {e}")

# 方法2: 尝试直接调用 UpdateTriggerStatus (如果需要)
print("\n[方法2] 检查是否需要使用 UpdateTriggerStatus...")
print("  (UpdateTriggerStatus 是独立的 API，用于仅更新触发器状态)")

# 验证触发器状态
print("\n[验证] 检查触发器当前状态...")
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
            print(f"  TriggerDesc: {t.get('TriggerDesc')}")
            break
except Exception as e:
    print(f"  ✗ 检查失败: {e}")

print("=" * 70)
