"""
火山方舟 Seedream 4.0 / 即梦AI 图生图 API 接入脚本
=========================================================

支持两套接口（任选其一）：

路径A：火山方舟 Ark（推荐，无需 LUMI）
  端点：https://ark.cn-beijing.volces.com/api/v3
  认证：Bearer Token（ARK API Key，方舟控制台获取）
  模型：doubao-seedream-4-0-250828（即梦4.0）等
  特点：OpenAI 兼容格式，Bearer Token，无需 LUMI 开通

路径B：火山引擎 CV 视觉服务（即梦4.0，2026-04-18 实测通过）
  端点：https://visual.volcengineapi.com
  认证：AK/SK + SigV4 签名（volcengine SDK）
  req_key：jimeng_t2i_v40
  特点：yugu 子账户 AK/SK 直接可用，无需额外开通

依赖：pip install requests Pillow volcengine
"""

import os
import time
import json
import requests
import hashlib
from pathlib import Path
from typing import Optional, Union, List
from urllib.parse import urlparse

# ─────────────────────────────────────────────
# 配置区
# ─────────────────────────────────────────────
# 方式1：从环境变量读取（推荐，敏感信息不硬编码）
ARK_API_KEY = os.getenv("ARK_API_KEY", "")

# 方式2：直接填入（仅本地测试用，完成后删除或置空）
# ARK_API_KEY = "your-ark-api-key-here"

# API 端点（OpenAI 兼容格式）
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

# 支持的模型
MODEL_SEEDREAM_4_0 = "doubao-seedream-4-0-250828"
MODEL_SEEDREAM_4_5 = "doubao-seedream-4-5-251128"
MODEL_SEEDREAM_5_0 = "doubao-seedream-5-0-260128"
MODEL_SEEDREAM_5_0_LITE = "doubao-seedream-5-0-lite-260128"

# 默认使用 Seedream 4.0（即梦4.0）
DEFAULT_MODEL = MODEL_SEEDREAM_4_0

# 输出目录
OUTPUT_DIR = Path(__file__).parent / "generated_images"
OUTPUT_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# 路径B：火山引擎 CV 视觉服务（即梦4.0 SDK 方式）
# ─────────────────────────────────────────────

class JimengV2Client:
    """
    即梦AI 4.0 图生图客户端（CV 视觉服务路径）
    端点：https://visual.volcengineapi.com
    req_key：jimeng_t2i_v40
    认证：volcengine SDK（AK/SK SigV4 签名）
    """

    def __init__(self, ak: str = None, sk: str = None):
        from volcengine.visual.VisualService import VisualService
        self.ak = ak or os.getenv("JIMENG_AK", "")
        self.sk = sk or os.getenv("JIMENG_SK", "")
        self._client = VisualService()
        self._client.set_ak(self.ak)
        self._client.set_sk(self.sk)

    def submit(self, prompt: str, image_urls: list = None,
               binary_data_base64: list = None,
               return_url: bool = True, **kwargs) -> str:
        """
        提交即梦4.0生成任务，返回 task_id

        参数:
            image_urls:            参考图 URL 列表（公网可访问）
            binary_data_base64:    参考图 base64 列表（可替代 image_urls，
                                   直接传本地图片的 base64 编码，
                                   API 实测可用！2026-04-18 验证）
        """
        body = {"req_key": "jimeng_t2i_v40", "prompt": prompt}
        if image_urls:
            body["image_urls"] = image_urls
        if binary_data_base64:
            body["binary_data_base64"] = binary_data_base64
        if return_url:
            body["return_url"] = True
        body.update(kwargs)
        resp = self._client.cv_sync2async_submit_task(body)
        if resp.get("code") != 10000:
            raise RuntimeError(f"提交失败: {resp}")
        return resp["data"]["task_id"]

    def get_result(self, task_id: str) -> dict:
        """查询任务结果"""
        resp = self._client.cv_sync2async_get_result(
            {"task_id": task_id, "req_key": "jimeng_t2i_v40"}
        )
        return resp

    def generate(self, prompt: str, image_urls: list = None,
                 binary_data_base64: list = None,
                 poll_interval: int = 3, max_wait: int = 300,
                 **kwargs) -> dict:
        """
        同步调用：提交任务 → 轮询 → 返回结果（含图片 URL 或 base64）

        参数:
            image_urls:            参考图 URL 列表
            binary_data_base64:    参考图 base64 列表（实测 API 直接接受，2026-04-18）
            seed:                  随机种子（固定值可复现结果，推荐 seed=12345）
        """
        task_id = self.submit(prompt, image_urls, binary_data_base64, **kwargs)
        start = time.time()
        while True:
            elapsed = time.time() - start
            if elapsed > max_wait:
                raise TimeoutError(f"任务 {task_id} 超过 {max_wait}s 未完成")
            resp = self.get_result(task_id)
            status = resp.get("data", {}).get("status", "")
            if status == "done":
                return resp
            elif status in ("failed", "not_found"):
                raise RuntimeError(f"任务失败: {resp}")
            time.sleep(poll_interval)


# ─────────────────────────────────────────────
# 核心请求类（路径A：火山方舟 Ark）
# ─────────────────────────────────────────────

class ArkClient:
    """火山方舟 Ark API 客户端"""

    def __init__(self, api_key: str = None, base_url: str = ARK_BASE_URL):
        self.api_key = api_key or ARK_API_KEY
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })

    def _post(self, endpoint: str, payload: dict, timeout: int = 60) -> dict:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        resp = self.session.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def _get(self, endpoint: str, timeout: int = 30) -> dict:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        resp = self.session.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    # ─────────────────────────────────────────
    # 同步文生图 / 图生图（直接返回结果）
    # 注意：同步接口有超时限制，图片生成较慢时不适用，
    #       建议使用异步接口 submit_task + query_task
    # ─────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        image: Optional[str] = None,
        size: str = "2K",
        n: int = 1,
        response_format: str = "url",
        watermark: bool = False,
        sequential: str = "disabled",
        timeout: int = 180,
    ) -> dict:
        """
        文生图 / 图生图（同步模式，适合快速测试）

        参数:
            prompt:   图片描述
            model:    模型 ID
            image:    参考图 URL（图生图时填入）
            size:     尺寸，4.0 支持 1K/2K/4K，4.5 支持 2K/4K，5.0 支持 2K/3K
            n:        生成数量
            response_format: url | b64_json
            watermark: 是否添加水印
            sequential: 组图模式，auto=自动组图，disabled=单张
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "n": n,
            "response_format": response_format,
            "watermark": watermark,
        }
        if image:
            payload["image"] = image
        if sequential and sequential != "disabled":
            payload["sequential_image_generation"] = sequential

        resp = self._post("images/generations", payload, timeout=timeout)
        return resp

    # ─────────────────────────────────────────
    # 异步文生图 / 图生图（推荐，适合生产环境）
    # 流程：submit → 轮询 task_id → 下载图片
    # ─────────────────────────────────────────

    def submit_task(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        image: Optional[str] = None,
        size: str = "2K",
        n: int = 1,
        response_format: str = "url",
        watermark: bool = False,
    ) -> str:
        """
        提交生成任务，返回 task_id
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "n": n,
            "response_format": response_format,
            "watermark": watermark,
        }
        if image:
            payload["image"] = image

        resp = self._post("images/generations/submit", payload)
        # 响应格式：{"task_id": "xxx", "status": "pending"}
        return resp.get("task_id") or resp.get("id")

    def query_task(self, task_id: str) -> dict:
        """
        查询任务状态，返回完整响应
        """
        return self._get(f"images/generations/tasks/{task_id}")

    def wait_for_task(
        self,
        task_id: str,
        poll_interval: int = 3,
        max_wait: int = 300,
    ) -> dict:
        """
        轮询等待任务完成，返回生成结果

        返回结构示例:
            {
                "status": "succeed",
                "data": [{"url": "https://..."}],
                "task_id": "xxx"
            }
        """
        start = time.time()
        while True:
            elapsed = time.time() - start
            if elapsed > max_wait:
                raise TimeoutError(f"任务 {task_id} 超过 {max_wait}s 未完成")

            result = self.query_task(task_id)
            status = result.get("status", "").lower()

            if status == "succeed":
                return result
            elif status in ("failed", "error"):
                raise RuntimeError(f"任务失败: {result.get('error', result)}")

            time.sleep(poll_interval)

    def generate_async(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        image: Optional[str] = None,
        size: str = "2K",
        n: int = 1,
        poll_interval: int = 3,
        max_wait: int = 300,
    ) -> dict:
        """
        异步生成（推荐）：自动提交+轮询+返回，等同于同步调用但更稳定
        """
        task_id = self.submit_task(prompt, model, image, size, n)
        return self.wait_for_task(task_id, poll_interval, max_wait)


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────

def download_image_bytes(url: str) -> bytes:
    """
    从腾讯文档 CDN 下载图片 bytes。
    直接复用 sheet_client.download_image_bytes（Referer/Origin 头已配好，实测通过）。
    """
    from sheet_client import download_image_bytes as _dl
    return _dl(url)


def download_image(url: str, save_path: Union[str, Path]) -> Path:
    """下载图片到本地（内部用 Referer 头）"""
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_bytes(download_image_bytes(url))
    return save_path


def generate_image_name(prefix: str = "seedream", ext: str = "png") -> str:
    """生成带时间戳的文件名"""
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}.{ext}"


def save_result(result: dict, output_dir: Path = OUTPUT_DIR,
                 prefix: str = "seedream") -> List[Path]:
    """
    从 API 响应中提取图片 URL 并下载保存
    同时支持 ArkClient 响应（data[].url）和 JimengV2 响应（data.image_urls / binary_data_base64）

    result: ArkClient / JimengV2Client 返回的 dict
    返回保存路径列表
    """
    import base64 as b64_module
    paths = []
    data = result.get("data", {})

    # 路径A：ArkClient 格式（data 是数组）
    if isinstance(data, list):
        for i, item in enumerate(data):
            url = item.get("url") or item.get("b64_json")
            if url and url.startswith("http"):
                fname = generate_image_name(prefix=f"{prefix}_{i+1:02d}")
                path = download_image(url, output_dir / fname)
            else:
                fname = generate_image_name(prefix=f"{prefix}_{i+1:02d}", ext="png")
                path = output_dir / fname
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b64_module.b64decode(url))
            paths.append(path)
            print(f"  ✅ 保存: {path.name}")

    # 路径B：JimengV2Client 格式（data 是 dict）
    else:
        urls = data.get("image_urls") or []
        b64s = data.get("binary_data_base64") or []
        for i, url in enumerate(urls):
            if url:
                fname = generate_image_name(prefix=f"{prefix}_{i+1:02d}")
                path = download_image(url, output_dir / fname)
                paths.append(path)
                print(f"  ✅ 保存: {path.name}")
        for i, b64 in enumerate(b64s):
            if b64:
                idx = len(urls) + i
                fname = generate_image_name(prefix=f"{prefix}_{idx+1:02d}", ext="png")
                path = output_dir / fname
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b64_module.b64decode(b64))
                paths.append(path)
                print(f"  ✅ 保存: {path.name}")
    return paths


# ─────────────────────────────────────────────
# 业务层：产品图生成（对接你的 AI 工作流）
# ─────────────────────────────────────────────

class ProductImageGenerator:
    """
    Etsy 产品图生成器

    颜色路由逻辑（匹配你的 AI 工作流需求说明）：
      - 黑色 → 即梦4.0 JimengV2Client（CV 视觉服务，实测 yugu 子账户 AK/SK 可用）
      - 其他颜色 → Kolors（硅基流动，单独调用）
    """

    def __init__(self, ark_api_key: str = None,
                 jimeng_ak: str = None, jimeng_sk: str = None):
        self.ark = ArkClient(api_key=ark_api_key) if ark_api_key else None
        self.jimeng = JimengV2Client(ak=jimeng_ak, sk=jimeng_sk)

    def generate_for_product(
        self,
        product_type: str,
        color: str,
        style: str,
        reference_image_url: Optional[str] = None,
        reference_image_b64: Optional[list] = None,
    ) -> List[Path]:
        """
        根据产品类型和颜色生成产品图

        参数:
            product_type: 产品类型，如 "狗牌", "领带夹", "袖扣"
            color:       主色调，如 "黑色", "金色", "银色", "玫瑰金"
            style:       风格描述，如 "宠物头像", "人物头像", "相盒照片"
            reference_image_url: 参考图 URL（可选，二选一）
            reference_image_b64: 参考图 base64 列表（可选，直接传 base64 更方便）
        """
        # ── 构造 prompt ──────────────────────────
        prompt = self._build_prompt(product_type, color, style)
        print(f"\n[ProductImageGenerator] 产品: {product_type} | 颜色: {color} | 风格: {style}")
        print(f"[ProductImageGenerator] Prompt: {prompt[:80]}...")

        # ── 颜色路由：黑色走即梦4.0（CV服务），其他走 Kolors ──
        if color in ("黑色", "black", "Black"):
            print("[ProductImageGenerator] 路由: 即梦4.0 JimengV2Client (CV视觉服务)")
            result = self.jimeng.generate(
                prompt=prompt,
                image_urls=[reference_image_url] if reference_image_url else None,
                binary_data_base64=reference_image_b64,
            )
        else:
            print("[ProductImageGenerator] 路由: Kolors (硅基流动) — 请接入 Kolors API")
            # TODO: 对接 Kolors API
            raise NotImplementedError("Kolors 路由尚未实现，请先接入硅基流动 API")

        return save_result(result)

    def _build_prompt(self, product_type: str, color: str, style: str) -> str:
        """根据产品类型构造英文 prompt"""
        base = f"A high-quality product photo of a {product_type} in {color} color"

        style_map = {
            "宠物头像": "with a cute pet portrait engraving, minimalist style, studio lighting",
            "人物头像": "with a personalized human portrait engraving, elegant style, studio lighting",
            "相盒照片": "with a photo frame locket design, vintage aesthetic, soft lighting",
            "相盒照片(宠物)": "with a pet memorial photo frame design, sentimental style, warm lighting",
        }

        style_suffix = style_map.get(style, style)
        return f"{base}, {style_suffix}, clean white background, professional e-commerce photography, ultra-detailed, 4k"

    def batch_generate(
        self,
        tasks: List[dict],
        delay: int = 2,
    ) -> List[List[Path]]:
        """
        批量生成

        tasks: [{"product_type": "...", "color": "...", "style": "...", "reference_image_url": "..."}, ...]
        """
        results = []
        for i, task in enumerate(tasks):
            print(f"\n[{i+1}/{len(tasks)}] 处理: {task['product_type']}")
            try:
                paths = self.generate_for_product(**task)
                results.append(paths)
            except Exception as e:
                print(f"  ❌ 失败: {e}")
                results.append([])
            if i < len(tasks) - 1:
                time.sleep(delay)
        return results


# ─────────────────────────────────────────────
# 快速测试
# ─────────────────────────────────────────────

def quick_test():
    """即梦4.0（JimengV2）+ Ark Seedream 快速测试"""

    # 测试 JimengV2Client（CV 视觉服务）
    jimeng_ak = os.getenv("JIMENG_AK", "").strip()
    jimeng_sk = os.getenv("JIMENG_SK", "").strip()

    if jimeng_ak and jimeng_sk:
        print("\n=== Test: 即梦4.0 JimengV2Client (CV视觉服务) ===")
        try:
            client = JimengV2Client(ak=jimeng_ak, sk=jimeng_sk)
            task_id = client.submit(
                prompt="A sleek black tie clip on a dark suit lapel, minimalist luxury style, studio lighting, 4k"
            )
            print(f"  task_id: {task_id}")
            result = client.generate(
                prompt="A sleek black tie clip on a dark suit lapel, minimalist luxury style, studio lighting, 4k"
            )
            paths = save_result(result, prefix="jimeng4")
            print(f"  ✅ 成功，保存 {len(paths)} 张图片")
        except Exception as e:
            print(f"  ❌ 失败: {e}")
    else:
        print("⚠️  未设置 JIMENG_AK/JIMENG_SK，跳过 JimengV2Client 测试")

    # 测试 ArkClient（火山方舟 Ark）
    if not ARK_API_KEY:
        print("\n⚠️  未设置 ARK_API_KEY，跳过 ArkClient 测试")
        print("   请设置环境变量: export ARK_API_KEY=你的密钥")
        return

    print("\n=== Test: ArkClient (火山方舟 Ark) ===")
    try:
        client = ArkClient()
        result = client.generate_async(
            prompt="A sleek silver cufflink, minimalist luxury style, studio lighting, 4k",
            model=MODEL_SEEDREAM_4_0,
            size="2K",
        )
        paths = save_result(result, prefix="ark")
        print(f"  ✅ 成功，保存 {len(paths)} 张图片")
    except Exception as e:
        print(f"  ❌ 失败: {e}")

    print("\n✅ 测试完成!")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        quick_test()
    else:
        print(__doc__)
        print("\n用法:")
        print("  python seedream_ark.py --test    # 运行快速测试")
        print("  设置环境变量: export ARK_API_KEY=你的密钥")
