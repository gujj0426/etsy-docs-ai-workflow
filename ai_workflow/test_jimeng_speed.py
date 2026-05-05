#!/usr/bin/env python3
"""
即梦4.0 API 响应速度测试
测试目标：确认即梦任务从提交到完成（status=done）的真实耗时
"""
import sys
import os
import time
import json
import hmac
import hashlib

sys.path.insert(0, '/Users/mac/Desktop/etsy/运营文档')
sys.path.insert(0, '/Users/mac/Desktop/etsy/运营文档/ai_workflow')

# 导入即梦凭证（从 scf_pipeline 复用）
from scf_pipeline import JIMENG_AK, JIMENG_SK

ENDPOINT  = "https://visual.volcengineapi.com"
REQ_KEY   = "jimeng_t2i_v40"
API_VER   = "2022-08-31"
SERVICE   = "cv"
REGION    = "cn-north-1"

# 200x200 绿色 PNG（有效测试图）
TEST_IMG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAMgAAADICAIAAAAiOjnJAAACFUlEQVR4nO3SQQkAIADAQMMazDjGsoRDkIMLsMfGXhOuG88L"
    "+JKxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIG"
    "IuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxS"
    "BiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEs"
    "UgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLh"
    "LFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi"
    "4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi8QBKo/TaWEaBAIAAAAASUVORK5CYII="
)

PROMPT = "将参考图片转换为精细黑白线稿，纯白背景，黑白色，高对比度，精细工笔画风格，忠实还原原图细节"


def _hmac_sha256(key: bytes, data: str) -> bytes:
    return hmac.new(key, data.encode(), hashlib.sha256).digest()

def _hmac_sha256_hex(key: bytes, data: str) -> str:
    return hmac.new(key, data.encode(), hashlib.sha256).hexdigest()

def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def api_call(action, payload, max_retries=5):
    """
    发一次 HTTP 请求，返回结果和耗时。
    有 429 时自动重试（指数退避）。
    """
    import urllib.request

    body_str  = json.dumps(payload, separators=(',', ':'))
    body_bytes= body_str.encode()

    # 时间
    now_ts  = int(time.time())
    x_date  = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now_ts))
    date_str = x_date[:8]
    body_sha = hashlib.sha256(body_bytes).hexdigest()

    # 签名
    signed_headers_list = ["content-type", "host", "x-content-sha256", "x-date"]
    signed_headers_str  = "\n".join(f"{k}:{v}" for k, v in [
        ("content-type", "application/json"),
        ("host", "visual.volcengineapi.com"),
        ("x-content-sha256", body_sha),
        ("x-date", x_date),
    ]) + "\n"

    canonical_request = "\n".join([
        "POST", "/",
        f"Action={action}&Version={API_VER}",
        signed_headers_str,
        ";".join(signed_headers_list),
        body_sha,
    ])

    credential_scope = f"{date_str}/{REGION}/{SERVICE}/request"
    string_to_sign   = "\n".join([
        "HMAC-SHA256", x_date, credential_scope, _sha256_hex(canonical_request),
    ])

    k1 = _hmac_sha256(JIMENG_SK.encode(), date_str)
    k2 = _hmac_sha256(k1, REGION)
    k3 = _hmac_sha256(k2, SERVICE)
    signing_key = _hmac_sha256(k3, "request")
    signature   = _hmac_sha256_hex(signing_key, string_to_sign)

    auth = (
        f"HMAC-SHA256 Credential={JIMENG_AK}/{credential_scope}, "
        f"SignedHeaders={';'.join(signed_headers_list)}, Signature={signature}"
    )

    headers = {
        "Authorization":      auth,
        "Content-Type":       "application/json",
        "Host":               "visual.volcengineapi.com",
        "X-Date":             x_date,
        "X-Content-Sha256":   body_sha,
    }

    url = f"{ENDPOINT}/?Action={action}&Version={API_VER}"

    for attempt in range(max_retries + 1):
        t0 = time.time()
        try:
            req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())
            elapsed = time.time() - t0
            return result, elapsed, None
        except urllib.error.HTTPError as e:
            err_body = e.read().decode(errors="replace")
            elapsed  = time.time() - t0
            # 429 或即梦并发超限
            if e.code == 429:
                should_retry = True
            else:
                try:
                    ej = json.loads(err_body)
                    should_retry = (ej.get("code") == 50430 or "Concurrent" in ej.get("message", ""))
                except Exception:
                    should_retry = False
            if should_retry and attempt < max_retries:
                wait = 2 ** attempt
                print(f"  ⚠️  [{action}] HTTP {e.code} 并发超限，{wait}s 后重试（{attempt+1}/{max_retries}）...")
                time.sleep(wait)
                continue
            return None, elapsed, f"HTTP {e.code}: {err_body[:300]}"
        except Exception as e:
            elapsed = time.time() - t0
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            return None, elapsed, str(e)

    return None, 0, "max retries exceeded"


def main():
    import datetime as dt
    print("=" * 60)
    print("即梦4.0 API 响应速度测试")
    print(f"测试时间: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"即梦AK: {JIMENG_AK[:8]}...")
    print("=" * 60)

    # ── Step 1: 提交任务 ─────────────────────────────────
    print("\n[Step 1] 提交即梦任务...")
    payload = {
        "req_key": REQ_KEY,
        "prompt":  PROMPT,
        "binary_data_base64": [TEST_IMG_B64],
        "return_url": True,
        "extra": {"seed": 12345},
    }

    resp, t_submit, err = api_call("CVSync2AsyncSubmitTask", payload)
    print(f"  提交耗时: {t_submit:.2f}s")

    if err:
        print(f"  ❌ 提交失败: {err}")
        return
    if resp is None:
        print("  ❌ 提交失败（resp=None）")
        return

    print(f"  提交响应: {json.dumps(resp, ensure_ascii=False)[:300]}")

    code    = resp.get("code")
    task_id = resp.get("data", {}).get("task_id")
    if not task_id:
        print(f"  ❌ 提交失败，code={code}，msg={resp.get('message')}")
        return

    print(f"  ✅ 任务提交成功！task_id={task_id}")

    # ── Step 2: 轮询直到完成 ────────────────────────────
    print("\n[Step 2] 开始轮询即梦任务状态（每3秒一次）...")

    total_start = time.time()
    poll_count  = 0
    last_status = ""

    while True:
        poll_count += 1
        r, pt, err2 = api_call("CVSync2AsyncGetResult", {
            "task_id": task_id,
            "req_key": REQ_KEY,
        }, max_retries=3)

        resp_data = (r or {}).get("data", {})
        # 实际响应字段全部小写
        status    = resp_data.get("status", "") or resp_data.get("Status", "")
        sub_status= resp_data.get("sub_status", "") or resp_data.get("SubStatus", "")

        elapsed_total = time.time() - total_start
        print(f"  #{poll_count:3d} | 总耗时: {elapsed_total:6.1f}s | "
              f"本轮: {pt:.2f}s | Status={status!r} SubStatus={sub_status!r} | "
              f"err={err2!r}")

        if status == "done":
            binary = resp_data.get("binary_data_base64") or resp_data.get("BinaryData") or []
            urls   = resp_data.get("image_urls") or resp_data.get("ImageUrls") or []
            print(f"\n🎉 即梦完成！")
            print(f"   总耗时: {elapsed_total:.1f}s")
            print(f"   轮询次数: {poll_count}")
            print(f"   图片数量: {len(binary)}")
            print(f"   URL数量:  {len(urls)}")
            if urls:
                print(f"   首张URL: {urls[0][:120]}")
            # 保存结果
            with open("/tmp/jimeng_result.json", "w") as f:
                json.dump({"task_id": task_id, "status": "done", "urls": urls,
                            "binary_count": len(binary), "elapsed_s": elapsed_total,
                            "poll_count": poll_count}, f, ensure_ascii=False, indent=2)
            print(f"   结果已保存到 /tmp/jimeng_result.json")
            break

        elif status in ("failed", "Failed", "error"):
            print(f"\n❌ 任务失败，status={status}")
            print(f"   resp_data={json.dumps(resp_data, ensure_ascii=False)[:400]}")
            break

        elif status == "pending" or status == "":
            # 仍在处理，继续轮询
            time.sleep(3)
            continue

        else:
            # 未知状态，也继续
            print(f"   [未知Status，继续等待]")
            time.sleep(3)
            continue

        # 超时保护（10分钟）
        if elapsed_total > 600:
            print(f"\n⏰ 超时（>600s），status={status}，退出")
            break


if __name__ == "__main__":
    main()
