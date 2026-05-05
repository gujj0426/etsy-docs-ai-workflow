#!/usr/bin/env python3
"""
删除并重新创建 SCF 定时器触发器
"""
import json
import sys
import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
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

print("=" * 70)
print("删除并重新创建 SCF 触发器")
print("=" * 70)
print()

# 1. 删除现有触发器
print("[1] 删除现有触发器...")
try:
    from tencentcloud.scf.v20180416.models import DeleteTriggerRequest
    
    req = DeleteTriggerRequest()
    req.FunctionName = FUNCTION_NAME
    req.Namespace = "default"
    req.TriggerName = TRIGGER_NAME
    req.Type = "timer"
    
    resp = client.DeleteTrigger(req)
    print(f"  ✓ 触发器删除成功!")
    print(f"  RequestId: {resp.RequestId}")
except Exception as e:
    print(f"  ✗ 删除失败 (可能触发器不存在): {e}")

print()
time.sleep(2)  # 等待删除完成

# 2. 创建新触发器
print("[2] 创建新触发器...")
try:
    from tencentcloud.scf.v20180416.models import CreateTriggerRequest
    
    req = CreateTriggerRequest()
    req.FunctionName = FUNCTION_NAME
    req.Namespace = "default"
    req.TriggerName = TRIGGER_NAME
    req.Type = "timer"
    req.TriggerDesc = json.dumps({
        "cron": "0 0/10 10-17 * * * *"  # 7位 Cron: 每天 10:00~17:50 每10分钟
    })
    req.Enable = "0"  # 0=启用, 1=禁用
    
    resp = client.CreateTrigger(req)
    print(f"  ✓ 触发器创建成功!")
    print(f"  RequestId: {resp.RequestId}")
except Exception as e:
    print(f"  ✗ 创建失败: {e}")

print()
time.sleep(2)  # 等待创建完成

# 3. 验证触发器状态
print("[3] 验证触发器状态...")
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
            print(f"  ✓ 触发器状态: {status_str}")
            print(f"  ✓ TriggerDesc: {t.get('TriggerDesc')}")
            break
    else:
        print(f"  ✗ 未找到触发器 '{TRIGGER_NAME}'")
except Exception as e:
    print(f"  ✗ 验证失败: {e}")

print()
print("=" * 70)
print("完成")
print("=" * 70)
