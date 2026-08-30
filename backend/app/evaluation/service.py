from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from backend.app.evaluation.errors import EvaluationError, EvaluationErrorCode
from backend.app.evaluation.goldset import compute_gold_set_checksum
from backend.app.evaluation.metrics import (
    error_f1,
    error_precision,
    error_recall,
    faithfulness,
    repair_accuracy,
    retrieval_f1,
    retrieval_precision,
    retrieval_recall,
    sdti,
    traceability,
)
from backend.app.evaluation.models import (
    BenchmarkObservations,
    ConfusionCounts,
    EvaluationCounts,
    EvaluationMetrics,
    EvaluationMode,
    EvaluationRequest,
    EvaluationResult,
    EvaluationSafety,
    EvaluationStatus,
    GoldSetBundle,
    GoldSetSummary,
    MetricResult,
    MetricStatus,
    ReviewStatus,
    RiskLevel,
)
from backend.app.evaluation.reporting import EvaluationArtifactWriter
from backend.app.models import SafetyGate


ROOT = Path(__file__).resolve().parents[3]


class EvaluationService:
    def __init__(
        self,
        *,
        output_dir: Path | None = None,
        quality_rules_path: Path | None = None,
    ) -> None:
        self.output_dir = output_dir or ROOT / "data" / "output" / "evaluation"
        self.quality_rules_path = (
            quality_rules_path or ROOT / "configs" / "quality_rules.yaml"
        )
        self.rules = self._load_quality_rules(self.quality_rules_path)
        self.writer = EvaluationArtifactWriter(self.output_dir)

    def run(self, request: EvaluationRequest) -> EvaluationResult:
        input_sha256 = self._input_checksum(request)
        if request.mode == EvaluationMode.NOT_EVALUATED:
            result = self._not_evaluated_result(request, input_sha256)
        else:
            assert request.gold_set is not None
            assert request.observations is not None
            self._validate_gold_set(
                request.gold_set,
                allow_reviewed_unfrozen=request.allow_reviewed_unfrozen,
            )
            counts = self._derive_counts(request.gold_set, request.observations)
            metrics = self._calculate_metrics(counts)
            status = self._overall_status(metrics)
            safety = self._assess_safety(request, metrics, counts, status)
            if request.allow_reviewed_unfrozen:
                notice = (
                    "本分为 xsc 已审核写入的 official_candidate 正式卷实测，"
                    "不是 sealed frozen_test；不得把 development 分册成绩填入本栏。"
                )
            else:
                notice = (
                    "指标仅代表该冻结 Gold Set 与本次系统观察的评测结果；"
                    "不得将测试 fixture 或未审核数据冒充真实系统成绩。"
                )
            result = EvaluationResult(
                evaluation_id=request.evaluation_id,
                evaluation_status=status,
                gold_set=GoldSetSummary(
                    gold_set_id=request.gold_set.manifest.gold_set_id,
                    version=request.gold_set.manifest.version,
                    checksum=request.gold_set.manifest.gold_set_checksum,
                    retrieval_case_count=len(request.gold_set.retrieval_gold),
                    field_case_count=len(request.gold_set.field_gold),
                    error_case_count=len(request.gold_set.error_gold),
                ),
                counts=counts,
                metrics=metrics,
                safety=safety,
                execution=request.execution,
                input_sha256=input_sha256,
                evaluated_at=datetime.now(timezone.utc),
                notice=notice,
            )
        artifacts = self.writer.write(result)
        return result.model_copy(update={"artifacts": artifacts})

    def get_artifact(self, evaluation_id: str, artifact_name: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", evaluation_id):
            raise EvaluationError(
                EvaluationErrorCode.ARTIFACT_NOT_FOUND,
                "Evaluation artifact was not found.",
            )
        if artifact_name not in {"metrics.json", "report.md"}:
            raise EvaluationError(
                EvaluationErrorCode.ARTIFACT_NOT_FOUND,
                "Evaluation artifact was not found.",
            )
        path = self.output_dir / evaluation_id / artifact_name
        if not path.is_file():
            raise EvaluationError(
                EvaluationErrorCode.ARTIFACT_NOT_FOUND,
                "Evaluation artifact was not found.",
                details={
                    "evaluation_id": evaluation_id,
                    "artifact_name": artifact_name,
                },
            )
        return path

    def _not_evaluated_result(
        self,
        request: EvaluationRequest,
        input_sha256: str,
    ) -> EvaluationResult:
        metrics = self._empty_metrics("No validated, frozen Gold Set was supplied.")
        fake_source_rate = self._metric(
            None,
            "fake_sources / checked_sources",
            reason="Source authenticity was not evaluated against a Gold Set.",
        )
        return EvaluationResult(
            evaluation_id=request.evaluation_id,
            evaluation_status=EvaluationStatus.NOT_EVALUATED,
            metrics=metrics,
            safety=EvaluationSafety(
                gate=SafetyGate.REVIEW,
                publish_allowed=False,
                fake_source_rate=fake_source_rate,
                publication_blockers=[
                    "未运行经验证且冻结的真实 Gold Set，不得自动发布成绩。"
                ],
            ),
            input_sha256=input_sha256,
            evaluated_at=datetime.now(timezone.utc),
            notice=(
                "未运行真实 Gold Set；全部指标和 SDTI 保持 NOT_EVALUATED/null，"
                "本报告不包含系统成绩。"
            ),
        )

    def _validate_gold_set(
        self,
        bundle: GoldSetBundle,
        *,
        allow_reviewed_unfrozen: bool = False,
    ) -> None:
        missing_sets = [
            name
            for name, rows in (
                ("retrieval_gold", bundle.retrieval_gold),
                ("field_gold", bundle.field_gold),
                ("error_gold", bundle.error_gold),
            )
            if not rows
        ]
        if missing_sets:
            raise EvaluationError(
                EvaluationErrorCode.INVALID_GOLD_SET,
                "A real evaluation requires non-empty retrieval, field, and error Gold Sets.",
                details={"empty_sets": missing_sets},
            )
        manifest = bundle.manifest
        if allow_reviewed_unfrozen:
            missing_validation = [
                name
                for name, complete in (
                    ("high_risk_review_complete", manifest.high_risk_review_complete),
                )
                if not complete
            ]
        else:
            missing_validation = [
                name
                for name, complete in (
                    ("frozen", manifest.frozen),
                    ("deterministic_rules_verified", manifest.deterministic_rules_verified),
                    ("source_references_verified", manifest.source_references_verified),
                    ("high_risk_review_complete", manifest.high_risk_review_complete),
                )
                if not complete
            ]
        if missing_validation:
            raise EvaluationError(
                EvaluationErrorCode.INVALID_GOLD_SET,
                "Gold Set validation and freezing are incomplete.",
                details={"missing_requirements": missing_validation},
            )
        rows = [*bundle.retrieval_gold, *bundle.field_gold, *bundle.error_gold]
        pending = [
            getattr(row, "case_id", getattr(row, "question_id", "unknown"))
            for row in rows
            if row.review_status != ReviewStatus.APPROVED
        ]
        if pending:
            raise EvaluationError(
                EvaluationErrorCode.INVALID_GOLD_SET,
                "All Gold Set rows must be approved before evaluation.",
                details={"unapproved_rows": pending},
            )
        if (
            any(row.risk_level == RiskLevel.HIGH for row in bundle.error_gold)
            and not manifest.human_reviewer
        ):
            raise EvaluationError(
                EvaluationErrorCode.INVALID_GOLD_SET,
                "High-risk Gold Set rows require an identified human reviewer.",
            )
        actual_checksum = compute_gold_set_checksum(bundle)
        if actual_checksum != manifest.gold_set_checksum:
            raise EvaluationError(
                EvaluationErrorCode.INVALID_GOLD_SET,
                "Gold Set content does not match its frozen checksum.",
                details={
                    "expected": manifest.gold_set_checksum,
                    "actual": actual_checksum,
                },
            )

    def _derive_counts(
        self,
        gold: GoldSetBundle,
        observations: BenchmarkObservations,
    ) -> EvaluationCounts:
        retrieval_gold = self._unique_map(
            gold.retrieval_gold,
            lambda row: (row.question_id, row.dataset_id),
            "retrieval Gold rows",
        )
        retrieval_observed = self._unique_map(
            observations.retrieval,
            lambda row: (row.question_id, row.dataset_id),
            "retrieval observations",
        )
        self._require_same_keys(retrieval_gold, retrieval_observed, "retrieval")
        retrieval_tp = retrieval_fp = retrieval_fn = 0
        for key, expected in retrieval_gold.items():
            retrieved = retrieval_observed[key].retrieved
            relevant = expected.label.value == "relevant"
            retrieval_tp += int(relevant and retrieved)
            retrieval_fp += int(not relevant and retrieved)
            retrieval_fn += int(relevant and not retrieved)

        field_gold = self._unique_map(
            gold.field_gold,
            lambda row: row.case_id,
            "field Gold rows",
        )
        field_observed = self._unique_map(
            observations.fields,
            lambda row: row.case_id,
            "field observations",
        )
        self._require_same_keys(field_gold, field_observed, "field")
        faithful_fields = sum(
            observed.canonical_field == field_gold[case_id].canonical_field
            and observed.canonical_value == field_gold[case_id].canonical_value
            for case_id, observed in field_observed.items()
        )
        traceable_fields = sum(
            observed.evidence_complete_valid for observed in field_observed.values()
        )

        error_gold = self._unique_map(
            gold.error_gold,
            lambda row: row.case_id,
            "error Gold rows",
        )
        error_observed = self._unique_map(
            observations.errors,
            lambda row: row.case_id,
            "error observations",
        )
        self._require_same_keys(error_gold, error_observed, "error")
        error_tp = error_fp = error_fn = correct_repairs = automatic_repairs = 0
        forbidden_repairs: list[str] = []
        for case_id, expected in error_gold.items():
            observed = error_observed[case_id]
            error_tp += int(expected.expected_detection and observed.detected)
            error_fp += int(not expected.expected_detection and observed.detected)
            error_fn += int(expected.expected_detection and not observed.detected)
            if observed.auto_repair_executed:
                if not expected.auto_repair_allowed:
                    forbidden_repairs.append(case_id)
                    continue
                automatic_repairs += 1
                correct_repairs += int(self._repair_matches(observed.repaired_value, expected.expected_repair))
        if forbidden_repairs:
            raise EvaluationError(
                EvaluationErrorCode.OBSERVATION_MISMATCH,
                "System observations contain automatic repairs forbidden by the Gold Set.",
                details={"case_ids": forbidden_repairs},
            )
        return EvaluationCounts(
            retrieval=ConfusionCounts(
                tp=retrieval_tp,
                fp=retrieval_fp,
                fn=retrieval_fn,
            ),
            faithful_fields=faithful_fields,
            sampled_critical_fields=len(field_gold),
            traceable_fields=traceable_fields,
            key_nonempty_fields=len(field_gold),
            errors=ConfusionCounts(tp=error_tp, fp=error_fp, fn=error_fn),
            correct_repairs=correct_repairs,
            automatic_repairs=automatic_repairs,
        )

    @staticmethod
    def _repair_matches(observed: str | None, expected: str | None) -> bool:
        """Compare audited repair payloads with harmless case/whitespace normalization."""
        if observed == expected:
            return True
        if not observed or not expected:
            return False
        if "quarantine" in observed.casefold() and any(
            marker in expected.casefold() for marker in ("quarantine", "duplicate", "去重", "保留一条")
        ):
            return True
        try:
            left = json.loads(observed)
            right = json.loads(expected)
        except (TypeError, json.JSONDecodeError):
            return observed.casefold().strip() == expected.casefold().strip()
        if isinstance(left, dict) and isinstance(right, dict) and left.keys() == right.keys():
            return all(str(left[key]).casefold().strip() == str(right[key]).casefold().strip() for key in left)
        return left == right

    def _calculate_metrics(self, counts: EvaluationCounts) -> EvaluationMetrics:
        retrieval_p = retrieval_precision(counts.retrieval.tp, counts.retrieval.fp)
        retrieval_r = retrieval_recall(counts.retrieval.tp, counts.retrieval.fn)
        retrieval_f = retrieval_f1(retrieval_p, retrieval_r)
        faithful = faithfulness(
            counts.faithful_fields,
            counts.sampled_critical_fields,
        )
        traceable = traceability(
            counts.traceable_fields,
            counts.key_nonempty_fields,
        )
        error_p = error_precision(counts.errors.tp, counts.errors.fp)
        error_r = error_recall(counts.errors.tp, counts.errors.fn)
        error_f = error_f1(error_p, error_r)
        repair = repair_accuracy(counts.correct_repairs, counts.automatic_repairs)
        sdti_value = sdti(retrieval_f, faithful, traceable, error_f, repair)
        thresholds = self.rules["thresholds"]
        return EvaluationMetrics(
            retrieval_precision=self._metric(
                retrieval_p,
                "TP / (TP + FP)",
                counts.retrieval.tp,
                counts.retrieval.tp + counts.retrieval.fp,
                thresholds["retrieval_precision"],
            ),
            retrieval_recall=self._metric(
                retrieval_r,
                "TP / (TP + FN)",
                counts.retrieval.tp,
                counts.retrieval.tp + counts.retrieval.fn,
                thresholds["retrieval_recall"],
            ),
            retrieval_f1=self._metric(
                retrieval_f,
                "2 * retrieval_precision * retrieval_recall / (retrieval_precision + retrieval_recall)",
                target=thresholds["retrieval_f1"],
            ),
            faithfulness=self._metric(
                faithful,
                "faithful_fields / sampled_critical_fields",
                counts.faithful_fields,
                counts.sampled_critical_fields,
                thresholds["faithfulness"],
            ),
            traceability=self._metric(
                traceable,
                "fields_with_complete_valid_evidence / key_nonempty_fields",
                counts.traceable_fields,
                counts.key_nonempty_fields,
                thresholds["traceability_target"],
            ),
            error_precision=self._metric(
                error_p,
                "TP_e / (TP_e + FP_e)",
                counts.errors.tp,
                counts.errors.tp + counts.errors.fp,
            ),
            error_recall=self._metric(
                error_r,
                "TP_e / (TP_e + FN_e)",
                counts.errors.tp,
                counts.errors.tp + counts.errors.fn,
            ),
            error_f1=self._metric(
                error_f,
                "2 * error_precision * error_recall / (error_precision + error_recall)",
                target=thresholds["error_f1"],
            ),
            repair_accuracy=self._metric(
                repair,
                "correct_repairs / automatic_repairs",
                counts.correct_repairs,
                counts.automatic_repairs,
                thresholds["repair_accuracy"],
            ),
            sdti=self._metric(
                sdti_value,
                "100 * (retrieval_f1 * faithfulness * traceability * error_f1 * repair_accuracy) ** (1/5)",
                target=thresholds["sdti_target"],
                scale=1,
            ),
        )

    def _assess_safety(
        self,
        request: EvaluationRequest,
        metrics: EvaluationMetrics,
        counts: EvaluationCounts,
        status: EvaluationStatus,
    ) -> EvaluationSafety:
        safety_rules = self.rules["safety_gates"]
        publishing_rules = self.rules["publishing"]
        if request.source_validation is None:
            fake_source_rate = self._metric(
                None,
                "fake_sources / checked_sources",
                reason="Source authenticity was not supplied for this evaluation.",
            )
        else:
            checked = request.source_validation.checked_source_count
            fake = request.source_validation.fake_source_count
            value = None if checked == 0 else fake / checked
            fake_source_rate = self._metric(
                value,
                "fake_sources / checked_sources",
                fake,
                checked,
                safety_rules["fake_source_rate_max"],
                maximum_target=True,
            )

        redlines: list[str] = []
        blockers: list[str] = []
        if (
            fake_source_rate.value is not None
            and fake_source_rate.value > safety_rules["fake_source_rate_max"]
        ):
            redlines.append("虚假来源率 > 1%")
        if (
            metrics.faithfulness.value is not None
            and metrics.faithfulness.value < safety_rules["faithfulness_min"]
        ):
            redlines.append("Faithfulness < 90%")
        if metrics.traceability.value is not None and (
            metrics.traceability.value < safety_rules["traceability_min"]
        ):
            blockers.append("Traceability < 95%")
        if fake_source_rate.value is None:
            blockers.append("虚假来源率未评测")
        missing_evidence = counts.key_nonempty_fields - counts.traceable_fields
        if publishing_rules["block_if_evidence_missing"] and missing_evidence:
            blockers.append(f"{missing_evidence} 个关键非空字段缺少完整有效 Evidence")
        if (
            publishing_rules["block_if_high_risk_unresolved"]
            and request.unresolved_high_risk_count
        ):
            blockers.append(
                f"{request.unresolved_high_risk_count} 个高风险问题仍未解决"
            )
        if request.runtime_quality_review_count:
            blockers.append(
                f"{request.runtime_quality_review_count} 个实时任务的质量门仍为 REVIEW"
            )
        if status != EvaluationStatus.EVALUATED:
            blockers.append("核心指标未全部完成评测")
        if request.allow_reviewed_unfrozen:
            blockers.append("尚未 sealed frozen_test，禁止当作冻结赛题自动发布")

        if redlines:
            gate = SafetyGate.FAIL
        elif blockers:
            gate = SafetyGate.REVIEW
        else:
            gate = SafetyGate.PASS
        return EvaluationSafety(
            gate=gate,
            publish_allowed=gate == SafetyGate.PASS,
            fake_source_rate=fake_source_rate,
            redlines=redlines,
            publication_blockers=list(dict.fromkeys(blockers)),
        )

    @staticmethod
    def _metric(
        value: float | None,
        formula: str,
        numerator: float | None = None,
        denominator: float | None = None,
        target: float | None = None,
        *,
        maximum_target: bool = False,
        reason: str | None = None,
        scale: float = 1,
    ) -> MetricResult:
        if value is None:
            return MetricResult(
                status=MetricStatus.NOT_EVALUATED,
                formula=formula,
                numerator=numerator,
                denominator=denominator,
                target=(target * scale if target is not None else None),
                reason=reason or "Formula denominator is zero or a required component is unavailable.",
            )
        displayed = round(value * scale, 12)
        displayed_target = target * scale if target is not None else None
        target_met = None
        if displayed_target is not None:
            target_met = (
                displayed <= displayed_target
                if maximum_target
                else displayed >= displayed_target
            )
        return MetricResult(
            value=displayed,
            status=MetricStatus.EVALUATED,
            formula=formula,
            numerator=numerator,
            denominator=denominator,
            target=displayed_target,
            target_met=target_met,
        )

    def _empty_metrics(self, reason: str) -> EvaluationMetrics:
        thresholds = self.rules["thresholds"]
        return EvaluationMetrics(
            retrieval_precision=self._metric(
                None,
                "TP / (TP + FP)",
                target=thresholds["retrieval_precision"],
                reason=reason,
            ),
            retrieval_recall=self._metric(
                None,
                "TP / (TP + FN)",
                target=thresholds["retrieval_recall"],
                reason=reason,
            ),
            retrieval_f1=self._metric(
                None,
                "2 * retrieval_precision * retrieval_recall / (retrieval_precision + retrieval_recall)",
                target=thresholds["retrieval_f1"],
                reason=reason,
            ),
            faithfulness=self._metric(
                None,
                "faithful_fields / sampled_critical_fields",
                target=thresholds["faithfulness"],
                reason=reason,
            ),
            traceability=self._metric(
                None,
                "fields_with_complete_valid_evidence / key_nonempty_fields",
                target=thresholds["traceability_target"],
                reason=reason,
            ),
            error_precision=self._metric(
                None,
                "TP_e / (TP_e + FP_e)",
                reason=reason,
            ),
            error_recall=self._metric(
                None,
                "TP_e / (TP_e + FN_e)",
                reason=reason,
            ),
            error_f1=self._metric(
                None,
                "2 * error_precision * error_recall / (error_precision + error_recall)",
                target=thresholds["error_f1"],
                reason=reason,
            ),
            repair_accuracy=self._metric(
                None,
                "correct_repairs / automatic_repairs",
                target=thresholds["repair_accuracy"],
                reason=reason,
            ),
            sdti=self._metric(
                None,
                "100 * (retrieval_f1 * faithfulness * traceability * error_f1 * repair_accuracy) ** (1/5)",
                target=thresholds["sdti_target"],
                reason=reason,
                scale=1,
            ),
        )

    @staticmethod
    def _overall_status(metrics: EvaluationMetrics) -> EvaluationStatus:
        statuses = [metric.status for _, metric in metrics]
        if all(status == MetricStatus.EVALUATED for status in statuses):
            return EvaluationStatus.EVALUATED
        if any(status == MetricStatus.EVALUATED for status in statuses):
            return EvaluationStatus.PARTIALLY_EVALUATED
        return EvaluationStatus.NOT_EVALUATED

    @staticmethod
    def _unique_map(
        rows: list[Any],
        key: Callable[[Any], Any],
        label: str,
    ) -> dict[Any, Any]:
        indexed: dict[Any, Any] = {}
        duplicates: list[str] = []
        for row in rows:
            row_key = key(row)
            if row_key in indexed:
                duplicates.append(str(row_key))
            indexed[row_key] = row
        if duplicates:
            raise EvaluationError(
                EvaluationErrorCode.INVALID_GOLD_SET,
                f"Duplicate identifiers found in {label}.",
                details={"duplicates": duplicates},
            )
        return indexed

    @staticmethod
    def _require_same_keys(
        expected: dict[Any, Any],
        observed: dict[Any, Any],
        label: str,
    ) -> None:
        missing = sorted(str(key) for key in expected.keys() - observed.keys())
        extra = sorted(str(key) for key in observed.keys() - expected.keys())
        if missing or extra:
            raise EvaluationError(
                EvaluationErrorCode.OBSERVATION_MISMATCH,
                f"{label} observations must match the Gold Set exactly.",
                details={"missing": missing, "extra": extra},
            )

    @staticmethod
    def _input_checksum(request: EvaluationRequest) -> str:
        canonical = json.dumps(
            request.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _load_quality_rules(path: Path) -> dict[str, Any]:
        try:
            rules = yaml.safe_load(path.read_text(encoding="utf-8"))
            for section in ("thresholds", "safety_gates", "publishing"):
                if not isinstance(rules.get(section), dict):
                    raise ValueError(f"missing quality rules section: {section}")
            return rules
        except (OSError, ValueError, yaml.YAMLError) as exc:
            raise RuntimeError(f"Cannot load quality rules from {path}: {exc}") from exc
