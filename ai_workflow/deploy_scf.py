#!/usr/bin/env python3
"""
腾讯云 SCF 部署脚本（官方 SDK）
部署 scf_pipeline.py 到 SCF + 配置工作日定时触发器
"""

import os, sys, json, time, shutil, base64, warnings
warnings.filterwarnings("ignore")
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from tencent_env import get_tencent_secret_pair

# ── 凭证 & 区域 ──────────────────────────────────
SECRET_ID, SECRET_KEY = get_tencent_secret_pair()
REGION     = "ap-shanghai"

# ── 函数配置 ───────────────────────────────────────
FUNCTION_NAME = "etsy-ai-workflow"
ENTRY_FILE    = "index.py"
HANDLER       = "index.scf_handler"
RUNTIME       = "Python3.9"
TIMEOUT       = 300
MEMORY_SIZE   = 512
DESCRIPTION   = "Etsy AI 产品图生图 pipeline"

# 触发器：周一至周五 10:00-16:50 每10分钟
TRIGGER_NAME = "workday-every-10min"
TRIGGER_CRON = "0/10 10-16 * * 1-5"
TIMEZONE     = "Asia/Shanghai"

# ── 路径 ──────────────────────────────────────────
BUILD_DIR   = SCRIPT_DIR / "scf_build"
CONFIG_FILE = SCRIPT_DIR.parent / "config" / "tdocs_openapi_v2.json"
VOLC_PATH   = Path("/Users/mac/Library/Python/3.9/lib/python/site-packages/volcengine")


# ──────────────────────────────────────────────────
# 初始化 SCF 客户端
# ──────────────────────────────────────────────────
def make_scf_client():
    from tencentcloud.scf.v20180416 import scf_client
    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile

    cred = credential.Credential(SECRET_ID, SECRET_KEY)
    hp = HttpProfile()
    hp.endpoint = "scf.tencentcloudapi.com"
    profile = ClientProfile("TC3-HMAC-SHA256", hp)
    return scf_client.ScfClient(cred, REGION, profile)


# ──────────────────────────────────────────────────
# 构建代码包
# ──────────────────────────────────────────────────
def build_code_package() -> bytes:
    print("[1/3] 构建代码包 ...")

    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)

    # 入口文件
    (BUILD_DIR / ENTRY_FILE).write_text(
        (SCRIPT_DIR / "scf_pipeline.py").read_text()
    )
    print(f"  ✅ {ENTRY_FILE}")

    # 配置文件
    cfg_dir = BUILD_DIR / "config"
    cfg_dir.mkdir()
    (cfg_dir / "tdocs_openapi_v2.json").write_text(CONFIG_FILE.read_text())
    print(f"  ✅ config/tdocs_openapi_v2.json")

    # volcengine SDK
    if VOLC_PATH.exists():
        shutil.copytree(VOLC_PATH, BUILD_DIR / "volcengine")
        sz = sum(f.stat().st_size for f in VOLC_PATH.rglob("*") if f.is_file())
        print(f"  ✅ volcengine SDK ({sz/1024/1024:.1f} MB)")
    else:
        print("  ⚠️  volcengine SDK 未找到，需手动安装到 SCF 层")

    # 打包 zip
    zip_path = BUILD_DIR / "function.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in BUILD_DIR.rglob("*"):
            if f.is_file() and f.suffix != ".zip":
                zf.write(f, str(f.relative_to(BUILD_DIR)))

    data = zip_path.read_bytes()
    print(f"  📦 代码包大小: {len(data)/1024/1024:.1f} MB")
    return data


# ──────────────────────────────────────────────────
# 部署函数
# ──────────────────────────────────────────────────
def deploy_function(code_bytes: bytes, client):
    from tencentcloud.scf.v20180416 import models

    print(f"\n[2/3] 检查函数 [{FUNCTION_NAME}] ...")
    existing = None
    try:
        req = models.ListFunctionsRequest()
        req.Limit = 100
        resp = client.ListFunctions(req)
        for fn in resp.Functions:
            if fn.FunctionName == FUNCTION_NAME:
                existing = fn
                break
    except Exception as e:
        print(f"  ⚠️  查询失败: {e}")

    b64 = base64.b64encode(code_bytes).decode()

    if existing:
         print(f"  ℹ️  函数已存在 v{getattr(existing, 'FunctionVersion', '?')}，更新代码 ...")

         req2 = models.UpdateFunctionCodeRequest()
         req2.FunctionName = FUNCTION_NAME
         req2.ZipFile = b64
         req2.CodeSource = "ZipFile"
         try:
             client.UpdateFunctionCode(req2)
             print(f"  ✅ 代码更新成功")
         except Exception as e:
             print(f"  ❌ 代码更新失败: {e}")
             return

         time.sleep(8)

         req3 = models.UpdateFunctionConfigurationRequest()
         req3.FunctionName = FUNCTION_NAME
         req3.Description = DESCRIPTION
         req3.MemorySize  = MEMORY_SIZE
         req3.Timeout     = TIMEOUT
         req3.Runtime     = RUNTIME
         try:
             client.UpdateFunctionConfiguration(req3)
             print(f"  ✅ 配置更新成功  timeout={TIMEOUT}s  memory={MEMORY_SIZE}MB")
         except Exception as e:
             print(f"  ❌ 配置更新失败: {e}")
    else:
         print(f"  ℹ️  函数不存在，创建新函数 ...")

         req = models.CreateFunctionRequest()
         req.FunctionName = FUNCTION_NAME
         req.Description = DESCRIPTION
         req.MemorySize  = MEMORY_SIZE
         req.Timeout     = TIMEOUT
         req.Runtime     = RUNTIME
         req.Handler     = HANDLER
         req.Code = models.Code()
         req.Code.ZipFile = b64
         req.Code.CodeSource = "ZipFile"
         try:
             resp = client.CreateFunction(req)
             print(f"  ✅ 函数创建成功  handler={HANDLER}")
         except Exception as e:
             print(f"  ❌ 函数创建失败: {e}")
             sys.exit(1)

         time.sleep(8)


# ──────────────────────────────────────────────────
# 配置触发器
# ──────────────────────────────────────────────────
def setup_trigger(client):
    from tencentcloud.scf.v20180416 import models

    print(f"\n[3/3] 配置触发器 [{TRIGGER_NAME}] ...")

    # 查询已有触发器
    try:
        req0 = models.ListTriggersRequest()
        req0.FunctionName = FUNCTION_NAME
        req0.Limit = 100
        resp0 = client.ListTriggers(req0)
        for t in getattr(resp0, "Triggers", []):
            if t.TriggerName == TRIGGER_NAME:
                print(f"  🗑️  删除旧触发器 ...")
                try:
                    req_d = models.DeleteTriggerRequest()
                    req_d.FunctionName = FUNCTION_NAME
                    req_d.TriggerName  = TRIGGER_NAME
                    req_d.Type         = "Timer"
                    client.DeleteTrigger(req_d)
                    time.sleep(2)
                except Exception:
                    pass
    except Exception as e:
        print(f"  ℹ️  查询触发器失败（忽略）: {e}")

    # 创建新触发器（Timer 用 TriggerDesc 传 cron）
    try:
        req = models.CreateTriggerRequest()
        req.FunctionName = FUNCTION_NAME
        req.TriggerName  = TRIGGER_NAME
        req.Type         = "Timer"
        req.TriggerDesc  = TRIGGER_CRON
        req.Enable       = True
        client.CreateTrigger(req)
        print(f"  ✅ 触发器创建成功！")
        print(f"      Cron: {TRIGGER_CRON}")
        print(f"      时区: {TIMEZONE}")
    except Exception as e:
        print(f"  ❌ 触发器创建失败: {e}")
        return

    # 设置时区（通过 UpdateTriggerStatus 更新）
    try:
        req2 = models.UpdateTriggerStatusRequest()
        req2.FunctionName = FUNCTION_NAME
        req2.TriggerName  = TRIGGER_NAME
        req2.Enable       = "TRUE"
        req2.Timezone      = TIMEZONE
        client.UpdateTriggerStatus(req2)
        print(f"  ✅ 触发器时区已设置: {TIMEZONE}")
    except Exception as e:
        print(f"  ⚠️  时区设置失败（可手动去控制台设置）: {e}")


# ──────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  🚀  Etsy AI WorkFlow → 腾讯云 SCF 部署")
    print("=" * 60)

    code_bytes = build_code_package()
    client = make_scf_client()
    print(f"\n  ✅ SCF 客户端就绪 ({REGION})")

    deploy_function(code_bytes, client)
    setup_trigger(client)

    print("\n" + "=" * 60)
    print(f"  ✅ 部署完成！")
    print(f"  📋 函数名:  {FUNCTION_NAME}")
    print(f"  🔧  入口:    {HANDLER}")
    print(f"  ⏰  触发:    周一至周五 10:00-16:50 每10分钟")
    print(f"  🌐  控制台:   https://console.cloud.tencent.com/scf")
    print("=" * 60)


if __name__ == "__main__":
    import zipfile  # 延迟导入，避免顶层 import 失败
    main()
