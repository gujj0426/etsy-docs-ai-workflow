#!/usr/bin/env python3
"""
检查 SCF 触发器状态，诊断 UpdateTriggerStatus 错误
"""
import json
import re
import sys
sys.path.insert(0, '/Users/mac/Desktop/etsy/运营文档/ai_workflow')

from tencentcloud.scf.v20180416 import scf_client
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.scf.v20180416.models import ListTriggersRequest, GetFunctionRequest, UpdateTriggerRequest

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

print("=" * 70)
print("SCF 函数和触发器状态检查")
print("=" * 70)

# 1. 检查函数状态
print("\n[1] 检查函数状态...")
try:
    req = GetFunctionRequest()
    req.FunctionName = FUNCTION_NAME
    resp = client.GetFunction(req)
    info = json.loads(resp.to_json_string())
    print(f"  ✓ 函数名称: {info.get('FunctionName')}")
    print(f"  ✓ 状态: {info.get('Status')}")
    print(f"  ✓ Handler: {info.get('Handler')}")
    print(f"  ✓ 运行时: {info.get('Runtime')}")
    print(f"  ✓ 内存: {info.get('MemorySize')}MB")
except Exception as e:
    print(f"  ✗ 错误: {e}")

# 2. 列出触发器
print("\n[2] 列出触发器...")
try:
    req = ListTriggersRequest()
    req.FunctionName = FUNCTION_NAME
    req.Namespace = "default"
    resp = client.ListTriggers(req)
    result = json.loads(resp.to_json_string())
    
    triggers = result.get('Triggers', [])
    total = result.get('TotalCount', 0)
    print(f"  ✓ 找到 {total} 个触发器:")
    print()
    
    for i, t in enumerate(triggers, 1):
        print(f"  [{i}] 名称: {t.get('TriggerName')}")
        print(f"      类型: {t.get('Type')}")
        enable = t.get('Enable')
        status_str = "✓ 启用 (0)" if enable == "0" else "✗ 禁用 (1)"
        print(f"      状态: {status_str}")
        
        # 解析 TriggerDesc
        trigger_desc = t.get('TriggerDesc', '')
        try:
            desc_obj = json.loads(trigger_desc)
            cron = desc_obj.get('cron', '')
            print(f"      Cron: {cron}")
            
            # 解析 Cron 表达式
            # 7位格式: 秒 分 时 日 月 周 年
            # 5位格式: 分 时 日 月 周
            parts = cron.strip().split()
            if len(parts) == 7:
                print(f"      （7位 Cron: 秒={parts[0]}, 分={parts[1]}, 时={parts[2]}, 日={parts[3]}, 月={parts[4]}, 周={parts[5]}）")
            elif len(parts) == 5:
                print(f"      （5位 Cron: 分={parts[0]}, 时={parts[1]}, 日={parts[2]}, 月={parts[3]}, 周={parts[4]}）")
        except:
            print(f"      TriggerDesc: {trigger_desc[:80]}...")
        print()
        
except Exception as e:
    print(f"  ✗ 错误: {e}")

print("=" * 70)
print("检查完成")
print("=" * 70)

# 3. 提供修复建议
print("\n[3] 诊断建议...")
print("  如果触发器状态为 '禁用 (1)'，可以运行以下命令启用:")
print("  cd /Users/mac/Desktop/etsy/运营文档 && python3 ai_workflow/enable_trigger.py")
print()
print("  如果 Cron 表达式不正确，enable_trigger.py 也会自动修正。")
print("=" * 70)
