#!/usr/bin/env python3
"""Verify SCF function status and correctly test volcengine import"""
import json, re, sys, importlib
sys.path.insert(0, '/Users/mac/Desktop/etsy/运营文档/ai_workflow')

from tencentcloud.scf.v20180416 import scf_client
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.scf.v20180416.models import GetFunctionRequest

# Read credentials from deploy_scf.py
with open('/Users/mac/Desktop/etsy/运营文档/ai_workflow/deploy_scf.py') as f:
    content = f.read()
SECRET_ID  = re.search(r'SECRET_ID\s*=\s*"([^"]+)"', content).group(1)
SECRET_KEY = re.search(r'SECRET_KEY\s*=\s*"([^"]+)"', content).group(1)

# Create SCF client
cred = credential.Credential(SECRET_ID, SECRET_KEY)
hp = HttpProfile()
hp.endpoint = "scf.tencentcloudapi.com"
profile = ClientProfile()
profile.httpProfile = hp
client = scf_client.ScfClient(cred, "ap-shanghai", profile)

# Get function status
req = GetFunctionRequest()
req.FunctionName = "etsy-ai-workflow"
req.Namespace = "default"
resp = client.GetFunction(req)
data = json.loads(resp.to_json_string())

print("=" * 50)
print(f"函数名称: {data.get('FunctionName')}")
print(f"运行状态: {data.get('Status')}")
print(f"Handler:   {data.get('Handler')}")
print(f"Runtime:   {data.get('Runtime')}")
print(f"内存:      {data.get('MemorySize')} MB")
print(f"超时:      {data.get('Timeout')} s")
print("=" * 50)

# List triggers
triggers = data.get('Triggers', [])
print(f"\n触发器数量: {len(triggers)}")
for t in triggers:
    enable_val = t.get('Enable', '')
    # SCF API: Enable=0 表示启用, 1=禁用, 2=更新中
    enable_map = {"0": "✅ 已启用", "1": "❌ 已禁用", "2": "⏳ 更新中"}
    trigger_name = t.get('TriggerName', '')
    trigger_type = t.get('Type', '')
    cron_desc = t.get('TriggerDesc', '')
    print(f"  - 名称: {trigger_name}")
    print(f"    类型: {trigger_type}")
    print(f"    状态: {enable_map.get(str(enable_val), str(enable_val))}")
    print(f"    Cron: {cron_desc}")
    print()

# Test the ACTUAL import that scf_pipeline.py uses
print("测试 volcengine.visual.VisualService 导入（scf_pipeline.py 实际用法）...")
try:
    import importlib
    vs = importlib.import_module('volcengine.visual.VisualService')
    print("  ✅ volcengine.visual.VisualService 导入成功")
except Exception as e:
    print(f"  ❌ 导入失败: {e}")
    # List what's in volcengine.visual
    import os
    vp = '/Users/mac/Desktop/etsy/运营文档/ai_workflow/volcengine/visual/'
    if os.path.isdir(vp):
        files = [f for f in os.listdir(vp) if f.endswith('.py')][:10]
        print(f"  volcengine/visual/ 内容: {files}")
