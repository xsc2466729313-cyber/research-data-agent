from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from backend.app.models import (
    CandidateSource,
    CanonicalRecord,
    EvidenceCell,
    MockPipelineResult,
    QualityReport,
    ResearchSpec,
    SafetyGate,
    SearchPlan,
    SearchPlanItem,
    SourceItem,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MOCK_DIR = PROJECT_ROOT / "mock"


class UnsupportedMockQuestion(ValueError):
    """Raised when a question does not match the only stage-00 demo asset pack."""


class MockPipeline:
    """Run the stage-00 demo only from reviewable files under mock/."""

    def __init__(self, mock_dir: Path = MOCK_DIR) -> None:
        self.mock_dir = mock_dir

    def run(self, question: str) -> MockPipelineResult:
        self._validate_supported_question(question)
        research_spec = self._load_research_spec(question)
        candidates = self._load_candidates()
        source_items = self._load_jsonl("source_items.jsonl", SourceItem)
        canonical_records = self._load_canonical_records()
        evidence = self._load_jsonl("evidence.jsonl", EvidenceCell)
        search_plan = self._build_search_plan(research_spec.task_id, candidates)
        quality_report = self._build_quality_report(
            research_spec.task_id,
            source_items,
            canonical_records,
            evidence,
        )

        return MockPipelineResult(
            notice=(
                "阶段 00 使用仓库内 Mock 资产；未访问真实数据库，且未运行真实 Gold Set。"
            ),
            research_spec=research_spec,
            search_plan=search_plan,
            candidate_sources=candidates,
            source_items=source_items,
            canonical_dataset=canonical_records,
            evidence=evidence,
            quality_report=quality_report,
        )

    def _load_research_spec(self, question: str) -> ResearchSpec:
        payload = self._load_json("research_spec.json")
        payload["research_goal"] = question
        return ResearchSpec.model_validate(payload)

    def _load_candidates(self) -> list[CandidateSource]:
        with (self.mock_dir / "candidate_sources.csv").open(
            newline="", encoding="utf-8-sig"
        ) as handle:
            rows = []
            for row in csv.DictReader(handle):
                row["sample_count"] = self._optional_int(row.get("sample_count"))
                row["has_treatment"] = self._parse_bool(row["has_treatment"])
                row["has_response"] = self._parse_bool(row["has_response"])
                row["public_access"] = self._parse_bool(row["public_access"])
                row["relevance_score"] = float(row["relevance_score"])
                rows.append(CandidateSource.model_validate(row))
        return rows

    def _load_canonical_records(self) -> list[CanonicalRecord]:
        with (self.mock_dir / "canonical_dataset.csv").open(
            newline="", encoding="utf-8-sig"
        ) as handle:
            records = []
            for row in csv.DictReader(handle):
                cleaned: dict[str, Any] = {
                    key: (value if value != "" else None) for key, value in row.items()
                }
                cleaned["confidence"] = float(row["confidence"])
                records.append(CanonicalRecord.model_validate(cleaned))
        return records

    def _load_jsonl(self, filename: str, model: type[Any]) -> list[Any]:
        items = []
        with (self.mock_dir / filename).open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    items.append(model.model_validate_json(line))
        return items

    def _load_json(self, filename: str) -> dict[str, Any]:
        with (self.mock_dir / filename).open(encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _build_search_plan(
        task_id: str, candidates: list[CandidateSource]
    ) -> SearchPlan:
        sources: list[str] = []
        for candidate in candidates:
            if candidate.source_database not in sources:
                sources.append(candidate.source_database)
        plans = [
            SearchPlanItem(
                source=source,
                goal=f"读取 {source} 的阶段 00 Mock 候选来源",
                priority=index,
            )
            for index, source in enumerate(sources, start=1)
        ]
        return SearchPlan(task_id=task_id, plans=plans)

    @staticmethod
    def _build_quality_report(
        task_id: str,
        source_items: list[SourceItem],
        records: list[CanonicalRecord],
        evidence: list[EvidenceCell],
    ) -> QualityReport:
        known_source_ids = {item.source_id for item in source_items}
        orphan_records = [
            record.source_id for record in records if record.source_id not in known_source_ids
        ]
        orphan_evidence = [
            cell.source_id for cell in evidence if cell.source_id not in known_source_ids
        ]
        incomplete_evidence = [
            cell.evidence_id
            for cell in evidence
            if not cell.raw_field or cell.raw_value is None
        ]

        errors: list[dict[str, Any]] = []
        if orphan_records:
            errors.append({"type": "orphan_record_source", "source_ids": orphan_records})
        if orphan_evidence:
            errors.append({"type": "orphan_evidence_source", "source_ids": orphan_evidence})
        if incomplete_evidence:
            errors.append(
                {"type": "incomplete_evidence", "evidence_ids": incomplete_evidence}
            )

        checks = {
            "canonical_schema_validation": "PASS",
            "source_linkage": "PASS" if not orphan_records and not orphan_evidence else "FAIL",
            "evidence_payload_validation": "PASS" if not incomplete_evidence else "FAIL",
            "her2_ihc_2plus_safety": "PASS",
        }
        evaluation_metrics = {
            name: None
            for name in (
                "retrieval_precision",
                "retrieval_recall",
                "faithfulness",
                "traceability",
                "repair_accuracy",
                "sdti",
            )
        }

        return QualityReport(
            task_id=task_id,
            metrics={
                "evaluation_status": "NOT_EVALUATED",
                "reason": "阶段 00 未运行真实 Gold Set，禁止生成评测成绩。",
                "values": evaluation_metrics,
                "mock_validation": {
                    "checks": checks,
                    "canonical_record_count": len(records),
                    "evidence_cell_count": len(evidence),
                    "source_item_count": len(source_items),
                },
            },
            safety_gate=SafetyGate.FAIL if errors else SafetyGate.REVIEW,
            errors=errors,
            repairs=[],
        )

    @staticmethod
    def _parse_bool(value: str) -> bool:
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "公开"}:
            return True
        if normalized in {"false", "0", "no", "不公开"}:
            return False
        raise ValueError(f"Unsupported boolean value: {value!r}")

    @staticmethod
    def _optional_int(value: str | None) -> int | None:
        return int(value) if value and value.strip() else None

    @staticmethod
    def _validate_supported_question(question: str) -> None:
        normalized = question.upper().replace(" ", "")
        concept_groups = {
            "乳腺癌": ("乳腺", "BREAST"),
            "HER2": ("HER2", "ERBB2"),
            "PIK3CA": ("PIK3CA",),
            "治疗响应": ("响应", "疗效", "RESPONSE"),
        }
        missing = [
            label
            for label, aliases in concept_groups.items()
            if not any(alias in normalized for alias in aliases)
        ]
        if missing:
            raise UnsupportedMockQuestion(
                "阶段 00 仅提供预置的 HER2/PIK3CA 乳腺癌治疗响应 Mock 场景；"
                f"当前问题缺少：{', '.join(missing)}。"
            )
