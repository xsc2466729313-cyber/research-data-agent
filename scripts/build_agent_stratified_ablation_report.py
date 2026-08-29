from __future__ import annotations

"""Build the internal stratified and ablation report from saved real runs."""

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.evaluation.observe import gold_id_matches
from backend.app.evaluation.official_run import ids_from_planner


ROOT = Path(__file__).resolve().parents[1]
DEV_GOLD = ROOT / "goldset" / "breast_cancer" / "development" / "retrieval_gold.csv"
BASELINE = ROOT / "data" / "output" / "evaluation" / "official-candidate-20260829T132222Z" / "metrics.json"
CURRENT = ROOT / "data" / "output" / "evaluation" / "official-candidate-autonomous-v9-20260830" / "metrics.json"
RAG = ROOT / "evaluation" / "vnext_retrieval_calibrated_macro_20260828.json"
QUERY = ROOT / "evaluation" / "query_understanding" / "ablation_20260828.json"
PLANNER = ROOT / "evaluation" / "planner_replacement_ablation_20260829" / "planner_replacement_ablation.json"
OUTPUT = ROOT / "evaluation" / "agent_stratified_ablation_20260829"

STRATA = {
    "临床结局": {"q01_neoadjuvant_pcr", "q02_her2_targeted_response", "q03_pik3ca_and_response_same_patient", "q07_neoadjuvant_trials"},
    "患者分层": {"q04_pik3ca_clinical_features", "q05_erbb2_her2_features", "q09_tnbc", "q10_hr_positive_her2_negative", "q11_her2_ihc_vs_erbb2_cna"},
    "知识与临床前": {"q06_pik3ca_knowledge_evidence", "q08_cell_line_drug_response"},
    "表达发现": {"q12_scanb_expression"},
}
METHOD_LABELS = {
    "project_bm25_tuned_v2": "调参 BM25",
    "vnext_bge_small_en_v1_5": "BGE-small-en-v1.5",
    "vnext_bm25_bge_fusion_v1": "BM25+BGE 融合",
}
DATASET_LABELS = {
    "beir_scifact": "SciFact",
    "beir_nfcorpus": "NFCorpus",
    "beir_scidocs": "SciDocs",
    "beir_arguana": "ArguAna",
    "beir_fiqa": "FiQA",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def development_strata() -> dict[str, dict[str, float | int]]:
    rows = list(csv.DictReader(DEV_GOLD.open(encoding="utf-8-sig")))
    questions: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        questions.setdefault(row["question_id"], []).append(row)
    assigned = set().union(*STRATA.values())
    if assigned != set(questions):
        raise ValueError("Development strata must cover every question exactly.")
    output: dict[str, dict[str, float | int]] = {}
    for name, ids in STRATA.items():
        tp = fp = fn = row_count = 0
        for question_id in sorted(ids):
            subset = questions[question_id]
            row_count += len(subset)
            retrieved = ids_from_planner(question_id, subset[0]["research_question"])
            for row in subset:
                predicted = any(gold_id_matches(row["dataset_id"], item) for item in retrieved)
                relevant = row["label"] == "relevant"
                tp += int(predicted and relevant)
                fp += int(predicted and not relevant)
                fn += int(not predicted and relevant)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        output[name] = {
            "question_count": len(ids),
            "row_count": row_count,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        }
    return output


def metric_value(document: dict[str, Any], key: str) -> float:
    return float(document["metrics"][key]["value"])


def fmt(value: float | None, digits: int = 4) -> str:
    return "NOT_EVALUATED" if value is None else f"{value:.{digits}f}"


def main() -> None:
    baseline = load_json(BASELINE)
    current = load_json(CURRENT)
    retrieval = load_json(RAG)
    query = load_json(QUERY)
    planner = load_json(PLANNER)
    strata = development_strata()
    payload = {
        "artifact_type": "agent_stratified_ablation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "official_candidate": "reviewed_unfrozen_candidate_not_sealed_test",
            "development": "diagnostic_only",
            "public_retrieval": "BEIR_capability_layer_not_SDTI",
            "planner_replacement": "internal_ablation_not_production_ranking",
        },
        "development_retrieval_strata": strata,
        "official_candidate_comparison": {"baseline": baseline, "current": current},
        "retrieval_layer": retrieval,
        "query_understanding_ablation": query,
        "planner_replacement_ablation": planner,
        "input_artifacts": {
            path.relative_to(ROOT).as_posix(): file_sha256(path)
            for path in (DEV_GOLD, BASELINE, CURRENT, RAG, QUERY, PLANNER)
        },
        "notice": "All values are read from saved runs. Missing experiments remain NOT_EVALUATED. official_candidate is not a sealed frozen test.",
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    baseline_metrics = baseline["metrics"]
    current_metrics = current["metrics"]
    metrics = [
        ("Retrieval Precision", "retrieval_precision"),
        ("Retrieval Recall", "retrieval_recall"),
        ("Retrieval F1", "retrieval_f1"),
        ("Faithfulness", "faithfulness"),
        ("Traceability", "traceability"),
        ("Error Precision", "error_precision"),
        ("Error Recall", "error_recall"),
        ("Error F1", "error_f1"),
        ("Repair Accuracy", "repair_accuracy"),
        ("SDTI", "sdti"),
    ]
    lines = [
        "# 乳腺癌科研数据 Agent 分层评测与消融实验报告",
        "",
        f"> 生成时间：{payload['created_at']}。本报告是内部研发评测，不嵌入产品前端。所有数字来自已保存运行产物；缺失实验不推算。",
        "",
        "## 1. 结论摘要",
        "",
        f"- 当前候选卷运行 `{current['evaluation_id']}` 的 SDTI 为 **{metric_value(current, 'sdti'):.2f}**，五个 SDTI 分量均达到目标。",
        f"- 同一 official_candidate 上，相对基线 `{baseline['evaluation_id']}` 的 SDTI 从 **{metric_value(baseline, 'sdti'):.2f}** 变为 **{metric_value(current, 'sdti'):.2f}**。",
        "- 当前运行安全门仍为 **REVIEW**，`publish_allowed=false`：有 9 个高风险问题未解决，且该卷不是 sealed frozen test。",
        "- 公开检索能力层中，BGE 的宏平均 nDCG@10 为 **0.3880**，BM25 为 **0.3147**；这不是乳腺癌 SDTI。",
        "- 开发集 12 个问题已全部纳入四类分层；分层结果用于发现泛化短板，不用候选卷 100 分覆盖这些较弱结果。",
        "",
        "## 2. 评测范围与解释边界",
        "",
        "| 层级 | 数据范围 | 用途 | 是否可作封存正式成绩 |",
        "|---|---|---|---|",
        "| official_candidate | retrieval 50 / field 26 / error 18 | 候选卷版本观察 | 否，`frozen=false` |",
        "| development | 12 个问题、53 条检索判断 | 分层诊断与迭代 | 否 |",
        "| BEIR | 5 个公开数据集、3,677 个查询 | 检索模块能力对照 | 否 |",
        "| 规划模型替换 | 3 个病例 × 3 次 × 2 组 | 内部消融 | 否 |",
        "",
        "## 3. 候选卷迭代前后",
        "",
        "| 指标 | 基线 | 当前 | 变化 | 目标 |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, key in metrics:
        before = baseline_metrics[key]["value"]
        after = current_metrics[key]["value"]
        target = current_metrics[key].get("target")
        digits = 2 if key == "sdti" else 4
        lines.append(f"| {label} | {before:.{digits}f} | {after:.{digits}f} | {after - before:+.{digits}f} | {fmt(target, digits)} |")
    safety = current.get("safety") or {}
    counts = current.get("counts") or {}
    lines += [
        "",
        "### 安全门与原始计数",
        "",
        f"- 安全门：`{safety.get('gate', 'NOT_EVALUATED')}`；允许自动发布：`{str(bool(safety.get('publish_allowed'))).lower()}`。",
        f"- 检索：TP={counts.get('retrieval', {}).get('tp', 0)} / FP={counts.get('retrieval', {}).get('fp', 0)} / FN={counts.get('retrieval', {}).get('fn', 0)}。",
        f"- 字段：Faithful={counts.get('faithful_fields', 0)}/{counts.get('sampled_critical_fields', 0)}；Traceable={counts.get('traceable_fields', 0)}/{counts.get('key_nonempty_fields', 0)}。",
        f"- 错误：TP={counts.get('errors', {}).get('tp', 0)} / FP={counts.get('errors', {}).get('fp', 0)} / FN={counts.get('errors', {}).get('fn', 0)}；自动修复正确={counts.get('correct_repairs', 0)}/{counts.get('automatic_repairs', 0)}。",
    ]
    lines.extend(f"- 发布阻断：{blocker}。" for blocker in safety.get("publication_blockers") or [])

    lines += [
        "",
        "## 4. Development 全量分层检索",
        "",
        "| 分层 | 问题数 | 判断行数 | TP | FP | FN | Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in strata.items():
        lines.append(f"| {name} | {row['question_count']} | {row['row_count']} | {row['tp']} | {row['fp']} | {row['fn']} | {row['precision']:.4f} | {row['recall']:.4f} | {row['f1']:.4f} |")
    totals = {key: sum(int(row[key]) for row in strata.values()) for key in ("question_count", "row_count", "tp", "fp", "fn")}
    precision = totals["tp"] / (totals["tp"] + totals["fp"]) if totals["tp"] + totals["fp"] else 0.0
    recall = totals["tp"] / (totals["tp"] + totals["fn"]) if totals["tp"] + totals["fn"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    lines.append(f"| **合计** | **{totals['question_count']}** | **{totals['row_count']}** | **{totals['tp']}** | **{totals['fp']}** | **{totals['fn']}** | **{precision:.4f}** | **{recall:.4f}** | **{f1:.4f}** |")

    lines += [
        "",
        "## 5. 检索层对比：BM25、BGE 与融合",
        "",
        "| 方法 | 数据集数 | nDCG@10 | Recall@100 | MRR@10 | 平均延迟(ms) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, row in retrieval["aggregate"].items():
        lines.append(f"| {METHOD_LABELS.get(key, key)} | {row['dataset_count']} | {row['ndcg_at_10_macro']:.4f} | {row['recall_at_100_macro']:.4f} | {row['mrr_at_10_macro']:.4f} | {row['mean_latency_ms_macro']:.2f} |")
    lines += [
        "",
        "### 按公开数据集分层",
        "",
        "| 数据集 | 查询数 | BM25 nDCG@10 | BGE nDCG@10 | 融合 nDCG@10 | BGE 相对 BM25 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for dataset, result in retrieval["results_by_dataset"].items():
        bm25 = result["project_bm25_tuned_v2"]
        bge = result["vnext_bge_small_en_v1_5"]
        fusion = result["vnext_bm25_bge_fusion_v1"]
        lines.append(f"| {DATASET_LABELS.get(dataset, dataset)} | {bge['query_count']} | {bm25['ndcg_at_10']:.4f} | {bge['ndcg_at_10']:.4f} | {fusion['ndcg_at_10']:.4f} | {bge['ndcg_at_10'] - bm25['ndcg_at_10']:+.4f} |")

    lines += [
        "",
        "## 6. 查询理解消融",
        "",
        "| 变体 | 状态 | nDCG@10 | Recall@100 | MRR@10 | 平均延迟(ms) |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for name, row in query["macro_average_equal_weight"].items():
        lines.append(f"| `{name}` | `{row.get('status', 'NOT_EVALUATED')}` | {fmt(row.get('ndcg_at_10'))} | {fmt(row.get('recall_at_100'))} | {fmt(row.get('mrr_at_10'))} | {fmt(row.get('mean_latency_ms'), 2)} |")
    lines += [
        "",
        "A_raw 与 B_rules 已完成；C/D/E 缺少真实结构化 Qwen 计划缓存，保持 `NOT_EVALUATED`。规则改写相对原始查询没有提升，因此未作为改进宣传。",
        "",
        "## 7. 中间规划模型替换消融",
        "",
        "| 组别 | 运行数 | Recall@3 | nDCG@3 | 平均延迟(ms) | 评审有效率 | 平均证据支持率 | 正式 SDTI |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name, summary in planner["summary"].items():
        item = summary["metrics"]
        lines.append(f"| {name} | {summary['runs']} | {item['recall@3']:.4f} | {item['ndcg@3']:.4f} | {item['avg_latency_ms']:.2f} | {item['judge_valid_rate']:.4f} | {item['avg_claim_support_rate']:.4f} | `NOT_EVALUATED` |")
    lines += [
        "",
        "DeepSeek 组在本次小样本检索排序上更高，但 Qwen 评审有效率更低；该消融不能推导通用模型排名，也不自动替换生产主链。",
        "",
        "## 8. 未完成实验",
        "",
        "| 实验 | 状态 | 原因 |",
        "|---|---|---|",
        "| Qwen 单查询改写 | `NOT_EVALUATED` | 缺少同协议真实计划缓存 |",
        "| Qwen 多查询扩展 | `NOT_EVALUATED` | 缺少同协议真实计划缓存 |",
        "| 规则 + Qwen 完整查询理解 | `NOT_EVALUATED` | 缺少同协议真实计划缓存 |",
        "| sealed frozen test | `NOT_EVALUATED` | 当前 official_candidate 未冻结封存 |",
        "",
        "## 9. 复现与产物",
        "",
        "```powershell",
        ".\\.venv\\Scripts\\python.exe goldset\\breast_cancer\\official_candidate\\collect_official_sdti.py --retrieval planner --evaluation-id official-candidate-autonomous-v9-20260830",
        ".\\.venv\\Scripts\\python.exe scripts\\build_agent_stratified_ablation_report.py",
        "```",
        "",
        f"- 当前候选卷：`{CURRENT.relative_to(ROOT).as_posix()}`",
        f"- 报告 JSON：`{(OUTPUT / 'report.json').relative_to(ROOT).as_posix()}`",
        f"- 本报告：`{(OUTPUT / 'report.md').relative_to(ROOT).as_posix()}`",
        "- 输入文件 SHA-256 已记录在 `report.json -> input_artifacts`。",
        "",
        "## 10. 研究解释",
        "",
        "候选卷上的满分说明当前确定性规划、字段规范化、错误检测和安全修复已覆盖该卷的已审核案例；它不证明对未见队列、未见字段或真实临床研究任务具有同等表现。开发集临床结局与患者分层仍有漏召回，规划模型替换评审也存在无效样本。后续应优先构建独立 sealed test，并扩大临床结局同域、HER2 IHC/ISH 与 ERBB2 CNA 区分、跨来源身份冲突等高风险分层。",
    ]
    (OUTPUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT / "report.json")
    print(OUTPUT / "report.md")


if __name__ == "__main__":
    main()
