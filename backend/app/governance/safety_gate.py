from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field

from backend.app.models import ApiModel
from backend.app.vnext_config import load_vnext_config

from .audit import build_audit_stamp, canonical_hash
from .models import (
    DecisionRecord,
    DecisionSource,
    DecisionStatus,
    EvidenceRecord,
    ReviewRecord,
    RuleOutcome,
    RuleValidation,
)


class SafetyDecisionRequest(ApiModel):
    proposal_id: str = Field(min_length=1)
    task_type: str = Field(min_length=1)
    candidate: dict[str, Any]
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    decision_source: DecisionSource
    model_name: str = "none"
    model_version: str = "not-invoked"
    prompt_version: str = "not-applicable"
    code_revision: str = "working-tree"
    dataset_manifest: str = "inline-request"


class SafetyDecisionResult(ApiModel):
    decision: DecisionRecord
    review_record: ReviewRecord | None = None


class SafetyLayer:
    """Non-bypassable deterministic gate for Agent and algorithm proposals."""

    RULE_VERSION = "0.1"
    SCHEMA_VERSION = "0.1"

    def __init__(self, *, auto_threshold: float | None = None, review_threshold: float | None = None) -> None:
        settings = load_vnext_config().governance
        auto_threshold = settings.auto_confidence_threshold if auto_threshold is None else auto_threshold
        review_threshold = settings.review_confidence_threshold if review_threshold is None else review_threshold
        if not 0 <= review_threshold <= auto_threshold <= 1:
            raise ValueError("thresholds must satisfy 0 <= review <= auto <= 1")
        self.auto_threshold = auto_threshold
        self.review_threshold = review_threshold
        self.RULE_VERSION = settings.rule_version
        self.SCHEMA_VERSION = settings.schema_version

    def evaluate(self, request: SafetyDecisionRequest) -> SafetyDecisionResult:
        checks = self._validate(request)
        outcomes = {item.outcome for item in checks}
        if RuleOutcome.BLOCK in outcomes or request.confidence < self.review_threshold:
            status = DecisionStatus.REJECT
        elif RuleOutcome.REVIEW in outcomes or request.confidence < self.auto_threshold:
            status = DecisionStatus.REVIEW
        else:
            status = DecisionStatus.AUTO

        created_at = datetime.now(timezone.utc)
        output_basis = {
            "proposal_id": request.proposal_id,
            "status": status.value,
            "rules": [item.model_dump(mode="json") for item in checks],
        }
        audit = build_audit_stamp(
            input_value=request,
            output_value=output_basis,
            code_revision=request.code_revision,
            model_name=request.model_name,
            model_version=request.model_version,
            prompt_version=request.prompt_version,
            rule_version=self.RULE_VERSION,
            schema_version=self.SCHEMA_VERSION,
            dataset_manifest=request.dataset_manifest,
        )
        decision = DecisionRecord(
            proposal_id=request.proposal_id,
            task_type=request.task_type,
            candidate=request.candidate,
            confidence=request.confidence,
            evidence=request.evidence,
            decision_source=request.decision_source,
            rule_validation=checks,
            status=status,
            model_version=request.model_version,
            created_at=created_at,
            audit=audit,
        )
        review = None
        if status is DecisionStatus.REVIEW:
            review_rules = [item.rule_id for item in checks if item.outcome is RuleOutcome.REVIEW]
            review = ReviewRecord(
                review_id=f"review:{canonical_hash(output_basis)[:24]}",
                proposal_id=request.proposal_id,
                task_type=request.task_type,
                reason="Proposal requires human review before execution or publication.",
                rule_ids=review_rules,
                created_at=created_at,
            )
        return SafetyDecisionResult(decision=decision, review_record=review)

    def _validate(self, request: SafetyDecisionRequest) -> list[RuleValidation]:
        candidate = request.candidate
        checks = [self._provenance_check(request.evidence)]
        checks.extend((self._her2_check(candidate), self._identity_check(candidate, request.task_type), self._response_domain_check(candidate)))
        return checks

    @staticmethod
    def _provenance_check(evidence: list[EvidenceRecord]) -> RuleValidation:
        complete = bool(evidence)
        return RuleValidation(
            rule_id="MISSING_EVIDENCE",
            outcome=RuleOutcome.PASS if complete else RuleOutcome.BLOCK,
            action="allow" if complete else "block_publish",
            detail="Complete field-level EvidenceRecord is present." if complete else "No complete field-level evidence was supplied.",
        )

    @staticmethod
    def _her2_check(candidate: dict[str, Any]) -> RuleValidation:
        assay = str(candidate.get("her2_assay", "")).upper().strip()
        raw = str(candidate.get("her2_raw_value", candidate.get("raw_value", ""))).upper().replace(" ", "")
        status = str(candidate.get("her2_status", "")).upper().strip()
        cna_conflation = str(candidate.get("source_assay", "")).upper() in {"CNA", "CNV"} and status == "POSITIVE"
        unsafe_ihc = assay == "IHC" and raw in {"2+", "IHC2+", "HER2IHC2+"} and status == "POSITIVE"
        blocked = unsafe_ihc or cna_conflation
        return RuleValidation(
            rule_id="HER2_IHC_2PLUS" if unsafe_ihc else "ERBB2_CNA_NOT_IHC" if cna_conflation else "MEDICAL_SEMANTIC_BOUNDARY",
            outcome=RuleOutcome.BLOCK if blocked else RuleOutcome.PASS,
            action="reject" if blocked else "preserve_dimensions",
            detail="Unsafe HER2/ERBB2 semantic conflation detected." if blocked else "HER2 assay and ERBB2 dimensions remain distinct.",
        )

    @staticmethod
    def _identity_check(candidate: dict[str, Any], task_type: str) -> RuleValidation:
        left_study, right_study = candidate.get("left_study_id"), candidate.get("right_study_id")
        crosswalk = bool(candidate.get("crosswalk_verified"))
        patient_conflict = bool(candidate.get("patient_id_contradiction"))
        sample_conflict = bool(candidate.get("sample_id_contradiction"))
        blocked = patient_conflict or sample_conflict or (left_study and right_study and left_study != right_study and not crosswalk)
        linker_status = str(candidate.get("patient_sample_linker_status", "")).upper()
        linker_required = task_type.casefold() in {"entity_link", "patient_sample_link", "entity_matching"}
        linker_blocked = linker_required and linker_status in {"REJECTED", "REJECT"}
        linker_review = linker_required and (
            not linker_status
            or linker_status in {"UNRESOLVED", "REVIEW", "LINKED_PATIENT_ONLY"}
            or not bool(candidate.get("auto_merge_allowed"))
        )
        outcome = RuleOutcome.BLOCK if blocked or linker_blocked else RuleOutcome.REVIEW if linker_review else RuleOutcome.PASS
        return RuleValidation(
            rule_id="FORBIDDEN_PATIENT_JOIN" if blocked else "PATIENT_SAMPLE_LINKER_GATE" if linker_required else "IDENTITY_BOUNDARY",
            outcome=outcome,
            action="reject" if outcome is RuleOutcome.BLOCK else "review" if outcome is RuleOutcome.REVIEW else "allow_candidate",
            detail=(
                "Identity contradiction or cross-study join without verified crosswalk."
                if blocked or linker_blocked
                else "PatientSampleLinker has not authorized automatic merge."
                if linker_review
                else "No forbidden identity join was detected."
            ),
        )

    @staticmethod
    def _response_domain_check(candidate: dict[str, Any]) -> RuleValidation:
        domain = str(candidate.get("response_domain", ""))
        response_type = str(candidate.get("response_type", "")).casefold()
        preclinical_measure = any(token in response_type for token in ("auc", "ic50", "viability"))
        blocked = preclinical_measure and domain == "clinical"
        return RuleValidation(
            rule_id="CROSS_DOMAIN_RESPONSE",
            outcome=RuleOutcome.BLOCK if blocked else RuleOutcome.PASS,
            action="reject" if blocked else "preserve_domain",
            detail="Preclinical drug sensitivity cannot be represented as patient clinical response." if blocked else "Response domain is internally consistent.",
        )
