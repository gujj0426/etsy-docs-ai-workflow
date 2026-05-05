#!/usr/bin/env bash
# 首次登录 GitHub CLI 后，一键创建远端仓库并推送当前分支。
# 用法：
#   ./scripts/gh_first_push.sh                  # 默认仓库名 etsy-docs-ai-workflow（公开）
#   ./scripts/gh_first_push.sh my-repo-name     # 自定义仓库名
#   GITHUB_REPO_VISIBILITY=private ./scripts/gh_first_push.sh my-private-repo

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REPO_NAME="${1:-etsy-docs-ai-workflow}"
VIS="${GITHUB_REPO_VISIBILITY:-public}"
if [[ "$VIS" != "public" && "$VIS" != "private" ]]; then
  echo "GITHUB_REPO_VISIBILITY 只能是 public 或 private"
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "未找到 gh，请先安装：brew install gh"
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "========================================"
  echo "尚未登录 GitHub。请在打开的浏览器中完成授权。"
  echo "========================================"
  gh auth login --web --hostname github.com --git-protocol https --skip-ssh-key
fi

if git remote get-url origin >/dev/null 2>&1; then
  echo "已存在 remote origin，直接推送..."
  git push -u origin main
else
  echo "创建远端仓库 ${REPO_NAME} (${VIS}) 并推送..."
  gh repo create "$REPO_NAME" "--${VIS}" --source=. --remote=origin --push
fi

echo "完成：$(git remote get-url origin)"
