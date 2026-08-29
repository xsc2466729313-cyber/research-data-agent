from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.evaluation.public_cleaning import (  # noqa: E402
    CLEANING_DATASETS,
    _project_consensus_repair,
    _project_format_profile_repair,
    evaluate_cleaning,
    load_cleaning_dataset,
    prepare_cleaning_dataset,
)
from backend.app.evaluation.public_entity import (  # noqa: E402
    ENTITY_DATASETS,
    _entity_data_dir,
    evaluate_entity_pairs,
    fit_entity_rule,
    fit_entity_v3_threshold,
    load_entity_pairs,
    prepare_entity_dataset,
)
from backend.app.evaluation.public_schema import (  # noqa: E402
    SCHEMA_DATASETS,
    evaluate_schema_matches,
    load_schema_task,
    prepare_schema_dataset,
)


REPOSITORIES = {
    "beir": {
        "url": "https://github.com/beir-cellar/beir",
        "revision": "ef83d29307061c65d04b035b4f4e7c18bd8374af",
    },
    "flag_embedding": {
        "url": "https://github.com/FlagOpen/FlagEmbedding",
        "model": "BAAI/bge-small-en-v1.5",
    },
    "valentine": {
        "url": "https://github.com/delftdata/valentine",
        "version": "1.0.0",
        "revision": "f0f738927455063841a4ebdda2f1420abc26922b",
    },
    "recordlinkage": {
        "url": "https://github.com/J535D165/recordlinkage",
        "version": "0.16",
        "revision": "b93d97641952f8c85106be5794ca93b1f1298fbc",
    },
    "raha": {
        "url": "https://github.com/BigDaMa/raha",
        "version": "1.26",
        "revision": "43a9417de5fc6ae87900b901c8846a97fc17c274",
    },
    "deepmatcher": {
        "url": "https://github.com/anhaidgroup/deepmatcher",
        "revision": "a89ffe6cd246f690afd2772e47eb071741160f16",
        "status": "NOT_EVALUATED",
        "reason": "官方依赖旧 torchtext/fasttext，与当前 Python 3.14 环境不兼容。",
    },
    "ditto": {
        "url": "https://github.com/megagonlabs/ditto",
        "revision": "52985564a93fb11308439516d3e17a033d43ec8f",
        "status": "NOT_EVALUATED",
        "reason": "官方环境固定 torch 1.9/transformers 4.9，未在当前 CPU 环境强行改写训练代码。",
    },
    "holoclean": {
        "url": "https://github.com/HoloClean/holoclean",
        "status": "NOT_EVALUATED",
        "reason": "需要 PostgreSQL 与独立服务环境，本轮只使用其公开 Hospital 数据。",
    },
}


def _git_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def _metrics(labels: Sequence[int], predictions: Sequence[int]) -> dict[str, float | int]:
    tp = sum(label == 1 and prediction == 1 for label, prediction in zip(labels, predictions))
    fp = sum(label == 0 and prediction == 1 for label, prediction in zip(labels, predictions))
    fn = sum(label == 1 and prediction == 0 for label, prediction in zip(labels, predictions))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "n": len(labels),
    }


def _schema_metrics(
    predicted: set[tuple[str, str]], gold: set[tuple[str, str]]
) -> dict[str, float | int]:
    labels = [1] * len(gold) + [0] * len(predicted - gold)
    predictions = [int(pair in predicted) for pair in gold] + [1] * len(predicted - gold)
    result = _metrics(labels, predictions)
    result["predicted_count"] = len(predicted)
    result["gold_count"] = len(gold)
    return result


def _macro(rows: Iterable[dict[str, Any]], metric: str) -> float | None:
    values = [float(row[metric]) for row in rows if row.get("status") == "OK" and row.get(metric) is not None]
    return sum(values) / len(values) if values else None


def _paired_macros(
    rows: Iterable[dict[str, Any]], project_metric: str, github_metric: str
) -> tuple[float | None, float | None, int]:
    paired = [
        row
        for row in rows
        if row.get("status") == "OK"
        and row.get(project_metric) is not None
        and row.get(github_metric) is not None
    ]
    project = sum(float(row[project_metric]) for row in paired) / len(paired) if paired else None
    github = sum(float(row[github_metric]) for row in paired) / len(paired) if paired else None
    return project, github, len(paired)


def _load_external_packages(package_dir: Path | None) -> None:
    if package_dir and str(package_dir) not in sys.path:
        sys.path.insert(0, str(package_dir))


def collect_retrieval_results() -> dict[str, Any]:
    run_root = PROJECT_ROOT / "evaluation" / "public_benchmarks" / "runs"
    dataset_ids = ["beir_scifact", "beir_nfcorpus", "beir_scidocs", "beir_arguana", "beir_fiqa"]
    rows: list[dict[str, Any]] = []
    required = ("project_bm25_tuned_v2", "vnext_bge_small_en_v1_5", "vnext_bm25_bge_fusion_v1")
    for dataset_id in dataset_ids:
        candidates: list[tuple[str, Path, dict[str, Any]]] = []
        for path in run_root.glob(f"*_{dataset_id}/run.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            candidates.append((payload.get("created_at", ""), path, payload))
        selected: dict[str, tuple[Path, dict[str, Any], dict[str, Any]]] = {}
        for method in required:
            matching = [item for item in candidates if method in item[2].get("results", {})]
            if matching:
                _, path, payload = max(matching, key=lambda item: (item[0], str(item[1])))
                selected[method] = (path, payload, payload["results"][method])
        if len(selected) != len(required):
            missing = ", ".join(method for method in required if method not in selected)
            rows.append({"dataset": dataset_id, "status": "NOT_EVALUATED", "reason": f"缺少本机运行方法：{missing}。"})
            continue
        hashes = {item[1]["dataset"]["qrels_test_sha256"] for item in selected.values()}
        if len(hashes) != 1:
            rows.append({"dataset": dataset_id, "status": "NOT_EVALUATED", "reason": "各方法使用的测试 qrels 哈希不一致。"})
            continue
        bm25_path, bm25_payload, bm25 = selected["project_bm25_tuned_v2"]
        bge_path, _, bge = selected["vnext_bge_small_en_v1_5"]
        hybrid_path, _, hybrid = selected["vnext_bm25_bge_fusion_v1"]
        rows.append({
            "dataset": dataset_id,
            "status": "OK",
            "query_count": bge["query_count"],
            "project_method": "BM25 + BGE fusion",
            "project_ndcg_at_10": hybrid["ndcg_at_10"],
            "github_method": "BGE-small-en-v1.5",
            "github_ndcg_at_10": bge["ndcg_at_10"],
            "bm25_ndcg_at_10": bm25["ndcg_at_10"],
            "source_id": bm25_payload["dataset"]["source_id"],
            "source_url": bm25_payload["dataset"]["source_url"],
            "qrels_sha256": bm25_payload["dataset"]["qrels_test_sha256"],
            "run_files": sorted({
                str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
                for path in (bm25_path, bge_path, hybrid_path)
            }),
        })
    return {
        "metric": "nDCG@10",
        "rows": rows,
        "project_macro": _macro(rows, "project_ndcg_at_10"),
        "github_macro": _macro(rows, "github_ndcg_at_10"),
        "bm25_macro": _macro(rows, "bm25_ndcg_at_10"),
    }


def run_schema_results(data_root: Path) -> dict[str, Any]:
    import pandas as pd
    from valentine import valentine_match
    from valentine.algorithms import (
        Coma,
        Cupid,
        DistributionBased,
        JaccardDistanceMatcher,
        SimilarityFlooding,
    )

    external_matchers = {
        "Valentine COMA": lambda: Coma(use_instances=True),
        "Valentine Cupid": Cupid,
        "Valentine DistributionBased": DistributionBased,
        "Valentine Jaccard": JaccardDistanceMatcher,
        "Valentine SimilarityFlooding": SimilarityFlooding,
    }
    rows: list[dict[str, Any]] = []
    for dataset_id in sorted(SCHEMA_DATASETS):
        dataset_dir, manifest = prepare_schema_dataset(dataset_id, data_root, download=False)
        source, target, gold, source_samples, target_samples = load_schema_task(dataset_dir)
        project = evaluate_schema_matches(
            source,
            target,
            gold,
            "project_schema_v3",
            source_samples=source_samples,
            target_samples=target_samples,
        )
        left = pd.read_csv(dataset_dir / "source_table.csv", dtype=str, keep_default_na=False)
        right = pd.read_csv(dataset_dir / "target_table.csv", dtype=str, keep_default_na=False)
        methods: dict[str, Any] = {}
        for label, factory in external_matchers.items():
            started = time.perf_counter()
            try:
                matches = valentine_match([left, right], factory())
                selected = matches.one_to_one_hungarian()
                predicted = {(pair.source_column, pair.target_column) for pair in selected}
                methods[label] = {
                    "status": "OK",
                    **_schema_metrics(predicted, gold),
                    "runtime_seconds": time.perf_counter() - started,
                }
            except Exception as exc:  # external methods fail independently
                methods[label] = {"status": "NOT_EVALUATED", "reason": f"{type(exc).__name__}: {exc}"}
        completed = [(name, result) for name, result in methods.items() if result["status"] == "OK"]
        best_name, best = max(completed, key=lambda item: item[1]["f1"]) if completed else ("无", {"f1": None})
        coma = methods["Valentine COMA"]
        rows.append({
            "dataset": dataset_id,
            "status": "OK",
            "gold_count": len(gold),
            "project_method": "Project Schema Matcher V3",
            "project_f1": project.f1,
            "project_metrics": asdict(project),
            "github_method": "Valentine COMA",
            "github_f1": coma.get("f1"),
            "best_github_method": best_name,
            "best_github_f1": best["f1"],
            "github_methods": methods,
            "source_id": manifest["source_id"],
            "source_url": manifest["source_url"],
            "ground_truth_sha256": manifest["ground_truth_sha256"],
        })
    return {
        "metric": "Schema F1",
        "rows": rows,
        "project_macro": _macro(rows, "project_f1"),
        "github_macro": _macro(rows, "github_f1"),
    }


def _recordlinkage_features(pairs: Sequence[tuple[dict[str, str], dict[str, str], int]]):
    import pandas as pd
    import recordlinkage

    left_rows = [left for left, _, _ in pairs]
    right_rows = [right for _, right, _ in pairs]
    left_frame = pd.DataFrame(left_rows).fillna("").astype(str)
    right_frame = pd.DataFrame(right_rows).fillna("").astype(str)
    indices = list(range(len(pairs)))
    pair_index = pd.MultiIndex.from_arrays([indices, indices])
    common_fields = sorted((set(left_frame.columns) & set(right_frame.columns)) - {"id"})
    compare = recordlinkage.Compare()
    for field in common_fields:
        compare.string(field, field, method="jarowinkler", missing_value=0.0, label=f"jw:{field}")
        compare.exact(field, field, missing_value=0.0, label=f"exact:{field}")
    if not common_fields:
        raise ValueError("No comparable fields in entity dataset")
    return compare.compute(pair_index, left_frame, right_frame)


def _fit_recordlinkage(
    train_pairs: Sequence[tuple[dict[str, str], dict[str, str], int]],
    valid_pairs: Sequence[tuple[dict[str, str], dict[str, str], int]],
):
    from sklearn.linear_model import LogisticRegression

    train_x = _recordlinkage_features(train_pairs)
    train_y = [label for _, _, label in train_pairs]
    valid_x = _recordlinkage_features(valid_pairs)
    valid_y = [label for _, _, label in valid_pairs]
    model = LogisticRegression(class_weight="balanced", max_iter=2000, random_state=0)
    model.fit(train_x, train_y)
    probabilities = model.predict_proba(valid_x)[:, 1]
    best: tuple[float, float, float] | None = None
    for index in range(5, 96):
        threshold = index / 100
        score = _metrics(valid_y, [int(value >= threshold) for value in probabilities])
        candidate = (float(score["f1"]), float(score["precision"]), threshold)
        if best is None or candidate > best:
            best = candidate
    assert best is not None
    return model, best[2]


def run_entity_results(data_root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for dataset_id in sorted(ENTITY_DATASETS):
        dataset_dir, manifest = prepare_entity_dataset(dataset_id, data_root, download=False)
        train_pairs, train_info = load_entity_pairs(dataset_dir, "train")
        valid_pairs, valid_info = load_entity_pairs(dataset_dir, "valid")
        test_pairs, test_info = load_entity_pairs(dataset_dir, "test")
        project_config = fit_entity_v3_threshold(train_pairs, valid_pairs)
        project = evaluate_entity_pairs(test_pairs, "project_entity_v3", rule_config=project_config)
        project_v2_config = fit_entity_rule(train_pairs, valid_pairs)
        project_v2 = evaluate_entity_pairs(test_pairs, "project_learned_entity_v2", rule_config=project_v2_config)
        started = time.perf_counter()
        try:
            model, threshold = _fit_recordlinkage(train_pairs, valid_pairs)
            test_x = _recordlinkage_features(test_pairs)
            labels = [label for _, _, label in test_pairs]
            predictions = [int(value >= threshold) for value in model.predict_proba(test_x)[:, 1]]
            external = {
                "status": "OK",
                **_metrics(labels, predictions),
                "threshold": threshold,
                "runtime_seconds": time.perf_counter() - started,
            }
        except Exception as exc:
            external = {"status": "NOT_EVALUATED", "reason": f"{type(exc).__name__}: {exc}"}
        rows.append({
            "dataset": dataset_id,
            "status": "OK",
            "project_method": "Project Entity Matcher V3",
            "project_f1": project.f1,
            "project_metrics": asdict(project),
            "project_v2_f1": project_v2.f1,
            "github_method": "RecordLinkage Jaro-Winkler + logistic",
            "github_f1": external.get("f1"),
            "github_metrics": external,
            "splits": {"train": train_info, "valid": valid_info, "test": test_info},
            "source_id": manifest["source_id"],
            "source_url": manifest["source_url"],
            "test_sha256": manifest["test_sha256"],
        })
    return {
        "metric": "Entity F1",
        "rows": rows,
        "project_macro": _macro(rows, "project_f1"),
        "github_macro": _macro(rows, "github_f1"),
    }


def _cell_detection_metrics(
    dirty: list[dict[str, str]], clean: list[dict[str, str]], repaired: list[dict[str, str]]
) -> dict[str, float | int]:
    columns = list(dirty[0])
    gold = {(row_index, column) for row_index, (before, after) in enumerate(zip(dirty, clean)) for column in columns if before[column] != after[column]}
    predicted = {(row_index, column) for row_index, (before, after) in enumerate(zip(dirty, repaired)) for column in columns if before[column] != after[column]}
    correct_repairs = sum(repaired[row][column] == clean[row][column] for row, column in predicted)
    result = _schema_metrics(predicted, gold)
    result["repair_accuracy"] = correct_repairs / len(predicted) if predicted else 0.0
    result["dirty_cell_count"] = len(gold)
    return result


class _SerialPool:
    def map(self, function, values):
        return list(map(function, values))

    def close(self) -> None:
        return None

    def join(self) -> None:
        return None


def _run_raha(
    dataset_name: str,
    dirty: list[dict[str, str]],
    clean: list[dict[str, str]],
) -> dict[str, Any]:
    import numpy as np
    import pandas as pd
    import raha

    random.seed(0)
    np.random.seed(0)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=f"github-benchmark-{dataset_name}-") as temporary:
        root = Path(temporary)
        dirty_path = root / "dirty.csv"
        clean_path = root / "clean.csv"
        pd.DataFrame(dirty).to_csv(dirty_path, index=False, encoding="utf-8")
        pd.DataFrame(clean).to_csv(clean_path, index=False, encoding="utf-8")
        definition = {"name": dataset_name, "path": str(dirty_path), "clean_path": str(clean_path)}
        detector = raha.Detection()
        detector.SAVE_RESULTS = False
        detector.VERBOSE = False
        detector.LABELING_BUDGET = min(20, len(dirty))
        # Raha's dBoost branch leaves temporary CSV handles open on Windows,
        # while KBVD reads bundled knowledge-base files with the system code
        # page. PVD and RVD are official, self-contained Raha strategies and
        # keep the comparison runnable without modifying upstream source.
        detector.ERROR_DETECTION_ALGORITHMS = ["PVD", "RVD"]
        original_pool = raha.detection.multiprocessing.Pool
        raha.detection.multiprocessing.Pool = lambda: _SerialPool()
        try:
            detected = detector.run(definition)
        finally:
            raha.detection.multiprocessing.Pool = original_pool
        dataset = raha.dataset.Dataset(definition)
        precision, recall, f1 = dataset.get_data_cleaning_evaluation(detected)[:3]
    return {
        "status": "OK",
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "detected_cell_count": len(detected),
        "labeling_budget": detector.LABELING_BUDGET,
        "strategy_subset": detector.ERROR_DETECTION_ALGORITHMS,
        "runtime_seconds": time.perf_counter() - started,
    }


def run_cleaning_results(data_root: Path, raha_datasets: set[str]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for dataset_id in sorted(CLEANING_DATASETS):
        dataset_dir, manifest = prepare_cleaning_dataset(dataset_id, data_root, download=False)
        dirty, clean = load_cleaning_dataset(dataset_dir)
        candidates = {
            "Project format profile v2": _project_format_profile_repair(dirty),
            "Project consensus clean v1": _project_consensus_repair(dirty),
        }
        project_methods = {name: _cell_detection_metrics(dirty, clean, repaired) for name, repaired in candidates.items()}
        project_name = "Project format profile v2"
        project = project_methods[project_name]
        strict_repair = evaluate_cleaning(dirty, clean, "project_format_profile_v2")
        if dataset_id not in raha_datasets:
            external = {"status": "NOT_EVALUATED", "reason": "本轮资源保护未运行 Raha；项目结果仍已完整计分。"}
        else:
            try:
                external = _run_raha(CLEANING_DATASETS[dataset_id]["folder_name"], dirty, clean)
            except Exception as exc:
                external = {"status": "NOT_EVALUATED", "reason": f"{type(exc).__name__}: {exc}"}
        rows.append({
            "dataset": dataset_id,
            "status": "OK",
            "dirty_cell_count": project["dirty_cell_count"],
            "project_method": project_name,
            "project_f1": project["f1"],
            "project_detection_metrics": project,
            "project_methods": project_methods,
            "project_exact_repair_f1": strict_repair.cell_f1,
            "project_repair_accuracy": strict_repair.repair_accuracy,
            "github_method": "Raha 1.26 PVD+RVD subset",
            "github_f1": external.get("f1"),
            "github_metrics": external,
            "source_id": manifest["source_id"],
            "source_url": manifest["source_url"],
            "dirty_sha256": manifest["dirty_sha256"],
            "clean_sha256": manifest["clean_sha256"],
        })
    project_macro, github_macro, comparable_count = _paired_macros(rows, "project_f1", "github_f1")
    return {
        "metric": "错误单元检测 F1（修复质量另列）",
        "rows": rows,
        "project_macro": project_macro,
        "github_macro": github_macro,
        "comparable_dataset_count": comparable_count,
        "project_all_six_macro": _macro(rows, "project_f1"),
    }


def _fmt(value: Any) -> str:
    return "未评测" if value is None else f"{float(value):.4f}"


def _project_fmt(value: Any) -> str:
    return "**未评测**" if value is None else f"**{float(value):.4f}**"


def _winner(project: Any, external: Any) -> str:
    if project is None or external is None:
        return "暂不能比较"
    difference = float(project) - float(external)
    if abs(difference) < 1e-12:
        return "相同"
    return f"本项目高 {difference:.4f}" if difference > 0 else f"外部方法高 {-difference:.4f}"


def build_report(payload: dict[str, Any]) -> str:
    retrieval = payload["modules"]["retrieval"]
    schema = payload["modules"]["schema_matching"]
    entity = payload["modules"]["entity_matching"]
    cleaning = payload["modules"]["cleaning"]
    lines = [
        "# GitHub 同类项目公开数据集实测对比",
        "",
        "> 这份报告只回答一个问题：把本项目与 GitHub 同类方法放到同一公开数据集、同一划分和同一指标下，谁在该功能上表现更好。它不是乳腺癌临床效果，也不是正式 SDTI。",
        "",
        "![GitHub 同类项目四模块对比](../../docs/images/github-benchmark-summary.png)",
        "",
        "## 先看结论",
        "",
        "| 功能 | 公开数据 | 本项目 | GitHub 对照 | 怎么读 |",
        "|---|---|---:|---:|---|",
        f"| 科学检索 | BEIR 5 个数据集 | {_project_fmt(retrieval['project_macro'])} | {_fmt(retrieval['github_macro'])} | {_winner(retrieval['project_macro'], retrieval['github_macro'])}（nDCG@10） |",
        f"| 字段匹配 | Valentine 10 个任务 | {_project_fmt(schema['project_macro'])} | {_fmt(schema['github_macro'])} | {_winner(schema['project_macro'], schema['github_macro'])}（F1） |",
        f"| 实体匹配 | DeepMatcher 5 个任务 | {_project_fmt(entity['project_macro'])} | {_fmt(entity['github_macro'])} | {_winner(entity['project_macro'], entity['github_macro'])}（F1） |",
        f"| 数据清洗 | 5 个共同实测任务（Tax 仅项目） | {_project_fmt(cleaning['project_macro'])} | {_fmt(cleaning['github_macro'])} | {_winner(cleaning['project_macro'], cleaning['github_macro'])}（错误单元检测 F1） |",
        "",
        "这里的四个分数不能相加。每一行是不同问题、不同数据和不同指标，只能在该行内部比较。",
        "",
        "## 和上一份内部报告的区别",
        "",
        "| 项目 | 上一份内部报告 | 这份 GitHub 对比报告 | 为什么数字会不同 |",
        "|---|---|---|---|",
        "| 目的 | 看项目版本迭代、消融和候选卷 | 看项目与同类开源方法谁更好 | 评测对象不同 |",
        "| 检索 | 同时列 BM25、BGE、融合 | 固定比较“项目融合 vs BGE” | 上一份没有把项目融合与外部 BGE 直接放在结论列 |",
        "| 字段匹配 | 项目 V2 值画像 **0.8451** | 生产 V3 **0.7994** vs Valentine COMA `0.7670` | V2 与 V3 不是同一个方法；这份固定 COMA，避免逐题挑最高算法 |",
        "| 实体匹配 | 项目 V2 **0.7408** | 生产 V3 **0.5579** vs RecordLinkage `0.7440` | V2 仍保存在结果中，宏平均约 **0.7408**；主表改用带安全决策的生产 V3 |",
        "| 数据清洗 | 6 集 Cell F1 **0.4856** | 共同 5 集检测 F1 **0.3937** vs Raha `0.8159` | 旧值含 Tax；新值只算双方都有结果的 5 集，并把检测与正确修复拆开 |",
        "| 正式成绩 | 候选卷观察值曾写 **100** | 不计算 SDTI | 候选卷仍是 `REVIEW`、不可发布；正式口径仍是 **63.36** |",
        "",
        "因此，当前报告不是在宣布项目整体退步，而是在把生产方法放到外部同类方法面前重新校准：字段匹配有优势，检索接近但略低，实体匹配和清洗检测需要继续提升。",
        "",
        "## 结果地图与改进优先级",
        "",
        "| 优先级 | 观察 | 下一轮应验证的改进 |",
        "|---|---|---|",
        "| P0 | 清洗宏平均落后 0.4223，Hospital/Rayyan 检出为 0 | 增加跨列约束与缺失/语义异常检测，在独立验证集选择阈值 |",
        "| P0 | 实体匹配宏平均落后 0.1861，Beer 数据集为 0 | 改进小样本校准和字段自适应权重，保持患者关联安全门不放宽 |",
        "| P1 | 融合检索略低于 BGE 0.0088 | 按数据集验证 RRF 权重与重排，不以测试集逐题选权重 |",
        "| 保持 | 字段匹配领先 COMA 0.0324 | 扩大医学高风险字段测试，继续保留 HER2/ERBB2 守门 |",
        "",
        "优先级依据差距与风险确定，不把四个异构分数合成为单一排名。每项改动都应在 development 上调参，再用独立 held-out 数据确认。",
        "",
        "## 1. 科学检索",
        "",
        "问题：给定一个科学问题，能否把相关文献排在前十。数字越高越好。项目方法是 BM25 与 BGE 融合；外部模型基线是 GitHub FlagEmbedding 使用的 BAAI/bge-small-en-v1.5 权重，由统一评测器加载，保证数据和指标一致。",
        "",
        "![BEIR 五个公开检索数据集分层结果](../../docs/images/github-retrieval-breakdown.png)",
        "",
        "| 数据集 | 查询数 | 本项目融合 | BGE 单路 | BM25 | 结果 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in retrieval["rows"]:
        if row["status"] != "OK":
            lines.append(f"| {row['dataset']} | - | 未评测 | 未评测 | 未评测 | {row['reason']} |")
        else:
            lines.append(f"| {row['dataset']} | {row['query_count']} | {_project_fmt(row['project_ndcg_at_10'])} | {_fmt(row['github_ndcg_at_10'])} | {_fmt(row['bm25_ndcg_at_10'])} | {_winner(row['project_ndcg_at_10'], row['github_ndcg_at_10'])} |")
    lines.extend([
        "",
        "怎么理解：BGE 单路代表语义检索能力，BM25 代表关键词检索能力，本项目融合两者。若融合没有超过两条单路，说明融合权重或重排仍需优化。",
        "",
        "## 2. 字段匹配",
        "",
        "问题：两张表中的不同列名是否表示同一字段。每个任务都使用 Valentine 官方 ground truth；主比较固定使用 Valentine 文档推荐的通用首选 COMA，避免看完测试结果后再挑算法。五种官方算法的逐项结果保留在 results.json。",
        "",
        "| 数据集 | 标准匹配数 | 本项目 V3 | COMA | 该任务外部最高（仅诊断） | 结果 |",
        "|---|---:|---:|---:|---|---|",
    ])
    for row in schema["rows"]:
        lines.append(f"| {row['dataset']} | {row['gold_count']} | {_project_fmt(row['project_f1'])} | {_fmt(row['github_f1'])} | {row['best_github_method']} {_fmt(row['best_github_f1'])} | {_winner(row['project_f1'], row['github_f1'])} |")
    lines.extend([
        "",
        "怎么理解：本项目加入了字段别名、值分布和医学安全边界；Valentine 是通用字段匹配工具。通用任务领先不等于医学字段已经安全，HER2 等高风险字段仍必须走 review。",
        "",
        "## 3. 实体匹配",
        "",
        "问题：两条记录是否指向同一个实体。训练、验证、测试使用 DeepMatcher 官方划分；外部对照使用 RecordLinkage 的 Jaro-Winkler/精确匹配特征和逻辑回归，阈值只在验证集选择。",
        "",
        "| 数据集 | 测试对数 | 本项目 V3 | RecordLinkage | 结果 |",
        "|---|---:|---:|---:|---|",
    ])
    for row in entity["rows"]:
        lines.append(f"| {row['dataset']} | {row['splits']['test']['pair_count']} | {_project_fmt(row['project_f1'])} | {_fmt(row['github_f1'])} | {_winner(row['project_f1'], row['github_f1'])} |")
    lines.extend([
        "",
        "怎么理解：这些是商品、论文和餐馆记录，不是患者身份。生产系统仍然把低置信度患者/样本关系放入 unresolved/review，不能因通用实体 F1 较高就自动合并患者。",
        "",
        "## 4. 数据清洗",
        "",
        "问题：能否找出错误单元格。项目与 Raha 使用相同 dirty/clean 表；项目侧固定使用 format-profile v2，不按测试集挑最好方法。表中主 F1 只比较错误位置检测；项目自动修复是否改对，另看“精确修复 F1”和 Repair Accuracy。外部方法运行 Raha 官方 PVD+RVD 策略子集并使用 20 条人工标注的模拟流程；完整默认策略中的 dBoost/KBVD 在 Windows 存在文件句柄和编码兼容问题，因此没有冒充完整 Raha 成绩。本项目方法不使用标签，监督成本也不同。主结论只对双方都完成的 5 个数据集取宏平均；Tax 只展示项目结果，不进入双方对比。",
        "",
        "| 数据集 | 错误单元 | 本项目检测 F1 | Raha PVD+RVD F1 | 项目精确修复 F1 | Repair Accuracy | 结果 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ])
    for row in cleaning["rows"]:
        reason = row["github_metrics"].get("reason") if row["github_metrics"]["status"] != "OK" else _winner(row["project_f1"], row["github_f1"])
        lines.append(f"| {row['dataset']} | {row['dirty_cell_count']} | {_project_fmt(row['project_f1'])} | {_fmt(row['github_f1'])} | {_project_fmt(row['project_exact_repair_f1'])} | {_project_fmt(row['project_repair_accuracy'])} | {reason} |")
    lines.extend([
        "",
        "怎么理解：检测到错误不代表能安全恢复正确值。对缺失值、语义冲突和医学字段，本项目宁可送审，也不为了提高修复数量而猜值。",
        "",
        "## 5. 没有填数字的 GitHub 项目",
        "",
        "| 项目 | 状态 | 原因 |",
        "|---|---|---|",
    ])
    for key in ("deepmatcher", "ditto", "holoclean"):
        repo = payload["repositories"][key]
        lines.append(f"| [{key}]({repo['url']}) | {repo['status']} | {repo['reason']} |")
    lines.extend([
        "",
        "这些项目的论文数字没有抄进本表，因为版本、硬件、数据预处理或划分不同。后续若完成隔离环境复现，再把本机实跑结果补入。",
        "",
        "## 6. 功能差异，不做伪总分",
        "",
        "| 能力 | 本项目 | GitHub 单点工具 |",
        "|---|---|---|",
        "| 从科研问题到数据集 | 有完整主链 | 多数只解决单个模块 |",
        "| 真实来源与字段追溯 | 保留 source_id、raw_field、raw_value | 取决于具体工具 |",
        "| 医学安全规则 | HER2、跨 response domain、低置信度关联强制守门 | 通用工具通常不包含 |",
        "| 自主闭环 | 可根据缺口补搜并比较两轮效果 | 单点算法通常无端到端闭环 |",
        "| 通用算法上限 | 某些数据集仍落后，需要继续优化 | 专用工具在其单点任务可能更强 |",
        "",
        "## 7. 复现信息",
        "",
        f"- 生成时间：`{payload['created_at']}`",
        f"- 本项目代码版本：`{payload['project_revision']}`",
        f"- Python：`{payload['environment']['python']}`",
        "- 完整逐方法指标、数据哈希、运行文件位置：见同目录 `results.json`。",
        "- 推荐复现命令：`python scripts/run_github_competitor_benchmark.py --external-package-dir <外部评测依赖目录>`。",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run same-data GitHub competitor benchmarks and build a Chinese Markdown report.")
    parser.add_argument("--external-package-dir", type=Path, default=os.environ.get("GITHUB_BENCHMARK_PACKAGE_DIR"))
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "evaluation" / "github_competitor_benchmark_20260830")
    parser.add_argument("--skip-schema", action="store_true")
    parser.add_argument("--skip-entity", action="store_true")
    parser.add_argument("--skip-raha", action="store_true")
    parser.add_argument("--include-raha-tax", action="store_true", help="Tax has 121k dirty cells and is intentionally excluded by default.")
    args = parser.parse_args()
    _load_external_packages(args.external_package_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    raha_datasets = set() if args.skip_raha else set(CLEANING_DATASETS) - {"raha_tax"}
    if args.include_raha_tax:
        raha_datasets.add("raha_tax")
    modules = {
        "retrieval": collect_retrieval_results(),
        "schema_matching": {"status": "NOT_EVALUATED", "rows": [], "project_macro": None, "github_macro": None} if args.skip_schema else run_schema_results(PROJECT_ROOT / "data" / "benchmarks" / "schema"),
        "entity_matching": {"status": "NOT_EVALUATED", "rows": [], "project_macro": None, "github_macro": None} if args.skip_entity else run_entity_results(PROJECT_ROOT / "data" / "benchmarks" / "entity"),
        "cleaning": run_cleaning_results(PROJECT_ROOT / "data" / "benchmarks" / "cleaning", raha_datasets),
    }
    payload = {
        "evaluation_id": "github-competitor-benchmark-20260830",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_revision": _git_revision(),
        "scope": "Same public data, same split, same metric; module-level comparison only.",
        "environment": {
            "python": sys.version,
            "platform": sys.platform,
            "packages": {
                name: importlib.metadata.version(name)
                for name in ("torch", "transformers", "sentence-transformers", "pandas", "scikit-learn", "recordlinkage", "raha", "valentine")
                if _package_exists(name)
            },
        },
        "repositories": REPOSITORIES,
        "modules": modules,
    }
    (args.output_dir / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "report.md").write_text(build_report(payload), encoding="utf-8")
    print(args.output_dir / "report.md")


def _package_exists(name: str) -> bool:
    try:
        importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


if __name__ == "__main__":
    main()
