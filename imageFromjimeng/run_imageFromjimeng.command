#!/bin/bash
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR" || exit 1

if [ ! -f "config.json" ]; then
  if [ ! -f "config.example.json" ]; then
    echo "缺少 config.example.json"
    read -r -p "按回车退出..." _
    exit 1
  fi
  cp config.example.json config.json
  echo "已生成 config.json 模板，请填写 jimeng_ak / jimeng_sk（可按需改 prompts）后重新双击运行。"
  echo "路径: $ROOT_DIR/config.json"
  read -r -p "按回车退出..." _
  exit 1
fi

EXITCODE=0
if command -v python3 >/dev/null 2>&1; then
  python3 "$ROOT_DIR/process_images.py" || EXITCODE=$?
else
  echo "未找到 python3，请先安装 Python 3"
  EXITCODE=1
fi

if [ "$EXITCODE" -ne 0 ]; then
  echo ""
  echo "[提示] 程序异常结束，退出码: $EXITCODE（请向上翻看日志）"
fi
echo ""
read -r -p "任务结束，按回车关闭窗口..." _
exit "$EXITCODE"
