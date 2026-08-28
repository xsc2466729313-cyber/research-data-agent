"""Retired compatibility entry point for the former AI proxy metric builder.

The previous implementation converted a model judge score into Faithfulness,
Traceability, Repair Accuracy and SDTI proxies. Those values do not follow the
frozen Gold Set definitions and must not be regenerated as project results.
"""

from __future__ import annotations


def main() -> int:
    raise SystemExit(
        "该脚本已停用：AI 评审分不能换算为正式 Faithfulness、Traceability、"
        "Repair Accuracy 或 SDTI。请使用冻结 Gold Set 和 scripts/run_qwen_review_evaluation.py；"
        "Qwen 评审结果仅作辅助诊断。"
    )


if __name__ == "__main__":
    raise SystemExit(main())
