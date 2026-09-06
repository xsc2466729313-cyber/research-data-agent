from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.app.research_planning.models import FieldPriority, FieldRequirement, ResearchContract
from backend.app.source_broker.models import DatasetCandidate, SourcePlanRequest
from backend.app.source_broker.service import SourceBroker
from backend.app.v30.models import (
    DiscoveryCandidate,
    RankedSourceCandidate,
    SelectedSourcePlan,
    SelectionContract,
    SourceSelectionRequest,
)
from backend.app.v30.registry.service import SourceRegistryService

FIELD_TO_MODALITIES = {
    "gene_expression": {"expression", "gene_expression"},
    "treatment_response": {"clinical_table", "clinical_outcomes", "drug_response", "treatment_response"},
    "clinical_table": {"clinical_table"},
    "mutation": {"mutation", "mutations"},
    "cna": {"cna"},
    "publication": {"publication"},
    "spectrum": {"spectrum"},
    "light_curve": {"light_curve"},
    "structure": {"structure"},
}


class SourceSelectionService:
    """Rank Discovery candidates by wrapping SourceBroker matcher/selector. Never fetches."""

    def __init__(
        self,
        *,
        broker: SourceBroker | None = None,
        registry: SourceRegistryService | None = None,
    ) -> None:
        self.broker = broker or SourceBroker()
        self.registry = registry or SourceRegistryService()

    def select(self, request: SourceSelectionRequest) -> SelectedSourcePlan:
        incoming_domain = request.contract.response_domain
        exclusions = _parse_exclusions(request.constraints)
        rejected: list[RankedSourceCandidate] = []
        eligible: list[DiscoveryCandidate] = []
        for candidate in request.candidates:
            locked = self._locked_status(candidate)
            excluded_by = _matched_exclusion(locked, exclusions)
            if excluded_by:
                rejected.append(
                    self._ranked(
                        locked,
                        reason=f"用户约束排除 {excluded_by}",
                        reason_code="user_constraint",
                    )
                )
                continue
            if candidate.registry_status == "planned" or candidate.verification_status == "planned":
                rejected.append(
                    self._ranked(locked, reason="来源仍为 planned，不能当作可取数来源。", reason_code="planned_source")
                )
                continue
            eligible.append(locked)

        selected: list[RankedSourceCandidate] = []
        coverage_summary: dict[str, Any] = {
            "hypothesized_required_coverage": 0.0,
            "runtime_verified": False,
            "uncovered_required_fields": list(request.contract.required_fields),
            "note": "覆盖率来自 Registry 能力假说，不是已取数证明。",
        }
        join_risk = ["不自动做患者级 Join。独立来源必须分开分析。"]
        selection_reason = ["选择结果由现有 SourceBroker matcher/selector 计算，v30 不复制集合覆盖算法。"]

        if eligible:
            planning_contract = self._planning_contract(request.contract)
            datasets = [self._dataset(item, request.contract.required_fields) for item in eligible]
            matrix = self.broker.matcher.build_matrix(planning_contract, datasets)
            plan = self.broker.selector.select(planning_contract, datasets, matrix, SourcePlanRequest())
            selected_ids = set(plan.selected_dataset_ids)
            by_id = {item.candidate_id: item for item in eligible}
            for dataset_id in plan.selected_dataset_ids:
                candidate = by_id[dataset_id]
                fields = self._hypothesized_fields(candidate, request.contract.required_fields)
                selected.append(
                    self._ranked(
                        candidate,
                        reason=self._select_reason(candidate, fields),
                        reason_code="hypothesized_coverage",
                        hypothesized_fields=fields,
                    )
                )
            for candidate in eligible:
                if candidate.candidate_id in selected_ids:
                    continue
                fields = self._hypothesized_fields(candidate, request.contract.required_fields)
                rejected.append(
                    self._ranked(
                        candidate,
                        reason="现有 SourceBroker 未将其纳入最小覆盖组合。",
                        reason_code="not_in_cover",
                        hypothesized_fields=fields,
                    )
                )
            coverage_summary = {
                "hypothesized_required_coverage": plan.portfolio_required_field_coverage,
                "runtime_verified": False,
                "uncovered_required_fields": list(plan.uncovered_required_fields),
                "selected_dataset_ids": list(plan.selected_dataset_ids),
                "note": "覆盖率来自 Registry 能力假说与 SourceBroker 规划矩阵，runtime_verified=false。",
            }
            selection_reason.extend(plan.explanation)
            join_risk.extend(f"{item.decision}: {item.reason}" for item in plan.join_policies)
            if len(selected) >= 2 and not any("FORBIDDEN_PATIENT_JOIN" in item for item in join_risk):
                join_risk.append("FORBIDDEN_PATIENT_JOIN: 多个候选视为独立队列，禁止患者级横向 Join。")

        return SelectedSourcePlan(
            selected_candidates=selected,
            rejected_candidates=rejected,
            coverage_summary=coverage_summary,
            selection_reason=selection_reason,
            join_risk=join_risk,
            response_domain=incoming_domain,
            fetched=False,
            integrated=False,
            notice="SelectedSourcePlan 只是来源组合建议，不是真实数据，也不会进入 Integrate。",
        )

    def _dataset(self, candidate: DiscoveryCandidate, required_fields: list[str]) -> DatasetCandidate:
        hints = self._hypothesized_fields(candidate, required_fields)
        return DatasetCandidate(
            dataset_id=candidate.candidate_id,
            source_id=candidate.source_key,
            accession=None,
            title=candidate.source_key,
            source_url=f"registry://{candidate.source_key}",
            field_hints=hints,
            access_mode="OPEN_API" if candidate.verification_status == "unverified" else "UNAVAILABLE",
            capability_status="literature_hint_requires_profiling",
            authority=0.7 if candidate.verification_status == "unverified" else 0.25,
            traceability=0.6,
            structuredness=0.6 if candidate.resource_kind == "official_api" else 0.3,
            cost=0.2,
            declared_granularity=["sample"] if candidate.verification_status == "unverified" else ["publication"],
        )

    def _hypothesized_fields(self, candidate: DiscoveryCandidate, required_fields: list[str]) -> list[str]:
        modalities = {item.casefold() for item in self._modalities(candidate.source_key)}
        matched: list[str] = []
        for field in required_fields:
            aliases = FIELD_TO_MODALITIES.get(field.casefold(), {field.casefold()})
            if aliases & modalities:
                matched.append(field)
        return matched

    def _modalities(self, source_key: str) -> list[str]:
        for item in self.registry.list_sources().sources:
            if item.source_key == source_key:
                return list(item.modalities)
        return []

    @staticmethod
    def _locked_status(candidate: DiscoveryCandidate) -> DiscoveryCandidate:
        status = candidate.verification_status
        if status == "verified":
            status = "unverified"
        if candidate.registry_status in {"catalog_only", "planned"}:
            status = "catalog_only"
        return candidate.model_copy(update={"verification_status": status, "integrate_eligible": False})

    @staticmethod
    def _planning_contract(contract: SelectionContract) -> ResearchContract:
        fields = [
            FieldRequirement(
                field_id=field,
                canonical_name=field,
                label=field,
                role="variable",
                priority=FieldPriority.REQUIRED,
                granularity="unknown",
                data_type="unknown",
                reason="v30 source selection required field",
                evidence_status="missing",
            )
            for field in contract.required_fields
        ]
        if not fields:
            fields = [
                FieldRequirement(
                    field_id="unspecified",
                    canonical_name="unspecified",
                    label="unspecified",
                    role="variable",
                    priority=FieldPriority.REQUIRED,
                    granularity="unknown",
                    data_type="unknown",
                    reason="no required fields supplied",
                    evidence_status="missing",
                )
            ]
        return ResearchContract(
            contract_id=contract.contract_id or "v30-inline-contract",
            topic_id="v30-inline-topic",
            candidate_id="v30-inline-candidate",
            topic=contract.research_goal or contract.domain,
            research_question=contract.research_goal or contract.domain,
            research_type="association",
            population="unspecified",
            exposure="unspecified",
            outcome="unspecified",
            required_fields=fields,
            validation_status="READY_FOR_SOURCE_PLANNING",
            created_at=datetime.now(timezone.utc),
            response_domain=_safe_response_domain(contract.response_domain),
            data_granularity=_safe_granularity(contract.data_granularity),
        )

    @staticmethod
    def _select_reason(candidate: DiscoveryCandidate, fields: list[str]) -> str:
        if candidate.verification_status == "catalog_only":
            joined = "、".join(fields) if fields else "目录能力"
            return f"仅作为 catalog_only 候选保留，假说相关字段：{joined}。不是已核验数据。"
        if fields:
            return f"假说覆盖 { '、'.join(fields) }，尚未取数。"
        return f"纳入 {candidate.source_key} 组合，尚未取数。"

    @staticmethod
    def _ranked(
        candidate: DiscoveryCandidate,
        *,
        reason: str,
        reason_code: str,
        hypothesized_fields: list[str] | None = None,
    ) -> RankedSourceCandidate:
        return RankedSourceCandidate(
            candidate_id=candidate.candidate_id,
            source_key=candidate.source_key,
            verification_status=candidate.verification_status,
            registry_status=candidate.registry_status,
            reason=reason,
            reason_code=reason_code,
            hypothesized_fields=list(hypothesized_fields or []),
            candidate=candidate,
        )


def _safe_response_domain(value: str) -> str:
    if value in {"clinical", "preclinical", "none"}:
        return value
    return "clinical"


def _safe_granularity(value: str) -> str:
    if value in {"patient", "sample", "cell_line", "trial", "publication"}:
        return value
    return "patient"


def _parse_exclusions(constraints: dict[str, Any] | list[str] | None) -> list[str]:
    raw: list[str] = []
    if constraints is None:
        return []
    if isinstance(constraints, list):
        raw.extend(str(item) for item in constraints)
    elif isinstance(constraints, dict):
        for key in ("exclude", "exclude_source_keys", "excluded", "constraints"):
            value = constraints.get(key)
            if isinstance(value, list):
                raw.extend(str(item) for item in value)
            elif isinstance(value, str) and value.strip():
                raw.append(value)
    cleaned: list[str] = []
    for item in raw:
        text = item.strip()
        for prefix in ("排除", "不要", "不用", "禁止"):
            if text.startswith(prefix):
                text = text[len(prefix) :].strip()
        if text:
            cleaned.append(text)
    return cleaned


def _matched_exclusion(candidate: DiscoveryCandidate, exclusions: list[str]) -> str | None:
    blob = " ".join(
        [
            candidate.source_key,
            candidate.candidate_id,
            candidate.source_id,
            candidate.locator.value or "",
            candidate.locator.note or "",
        ]
    ).casefold()
    for token in exclusions:
        if token.casefold() in blob:
            return token
    return None
