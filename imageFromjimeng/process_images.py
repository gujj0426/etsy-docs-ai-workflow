#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


def _project_root() -> Path:
    """源码运行时取脚本目录；PyInstaller 打包后取可执行文件所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


PROJECT_DIR = _project_root()
CONFIG_PATH = PROJECT_DIR / "config.json"


def get_example_path() -> Path:
    """优先同级目录的模板；单文件打包时回退到 PyInstaller 解压目录。"""
    side = PROJECT_DIR / "config.example.json"
    if side.exists():
        return side
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / "config.example.json"
        if bundled.exists():
            return bundled
    return side


CATEGORY_KEYS = ("pet_black", "pet_nonblack", "human_black", "human_nonblack")

ALLOWED_SUFFIX = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def resolve_project_path(raw: str | Path) -> Path:
    """配置里的相对路径一律相对于项目根目录（不依赖当前工作目录）。"""
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (PROJECT_DIR / p).resolve()
    return p


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        ex = get_example_path()
        if not ex.exists():
            raise RuntimeError(f"缺少模板文件：请在程序同目录放置 config.example.json")
        shutil.copyfile(ex, CONFIG_PATH)
        raise RuntimeError(f"未找到 config.json，已自动创建模板：{CONFIG_PATH}")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_prompts(cfg: dict) -> dict[str, str]:
    """
    从 config.json 的 prompts 节读取四类提示词。
    若某键缺失或为空，则尝试用同目录 config.example.json 中的对应项补齐。
    """
    user_pr = cfg.get("prompts")
    if not isinstance(user_pr, dict):
        user_pr = {}

    merged: dict[str, str] = {}
    for k in CATEGORY_KEYS:
        v = user_pr.get(k)
        merged[k] = str(v).strip() if v is not None else ""

    missing = [k for k in CATEGORY_KEYS if not merged[k]]
    if not missing:
        return merged

    ex_path = get_example_path()
    if ex_path.exists():
        try:
            ex = json.loads(ex_path.read_text(encoding="utf-8"))
            ex_pr = ex.get("prompts")
            if isinstance(ex_pr, dict):
                for k in missing:
                    ev = ex_pr.get(k)
                    if ev is not None and str(ev).strip():
                        merged[k] = str(ev).strip()
        except Exception:
            pass

    still = [k for k in CATEGORY_KEYS if not merged[k]]
    if still:
        raise RuntimeError(
            "config.json 中 prompts 不完整，缺少或为空："
            + ", ".join(still)
            + "。请从 config.example.json 复制 prompts 整段到 config.json。"
        )
    return merged


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _hmac_sha256(key: bytes, data: str) -> bytes:
    return hmac.new(key, data.encode(), hashlib.sha256).digest()


def _hmac_sha256_hex(key: bytes, data: str) -> str:
    return hmac.new(key, data.encode(), hashlib.sha256).hexdigest()


def volc_request(
    ak: str,
    sk: str,
    action: str,
    payload: dict,
    timeout: int = 60,
    max_retries: int = 5,
) -> dict:
    host = "visual.volcengineapi.com"
    endpoint = f"https://{host}"
    api_ver = "2022-08-31"
    service = "cv"
    region = "cn-north-1"

    body_str = json.dumps(payload, ensure_ascii=False)
    body_bytes = body_str.encode("utf-8")
    body_sha256 = hashlib.sha256(body_bytes).hexdigest()

    now_ts = int(time.time())
    x_date = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now_ts))
    date_str = x_date[:8]

    signed_headers_list = ["content-type", "host", "x-content-sha256", "x-date"]
    signed_headers_str = "\n".join(
        [
            "content-type:application/json",
            f"host:{host}",
            f"x-content-sha256:{body_sha256}",
            f"x-date:{x_date}",
        ]
    ) + "\n"

    canonical_request = "\n".join(
        [
            "POST",
            "/",
            f"Action={action}&Version={api_ver}",
            signed_headers_str,
            ";".join(signed_headers_list),
            body_sha256,
        ]
    )

    credential_scope = f"{date_str}/{region}/{service}/request"
    string_to_sign = "\n".join(
        [
            "HMAC-SHA256",
            x_date,
            credential_scope,
            _sha256_hex(canonical_request),
        ]
    )

    k1 = _hmac_sha256(sk.encode(), date_str)
    k2 = _hmac_sha256(k1, region)
    k3 = _hmac_sha256(k2, service)
    signing_key = _hmac_sha256(k3, "request")
    signature = _hmac_sha256_hex(signing_key, string_to_sign)

    auth = (
        f"HMAC-SHA256 Credential={ak}/{credential_scope}, "
        f"SignedHeaders={';'.join(signed_headers_list)}, Signature={signature}"
    )
    headers = {
        "Authorization": auth,
        "Content-Type": "application/json",
        "Host": host,
        "X-Date": x_date,
        "X-Content-Sha256": body_sha256,
    }
    url = f"{endpoint}/?Action={action}&Version={api_ver}"
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")

    result = None
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode())
            break
        except urllib.error.HTTPError as e:
            err_body = e.read().decode(errors="replace")
            retry = False
            if e.code == 429:
                retry = True
            else:
                try:
                    ej = json.loads(err_body)
                    if ej.get("code") == 50430 or "Concurrent" in ej.get("message", ""):
                        retry = True
                except Exception:
                    pass
            if retry and attempt < max_retries:
                wait = 2**attempt
                print(f"  ⚠️ 即梦请求受限（HTTP {e.code}），{wait}s 后重试 ({attempt + 1}/{max_retries})...")
                time.sleep(wait)
                continue
            raise RuntimeError(f"HTTP {e.code}: {err_body[:400]}") from e
        except Exception as e:
            if attempt < max_retries:
                wait = 2**attempt
                print(f"  ⚠️ 请求异常：{e}，{wait}s 后重试...")
                time.sleep(wait)
                continue
            raise

    code = str(result.get("code", "10000"))
    if code != "10000":
        raise RuntimeError(f"即梦 API 错误[{code}] {result.get('message', '')}")
    return result


def jimeng_generate(ak: str, sk: str, image_bytes: bytes, prompt: str, seed: int) -> bytes:
    submit = volc_request(
        ak,
        sk,
        "CVSync2AsyncSubmitTask",
        {
            "req_key": "jimeng_t2i_v40",
            "prompt": prompt,
            "binary_data_base64": [base64.b64encode(image_bytes).decode()],
            "return_url": True,
            "extra": {"seed": seed},
        },
    )
    task_id = submit.get("data", {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"提交成功但无 task_id: {submit}")

    start = time.time()
    while True:
        if time.time() - start > 600:
            raise TimeoutError(f"任务超时: {task_id}")
        result = volc_request(
            ak,
            sk,
            "CVSync2AsyncGetResult",
            {"task_id": task_id, "req_key": "jimeng_t2i_v40"},
        )
        data = result.get("data", {})
        status = data.get("status") or data.get("Status")
        if status == "done":
            b64_list = data.get("binary_data_base64") or data.get("BinaryData") or []
            if b64_list:
                return base64.b64decode(b64_list[0])
            urls = data.get("image_urls") or data.get("ImageUrls") or []
            if not urls:
                raise RuntimeError("done 但无图片数据")
            req = urllib.request.Request(urls[0], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        if status in ("failed", "Failed", "not_found"):
            raise RuntimeError(f"任务失败: {result}")
        time.sleep(3)


def unique_path(dst_dir: Path, filename: str) -> Path:
    target = dst_dir / filename
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    idx = 1
    while True:
        candidate = dst_dir / f"{stem}_{idx}{suffix}"
        if not candidate.exists():
            return candidate
        idx += 1


def process_one_folder(
    ak: str,
    sk: str,
    seed: int,
    key: str,
    prompt: str,
    input_dir: Path,
    output_dir: Path,
    backup_dir: Path,
    delay_after_success: float,
) -> tuple[int, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    input_dir.mkdir(parents=True, exist_ok=True)

    success = 0
    failed = 0
    files = [p for p in sorted(input_dir.iterdir()) if p.is_file() and p.suffix.lower() in ALLOWED_SUFFIX]
    for src in files:
        try:
            print(f"[{key}] 处理: {src.name}")
            generated = jimeng_generate(ak, sk, src.read_bytes(), prompt, seed)
            out_name = f"{src.stem}_ai_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            out_path = unique_path(output_dir, out_name)
            out_path.write_bytes(generated)
            backup_path = unique_path(backup_dir, src.name)
            shutil.move(str(src), str(backup_path))
            print(f"[{key}] 成功 -> 输出: {out_path.name} | 备份: {backup_path.name}")
            success += 1
            if delay_after_success > 0:
                time.sleep(delay_after_success)
        except Exception as exc:
            failed += 1
            print(f"[{key}] 失败 {src.name}: {exc}")
    return success, failed


def main() -> int:
    try:
        cfg = load_config()
    except Exception as exc:
        print(exc)
        print("请填写 config.json 后重新运行。")
        return 1

    ak = os.environ.get("JIMENG_AK") or cfg.get("jimeng_ak", "")
    sk = os.environ.get("JIMENG_SK") or cfg.get("jimeng_sk", "")
    if not ak or not sk:
        print("缺少即梦凭证：请在 config.json 填写 jimeng_ak/jimeng_sk，或设置环境变量 JIMENG_AK/JIMENG_SK。")
        return 2

    seed = int(cfg.get("seed", 12345))
    delay_after_success = float(cfg.get("delay_seconds_between_requests", 3))
    prompts = load_prompts(cfg)
    folders = cfg.get("folders", {})
    total_ok = 0
    total_fail = 0
    for key in CATEGORY_KEYS:
        f = folders.get(key, {})
        input_dir = resolve_project_path(f.get("input", f"input/{key}"))
        output_dir = resolve_project_path(f.get("output", f"output/{key}"))
        backup_dir = resolve_project_path(f.get("backup", f"backup/{key}"))
        ok, fail = process_one_folder(
            ak,
            sk,
            seed,
            key,
            prompts[key],
            input_dir,
            output_dir,
            backup_dir,
            delay_after_success,
        )
        total_ok += ok
        total_fail += fail

    print("=" * 60)
    print(f"完成：成功 {total_ok} 张，失败 {total_fail} 张")
    print("=" * 60)
    return 0 if total_fail == 0 else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已中断。")
        raise SystemExit(130) from None
    except Exception:
        import traceback

        traceback.print_exc()
        raise SystemExit(1) from None
