#!/usr/bin/env python3
"""
腾讯文档 workFlowTest 全流程联调：
  下载「客户原图」→ 即梦图生图 → 上传资源 → 回写「AI生成粗略图」

默认行为与生产 main() 一致（按出库日期/设计风格/幂等筛选）。
指定 --record-id 可测单行（无视日期筛选）；--force 可在已有 AI 图时强制覆盖。

示例：
  python3 test_tdocs_jimeng_e2e.py --list
  python3 test_tdocs_jimeng_e2e.py
  python3 test_tdocs_jimeng_e2e.py --record-id rxxxx --force
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="腾讯表格 + 即梦 + 回写 全流程测试",
    )
    ap.add_argument(
        "--list",
        action="store_true",
        help="仅列出当前（生产规则下）会触发的行，不执行生图",
    )
    ap.add_argument(
        "--record-id",
        metavar="ID",
        help="只处理该 recordID（不校验出库日期；需有客户原图；默认仍要求 AI 列为空，除非 --force）",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="忽略「AI生成粗略图」是否已有值（联调覆盖用）",
    )
    args = ap.parse_args()

    # 在 import 前可改环境变量；此处直接 import 会加载 scf_pipeline 及 token
    import scf_pipeline as sp

    if args.list:
        sp._log.info("=" * 60)
        sp._log.info("仅列表：fetch_trigger_records() 结果")
        sp._log.info("=" * 60)
        try:
            rows = sp.fetch_trigger_records()
        except Exception as e:
            sp._log.error(f"读取失败：{e}")
            return 1
        sp._log.info(f"共 {len(rows)} 条将触发")
        for r in rows:
            sp._log.info(
                f"  {r['record_id']} | 订单 {r['order_no']} | "
                f"{r['style']} | {r['color']} | 出库 {r['outdate']}"
            )
        return 0

    if args.record_id:
        sp._log.info("=" * 60)
        sp._log.info(f"单条联调 record_id={args.record_id} force={args.force}")
        sp._log.info("=" * 60)
        try:
            rec = sp.fetch_pipeline_record_by_id(args.record_id, force=args.force)
        except Exception as e:
            sp._log.error(f"{e}")
            return 2
        sp.process_pipeline_records([rec])
        return 0

    sp.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
