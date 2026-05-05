#!/usr/bin/env python3
"""Enable SCF timer trigger and fix Cron expression"""
import json, re, sys
sys.path.insert(0, '/Users/mac/Desktop/etsy/运营文档/ai_workflow')

from tencentcloud.scf.v20180416 import scf_client
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.scf.v20180416.models import UpdateTriggerRequest

# Read credentials
with open('/Users/mac/Desktop/etsy/运营文档/ai_workflow/deploy_scf.py') as f:
    content = f.read()
SECRET_ID  = re.search(r'SECRET_ID\s*=\s*"([^"]+)"', content).group(1)
SECRET_KEY = re.search(r'SECRET_KEY\s*=\s*"([^"]+)"', content).group(1)

cred = credential.Credential(SECRET_ID, SECRET_KEY)
hp = HttpProfile()
hp.endpoint = "scf.tencentcloudapi.com"
profile = ClientProfile()
profile.httpProfile = hp
client = scf_client.ScfClient(cred, "ap-shanghai", profile)

# Enable trigger and fix Cron: 0/10 10-17 * * * (10:00~17:50 every 10min)
req = UpdateTriggerRequest()
req.FunctionName = "etsy-ai-workflow"
req.Namespace   = "default"
req.TriggerName = "workday-every-10min"
req.Type         = "timer"
req.TriggerDesc = json.dumps({
    "cron": "0 0/10 10-17 * * *"
})
req.Enable = "0"  # 0=启用, 1=禁用

resp = client.UpdateTrigger(req)
print("✅ 触发器已更新！")
print(resp.to_json_string(indent=2))
