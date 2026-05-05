"""腾讯云部署/调试脚本共用的密钥读取（禁止在仓库中硬编码 Secret）。"""
from __future__ import annotations

import os


def get_tencent_secret_pair() -> tuple[str, str]:
    """
    返回 (SecretId, SecretKey)。优先读标准环境变量，便于本地与 CI。
    """
    sid = (
        os.environ.get("TENCENTCLOUD_SECRET_ID")
        or os.environ.get("TENCENT_SECRET_ID")
        or os.environ.get("COS_SECRET_ID")
        or ""
    ).strip()
    sk = (
        os.environ.get("TENCENTCLOUD_SECRET_KEY")
        or os.environ.get("TENCENT_SECRET_KEY")
        or os.environ.get("COS_SECRET_KEY")
        or ""
    ).strip()
    if not sid or not sk:
        raise RuntimeError(
            "缺少腾讯云密钥：请设置环境变量 "
            "TENCENTCLOUD_SECRET_ID 与 TENCENTCLOUD_SECRET_KEY "
            "（或 TENCENT_SECRET_ID / TENCENT_SECRET_KEY；COS 脚本亦可用 COS_SECRET_ID / COS_SECRET_KEY）"
        )
    return sid, sk
