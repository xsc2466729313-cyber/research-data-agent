from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from backend.app.quality_v2.models import (
    DetectionRisk,
    ErrorDetectionResult,
    GateStatus,
    HardGate,
    QualityRecord,
    ReadinessReport,
    SoftIndicators,
)


class ReadinessEvaluator:
    VERSION = "research-readiness-v2"
    _CANONICAL_REQUIRED = ("study_id", "disease", "source_id", "raw_field", "raw_value", "confidence")
    _CRITICAL_TYPES = frozenset({
        "her2_assay_error", "erbb2_cna_not_ihc", "patient_sample_conflict",
        "high_authority_conflict", "cross_domain_response",
    })

    def evaluate(
        self,
        records: Iterable[QualityRecord],
        detection: ErrorDetectionResult,
        *,
        task_id: str | None = None,
        required_fields: Iterable[str] = (),
        recommended_fields: Iterable[str] = (),
        granularity: str | None = None,
    ) -> ReadinessReport:
        items = list(records)
        required = list(dict.fromkeys([*self._CANONICAL_REQUIRED, *required_fields]))
        findings_by_record = {record_id for finding in detection.findings for record_id in finding.record_ids}
        gates = [
            self._required_gate(items, required),
            self._outcome_gate(items, required),
            self._granularity_gate(items, granularity),
            self._provenance_gate(items),
            self._join_gate(detection),
            self._medical_gate(detection),
        ]
        missing_cells = sum(1 for item in items for field in required if item.record.get(field) in (None, ""))
        denominator = max(len(items) * max(len(required), 1), 1)
        missingness = min(missing_cells / denominator, 1.0)
        recommended = list(dict.fromkeys(recommended_fields))
        recommended_coverage = 1.0 if not recommended else sum(any(item.record.get(field) not in (None, "") for item in items) for field in recommended) / len(recommended)
        traceability = sum(all(item.record.get(field) not in (None, "") for field in ("source_id", "raw_field", "raw_value")) for item in items) / len(items) if items else 0.0
        authority = sum({"high": 1.0, "standard": 0.7, "low": 0.3}.get(getattr(item.source_authority, "value", str(item.source_authority)), 0.5) for item in items) / len(items) if items else 0.0
        review_count = sum(1 for finding in detection.findings if finding.recommended_action.value == "REVIEW")
        blocking_count = sum(1 for finding in detection.findings if finding.recommended_action.value == "BLOCK" or finding.risk_level is DetectionRisk.HIGH)
        soft = SoftIndicators(sample_size=len(items), missingness_rate=round(missingness, 4), recommended_field_coverage=round(recommended_coverage, 4), source_authority_score=round(authority, 4), traceability_rate=round(traceability, 4), review_burden=round(min(review_count / max(len(items), 1), 1.0), 4))
        failed = [gate for gate in gates if gate.status is GateStatus.FAIL]
        reviewed = [gate for gate in gates if gate.status is GateStatus.REVIEW]
        if failed:
            status = "NOT_READY"
        elif reviewed:
            status = "READY_WITH_REVIEW"
        else:
            status = "READY"
        rationale = [f"{gate.gate_id}: {gate.evidence}" for gate in gates]
        if not items:
            status = "NOT_READY"
            rationale.append("没有记录，无法形成可复现科研队列。")
        return ReadinessReport(task_id=task_id or detection.task_id, status=status, publish_allowed=status == "READY", hard_gates=gates, soft_indicators=soft, reviewed_record_count=len(findings_by_record), blocking_finding_count=blocking_count, review_finding_count=review_count, rationale=rationale, readiness_version=self.VERSION, evaluated_at=datetime.now(timezone.utc))

    def evaluate_readiness(self, records, detection, **kwargs):
        return self.evaluate(records, detection, **kwargs)

    @staticmethod
    def _required_gate(records, required):
        missing = sorted({field for item in records for field in required if item.record.get(field) in (None, "")})
        return HardGate(gate_id="required_fields", status=GateStatus.FAIL if missing else GateStatus.PASS, passed=not missing, evidence="缺少必填字段: " + ", ".join(missing) if missing else f"{len(required)} 个必填字段均有值。", affected_record_ids=[item.record_id for item in records if any(item.record.get(field) in (None, "") for field in missing)])

    def _outcome_gate(self, records, required):
        outcome_fields = [field for field in ("response", "response_domain", "response_type") if field in required]
        if not outcome_fields:
            outcome_fields = ["response_domain"] if any(item.record.get("response") not in (None, "") for item in records) else []
        invalid = [item.record_id for item in records if item.record.get("response") not in (None, "") and item.record.get("response_domain") in (None, "")]
        return HardGate(gate_id="outcome_validity", status=GateStatus.FAIL if invalid else GateStatus.PASS, passed=not invalid, evidence="存在 response 但缺 response_domain。" if invalid else "response 与 response_domain 未发现跨域缺失。", affected_record_ids=invalid)

    @staticmethod
    def _granularity_gate(records, granularity):
        if not granularity:
            return HardGate(gate_id="granularity_match", status=GateStatus.PASS, passed=True, evidence="未指定分析粒度，保留实际记录粒度。")
        field = {"patient": "patient_id", "patient-level": "patient_id", "sample": "sample_id", "sample-level": "sample_id", "study": "study_id", "study-level": "study_id"}.get(granularity.casefold())
        if not field:
            return HardGate(gate_id="granularity_match", status=GateStatus.REVIEW, passed=False, evidence=f"无法解释分析粒度 {granularity}，需要人工确认。")
        missing = [item.record_id for item in records if item.record.get(field) in (None, "")]
        return HardGate(gate_id="granularity_match", status=GateStatus.FAIL if missing else GateStatus.PASS, passed=not missing, evidence=f"目标粒度 {granularity} 对应 {field}。" + (f" 缺失 {len(missing)} 行。" if missing else ""), affected_record_ids=missing)

    @staticmethod
    def _provenance_gate(records):
        missing = [item.record_id for item in records if any(item.record.get(field) in (None, "") for field in ("source_id", "raw_field", "raw_value"))]
        return HardGate(gate_id="provenance_completeness", status=GateStatus.FAIL if missing else GateStatus.PASS, passed=not missing, evidence="关键来源追溯字段完整。" if not missing else f"{len(missing)} 行缺少 source_id/raw_field/raw_value。", affected_record_ids=missing)

    @staticmethod
    def _join_gate(detection):
        ids = [record_id for finding in detection.findings if finding.error_type in {"patient_sample_conflict", "high_authority_conflict"} for record_id in finding.record_ids]
        return HardGate(gate_id="join_safety", status=GateStatus.FAIL if ids else GateStatus.PASS, passed=not ids, evidence="未发现患者/样本身份冲突。" if not ids else "发现身份冲突，禁止进入正式发布集。", affected_record_ids=sorted(set(ids)))

    def _medical_gate(self, detection):
        critical = [record_id for finding in detection.findings if finding.error_type in self._CRITICAL_TYPES for record_id in finding.record_ids]
        return HardGate(gate_id="critical_medical_rules", status=GateStatus.FAIL if critical else GateStatus.PASS, passed=not critical, evidence="关键医学安全规则通过。" if not critical else "存在未解决的医学高风险或跨 response_domain 冲突。", affected_record_ids=sorted(set(critical)))


def evaluate_readiness(records, detection: ErrorDetectionResult, **kwargs) -> ReadinessReport:
    normalized = [item if isinstance(item, QualityRecord) else QualityRecord.model_validate(item) for item in records]
    return ReadinessEvaluator().evaluate(normalized, detection, **kwargs)
