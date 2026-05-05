#!/bin/bash
# ─────────────────────────────────────────────
# Google Drive OAuth 授权启动器
# ─────────────────────────────────────────────

cd "$(dirname "$0")"

# 检查是否需要安装 requests（仅用于其他脚本，本授权脚本不需要）
python3 -c "import requests" 2>/dev/null
if [ $? -ne 0 ]; then
    echo ""
    echo "⚠️  注意：检测到缺少 requests 库"
    echo "   本授权脚本无需安装（已使用标准库实现）"
    echo "   其他脚本（如 gdrive_client.py）才需要 requests"
    echo ""
fi

echo "=================================================="
echo "  Google Drive OAuth 授权"
echo "=================================================="
echo ""

python3 get_refresh_token.py

echo ""
echo "按 Enter 退出..."
read -r dummy
