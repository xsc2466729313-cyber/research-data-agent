import pytest
from pathlib import Path

from scripts.export_report_benchmark_summary import build_summary


ROOT = Path(__file__).resolve().parents[2]


def test_frontend_summary_keeps_public_and_agent_comparisons_distinct() -> None:
    retrieval = {
        "aggregate": {
            method: {"ndcg_at_10_macro": score, "recall_at_100_macro": score, "mrr_at_10_macro": score}
            for method, score in {
                "project_bm25_tuned_v2": 0.3,
                "vnext_bge_small_en_v1_5": 0.4,
                "vnext_bm25_bge_fusion_v1": 0.38,
            }.items()
        },
        "results_by_dataset": {
            dataset_id: {
                "project_bm25_tuned_v2": {"query_count": 2, "ndcg_at_10": 0.3},
                "vnext_bge_small_en_v1_5": {"query_count": 2, "ndcg_at_10": 0.4},
            }
            for dataset_id in ("beir_scifact", "beir_nfcorpus", "beir_scidocs", "beir_arguana", "beir_fiqa")
        },
    }
    query_ablation = {
        "macro_average_equal_weight": {
            method: {"ndcg_at_10": 0.3, "recall_at_100": 0.5, "mrr_at_10": 0.3}
            for method in ("A_raw", "C_qwen_single", "D_qwen_multi", "E_rules_qwen")
        },
        "datasets": {"d": {"evaluation_query_count": 5}},
    }
    planner = {
        "metadata": {"protocol": "controlled"},
        "summary": {
            "Qwen 中间智能体": {"cases": 3, "metrics": {"recall@3": 1, "mrr@3": 1, "ndcg@3": 1, "avg_latency_ms": 20}},
            "DeepSeek 替换组": {"cases": 3, "metrics": {"recall@3": 0.6, "mrr@3": 0.6, "ndcg@3": 0.6, "avg_latency_ms": 10}},
        },
    }
    loop = {
        "completed_iterations": 2,
        "iterations": [
            {"metrics": {"progress_score": 0.8}, "result": {"model_name": "qwen"}},
            {"metrics": {"progress_score": 0.9}, "result": {"model_name": "qwen"}},
        ],
    }
    summary = build_summary(retrieval, query_ablation, planner, loop)
    assert summary["retrieval"]["query_count"] == 10
    assert summary["retrieval"]["strata"][0]["delta_ndcg_at_10"] == pytest.approx(0.1)
    assert summary["model_comparison"]["qwen"]["recall_at_3"] == 1
    assert summary["closed_loop"]["score_delta"] == pytest.approx(0.1)


def test_benchmark_results_live_in_reports_not_the_user_frontend() -> None:
    frontend = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    report = (ROOT / "docs" / "多癌种精准治疗科研数据智能整合系统_专业叙事与规范图示终稿_20260904.md").read_text(encoding="utf-8")

    assert "public-benchmark" not in frontend
    assert "public-benchmark-summary.json" not in script
    assert "3,677" in report
    assert "千问 3.8-Max" in report
    assert "DeepSeek" in report
    assert "前三条命中率" in report
    assert "Qwen-plus" not in report
    assert "3,029" not in report
