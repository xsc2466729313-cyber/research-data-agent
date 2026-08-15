from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Protocol

import yaml

from backend.app.evaluation.models import (
    ErrorGoldCase,
    FieldGoldCase,
    RetrievalGoldCase,
    ReviewStatus,
    RiskLevel,
)
from backend.app.goldset.error_constructor import ErrorCaseConstructor
from backend.app.goldset.errors import (
    GoldSetCurationError,
    GoldSetCurationErrorCode,
)
from backend.app.goldset.models import (
    CurationKind,
    CurationStatus,
    ErrorConstructionRequest,
    ErrorConstructionResult,
    ErrorReviewedDraft,
    ErrorSecondReviewRequest,
    FieldDraft,
    FieldInitialLabelRequest,
    FieldInitialLabelResult,
    FieldReviewedDraft,
    FieldSecondReviewRequest,
    FindingSeverity,
    GoldSetRuleValidationRequest,
    GoldSetRuleValidationResult,
    RetrievalDraft,
    RetrievalInitialLabelRequest,
    RetrievalInitialLabelResult,
    RetrievalReviewedDraft,
    RetrievalSecondReviewRequest,
    ReviewQueueItem,
    RuleFinding,
    SourceReference,
    SourceVerificationResult,
    VerificationStatus,
)
from backend.app.goldset.review_queue import ReviewQueueBuilder
from backend.app.goldset.source_verifier import OfficialSourceVerifier
from backend.app.normalization import DrugNormalizer, GeneNormalizer


ROOT = Path(__file__).resolve().parents[3]


class SourceVerifier(Protocol):
    def verify(self, source: SourceReference) -> SourceVerificationResult: ...


class GoldSetCurationService:
    def __init__(
        self,
        *,
        verifier: SourceVerifier | None = None,
        rules_path: Path | None = None,
        canonical_schema_path: Path | None = None,
        medical_rules_path: Path | None = None,
    ) -> None:
        self.rules_path = rules_path or ROOT / "configs" / "goldset_rules.yaml"
        self.canonical_schema_path = (
            canonical_schema_path or ROOT / "configs" / "canonical_schema.yaml"
        )
        self.medical_rules_path = (
            medical_rules_path or ROOT / "configs" / "medical_rules.yaml"
        )
        self.rules = self._load_yaml(self.rules_path)
        self.canonical_schema = self._load_yaml(self.canonical_schema_path)
        self.medical_rules = self._load_yaml(self.medical_rules_path)
        self.verifier = verifier or OfficialSourceVerifier(rules_path=self.rules_path)
        self.queue_builder = ReviewQueueBuilder()
        self.error_constructor = ErrorCaseConstructor()
        self.gene_normalizer = GeneNormalizer()
        self.drug_normalizer = DrugNormalizer()
        review_rules = self.rules["model_review"]
        self.initial_confidence_min = float(review_rules["initial_confidence_min"])
        self.review_confidence_min = float(
            review_rules["independent_review_confidence_min"]
        )
        curation = self.rules["curation"]
        self.high_risk_fields = set(curation["high_risk_canonical_fields"])
        self.high_risk_error_types = set(curation["high_risk_error_types"])
        self.auto_repair_error_types = set(curation["auto_repair_error_types"])
        self.canonical_fields: dict[str, dict[str, Any]] = self.canonical_schema[
            "fields"
        ]
        self._validate_configuration()

    def verify_source(self, source: SourceReference) -> SourceVerificationResult:
        return self.verifier.verify(source)

    def initial_label_retrieval(
        self,
        request: RetrievalInitialLabelRequest,
    ) -> RetrievalInitialLabelResult:
        self._require_unique(
            [(row.question_id, row.source.accession) for row in request.proposals],
            "retrieval question/accession pairs",
        )
        verifications: dict[tuple[str, str, str, str], SourceVerificationResult] = {}
        drafts: list[RetrievalDraft] = []
        queue: list[ReviewQueueItem] = []
        for proposal in request.proposals:
            verification = self._verify_cached(proposal.source, verifications)
            reasons = self._initial_reasons(verification, proposal.confidence)
            draft_id = self._id(
                "retrieval-draft",
                proposal.question_id,
                proposal.source.accession,
            )
            draft = RetrievalDraft(
                draft_id=draft_id,
                primary_model_id=request.model_id,
                question_id=proposal.question_id,
                research_question=proposal.research_question,
                dataset_id=proposal.source.accession,
                proposed_label=proposal.proposed_label,
                confidence=proposal.confidence,
                rationale=proposal.rationale,
                source_verification=verification,
                status=(
                    CurationStatus.HUMAN_REVIEW_REQUIRED
                    if reasons
                    else CurationStatus.INITIAL_LABELED
                ),
            )
            drafts.append(draft)
            if reasons:
                queue.append(
                    self.queue_builder.build(
                        kind=CurationKind.RETRIEVAL,
                        case_id=draft_id,
                        source_id=proposal.source.source_id,
                        reasons=reasons,
                    )
                )
        return RetrievalInitialLabelResult(
            drafts=drafts,
            review_queue=queue,
            notice=(
                "Primary-model labels are proposals only. Every draft still requires "
                "an independent second-model review and deterministic validation."
            ),
        )

    def initial_label_fields(
        self,
        request: FieldInitialLabelRequest,
    ) -> FieldInitialLabelResult:
        self._require_unique(
            [row.case_id for row in request.proposals],
            "field case IDs",
        )
        verifications: dict[tuple[str, str, str, str], SourceVerificationResult] = {}
        drafts: list[FieldDraft] = []
        queue: list[ReviewQueueItem] = []
        for proposal in request.proposals:
            verification = self._verify_cached(proposal.source, verifications)
            reasons = self._initial_reasons(verification, proposal.confidence)
            if proposal.proposed_canonical_field in self.high_risk_fields:
                reasons.append("high_risk_medical_field")
            draft = FieldDraft(
                draft_id=self._id("field-draft", proposal.case_id),
                primary_model_id=request.model_id,
                case_id=proposal.case_id,
                source_dataset=proposal.source.accession,
                raw_field=proposal.raw_field,
                raw_value=proposal.raw_value,
                proposed_canonical_field=proposal.proposed_canonical_field,
                proposed_canonical_value=proposal.proposed_canonical_value,
                allowed_auto_transform=proposal.allowed_auto_transform,
                companion_fields=proposal.companion_fields,
                confidence=proposal.confidence,
                rationale=proposal.rationale,
                source_verification=verification,
                status=(
                    CurationStatus.HUMAN_REVIEW_REQUIRED
                    if reasons
                    else CurationStatus.INITIAL_LABELED
                ),
            )
            drafts.append(draft)
            if reasons:
                queue.append(
                    self.queue_builder.build(
                        kind=CurationKind.FIELD,
                        case_id=proposal.case_id,
                        source_id=proposal.source.source_id,
                        reasons=reasons,
                    )
                )
        return FieldInitialLabelResult(
            drafts=drafts,
            review_queue=queue,
            notice=(
                "Field labels remain pending proposals. High-risk medical fields are "
                "routed to human review even when model confidence is high."
            ),
        )

    def construct_error_cases(
        self,
        request: ErrorConstructionRequest,
    ) -> ErrorConstructionResult:
        self._require_unique([seed.record_id for seed in request.seeds], "error seed IDs")
        verifications: dict[tuple[str, str, str, str], SourceVerificationResult] = {}
        drafts = []
        skipped: list[str] = []
        queue: list[ReviewQueueItem] = []
        for seed in request.seeds:
            verification = self._verify_cached(seed.source, verifications)
            seed_drafts, seed_skipped = self.error_constructor.construct(
                seed,
                verification,
                high_risk_types=self.high_risk_error_types,
                auto_repair_types=self.auto_repair_error_types,
            )
            drafts.extend(seed_drafts)
            skipped.extend(seed_skipped)
            for draft in seed_drafts:
                reasons: list[str] = []
                if verification.status != VerificationStatus.VERIFIED:
                    reasons.append("source_unverified")
                if draft.error_type in self.high_risk_error_types:
                    reasons.append(f"high_risk_error:{draft.error_type}")
                if reasons:
                    queue.append(
                        self.queue_builder.build(
                            kind=CurationKind.ERROR,
                            case_id=draft.draft_id,
                            source_id=seed.source.source_id,
                            reasons=reasons,
                        )
                    )
        return ErrorConstructionResult(
            drafts=drafts,
            skipped_mutations=skipped,
            review_queue=self._deduplicate_queue(queue),
            notice=(
                "Generated records are explicitly synthetic perturbations of supplied "
                "source-backed seeds. They are not approved Gold until independently "
                "reviewed and rule-validated."
            ),
        )

    def review_retrieval(
        self,
        request: RetrievalSecondReviewRequest,
    ) -> RetrievalReviewedDraft:
        refreshed_draft = request.draft.model_copy(
            update={
                "source_verification": self.verifier.verify(
                    request.draft.source_verification.source
                )
            }
        )
        self._require_independent(
            refreshed_draft.primary_model_id,
            request.reviewer_model_id,
        )
        agreement = request.reviewed_label == refreshed_draft.proposed_label
        status = self._review_status(
            draft_confidence=refreshed_draft.confidence,
            review_confidence=request.confidence,
            source_status=refreshed_draft.source_verification.status,
            agreement=agreement,
        )
        return RetrievalReviewedDraft(
            draft=refreshed_draft,
            reviewer_model_id=request.reviewer_model_id,
            reviewed_label=request.reviewed_label,
            confidence=request.confidence,
            rationale=request.rationale,
            agreement=agreement,
            status=status,
        )

    def review_field(self, request: FieldSecondReviewRequest) -> FieldReviewedDraft:
        refreshed_draft = request.draft.model_copy(
            update={
                "source_verification": self.verifier.verify(
                    request.draft.source_verification.source
                )
            }
        )
        self._require_independent(
            refreshed_draft.primary_model_id,
            request.reviewer_model_id,
        )
        agreement = (
            request.reviewed_canonical_field
            == refreshed_draft.proposed_canonical_field
            and request.reviewed_canonical_value
            == refreshed_draft.proposed_canonical_value
            and request.preserves_medical_meaning
        )
        status = self._review_status(
            draft_confidence=refreshed_draft.confidence,
            review_confidence=request.confidence,
            source_status=refreshed_draft.source_verification.status,
            agreement=agreement,
            high_risk=(
                refreshed_draft.proposed_canonical_field in self.high_risk_fields
            ),
        )
        return FieldReviewedDraft(
            draft=refreshed_draft,
            reviewer_model_id=request.reviewer_model_id,
            reviewed_canonical_field=request.reviewed_canonical_field,
            reviewed_canonical_value=request.reviewed_canonical_value,
            preserves_medical_meaning=request.preserves_medical_meaning,
            confidence=request.confidence,
            rationale=request.rationale,
            agreement=agreement,
            status=status,
        )

    def review_error(self, request: ErrorSecondReviewRequest) -> ErrorReviewedDraft:
        refreshed_draft = request.draft.model_copy(
            update={
                "source_verification": self.verifier.verify(
                    request.draft.source_verification.source
                )
            }
        )
        self._require_independent(
            refreshed_draft.primary_actor_id,
            request.reviewer_model_id,
        )
        agreement = (
            request.reviewed_error_type == refreshed_draft.error_type
            and request.reviewed_expected_detection == refreshed_draft.expected_detection
            and request.reviewed_expected_repair == refreshed_draft.expected_repair
            and request.reviewed_auto_repair_allowed
            == refreshed_draft.auto_repair_allowed
        )
        status = self._review_status(
            draft_confidence=1.0,
            review_confidence=request.confidence,
            source_status=refreshed_draft.source_verification.status,
            agreement=agreement,
            high_risk=(refreshed_draft.error_type in self.high_risk_error_types),
        )
        return ErrorReviewedDraft(
            draft=refreshed_draft,
            reviewer_model_id=request.reviewer_model_id,
            reviewed_error_type=request.reviewed_error_type,
            reviewed_expected_detection=request.reviewed_expected_detection,
            reviewed_expected_repair=request.reviewed_expected_repair,
            reviewed_auto_repair_allowed=request.reviewed_auto_repair_allowed,
            confidence=request.confidence,
            rationale=request.rationale,
            agreement=agreement,
            status=status,
        )

    def validate_rules(
        self,
        request: GoldSetRuleValidationRequest,
    ) -> GoldSetRuleValidationResult:
        retrieval_gold: list[RetrievalGoldCase] = []
        field_gold: list[FieldGoldCase] = []
        error_gold: list[ErrorGoldCase] = []
        findings: list[RuleFinding] = []
        queue: list[ReviewQueueItem] = []
        verifications: dict[tuple[str, str, str, str], SourceVerificationResult] = {}

        for submitted in request.retrieval:
            reviewed = self._refresh_retrieval_review(submitted, verifications)
            case_findings, reasons = self._validate_retrieval(reviewed)
            findings.extend(case_findings)
            status = ReviewStatus.PENDING if reasons else ReviewStatus.APPROVED
            retrieval_gold.append(
                RetrievalGoldCase(
                    question_id=reviewed.draft.question_id,
                    research_question=reviewed.draft.research_question,
                    dataset_id=reviewed.draft.dataset_id,
                    label=reviewed.draft.proposed_label,
                    label_source=self._label_source(
                        reviewed.draft.primary_model_id,
                        reviewed.reviewer_model_id,
                    ),
                    review_status=status,
                    notes=self._notes(reviewed.draft.draft_id, reviewed.draft.source_verification),
                )
            )
            if reasons:
                queue.append(
                    self.queue_builder.build(
                        kind=CurationKind.RETRIEVAL,
                        case_id=reviewed.draft.draft_id,
                        source_id=reviewed.draft.source_verification.source.source_id,
                        reasons=reasons,
                    )
                )

        for submitted in request.fields:
            reviewed = self._refresh_field_review(submitted, verifications)
            case_findings, reasons = self._validate_field(reviewed)
            findings.extend(case_findings)
            status = ReviewStatus.PENDING if reasons else ReviewStatus.APPROVED
            field_gold.append(
                FieldGoldCase(
                    case_id=reviewed.draft.case_id,
                    source_dataset=reviewed.draft.source_dataset,
                    raw_field=reviewed.draft.raw_field,
                    raw_value=reviewed.draft.raw_value,
                    canonical_field=reviewed.draft.proposed_canonical_field,
                    canonical_value=reviewed.draft.proposed_canonical_value,
                    allowed_auto_transform=reviewed.draft.allowed_auto_transform,
                    label_source=self._label_source(
                        reviewed.draft.primary_model_id,
                        reviewed.reviewer_model_id,
                    ),
                    review_status=status,
                    notes=self._notes(reviewed.draft.draft_id, reviewed.draft.source_verification),
                )
            )
            if reasons:
                queue.append(
                    self.queue_builder.build(
                        kind=CurationKind.FIELD,
                        case_id=reviewed.draft.case_id,
                        source_id=reviewed.draft.source_verification.source.source_id,
                        reasons=reasons,
                    )
                )

        for submitted in request.errors:
            reviewed = self._refresh_error_review(submitted, verifications)
            case_findings, reasons = self._validate_error(reviewed)
            findings.extend(case_findings)
            status = ReviewStatus.PENDING if reasons else ReviewStatus.APPROVED
            error_gold.append(
                ErrorGoldCase(
                    case_id=reviewed.draft.draft_id,
                    error_type=reviewed.draft.error_type,
                    original_record=reviewed.draft.original_record,
                    expected_detection=reviewed.draft.expected_detection,
                    expected_repair=reviewed.draft.expected_repair,
                    auto_repair_allowed=reviewed.draft.auto_repair_allowed,
                    risk_level=reviewed.draft.risk_level,
                    review_status=status,
                    notes=self._notes(reviewed.draft.draft_id, reviewed.draft.source_verification),
                )
            )
            if reasons:
                queue.append(
                    self.queue_builder.build(
                        kind=CurationKind.ERROR,
                        case_id=reviewed.draft.draft_id,
                        source_id=reviewed.draft.source_verification.source.source_id,
                        reasons=reasons,
                    )
                )

        queue = self._deduplicate_queue(queue)
        approved_count = sum(
            row.review_status == ReviewStatus.APPROVED
            for row in [*retrieval_gold, *field_gold, *error_gold]
        )
        total_count = len(retrieval_gold) + len(field_gold) + len(error_gold)
        freeze_eligible = (
            bool(retrieval_gold and field_gold and error_gold)
            and approved_count == total_count
            and not queue
        )
        return GoldSetRuleValidationResult(
            retrieval_gold=retrieval_gold,
            field_gold=field_gold,
            error_gold=error_gold,
            findings=findings,
            review_queue=queue,
            summary={
                "total_count": total_count,
                "approved_count": approved_count,
                "pending_count": total_count - approved_count,
                "review_queue_count": len(queue),
                "source_failures": sum(
                    finding.rule_id == "SOURCE_VERIFIED" and not finding.passed
                    for finding in findings
                ),
            },
            freeze_eligible=freeze_eligible,
            notice=(
                "freeze_eligible only means dual review, source verification, and rules "
                "passed. A versioned GoldSetManifest and checksum are still required by "
                "the stage 07 evaluator; queued cases require human adjudication first."
            ),
        )

    def _validate_retrieval(
        self,
        reviewed: RetrievalReviewedDraft,
    ) -> tuple[list[RuleFinding], list[str]]:
        draft = reviewed.draft
        case_id = draft.draft_id
        checks = [
            (
                "SOURCE_VERIFIED",
                draft.source_verification.status == VerificationStatus.VERIFIED,
                FindingSeverity.ERROR,
                "Dataset accession was verified against its official source.",
                "source_unverified",
            ),
            (
                "INDEPENDENT_MODEL_AGREEMENT",
                reviewed.agreement,
                FindingSeverity.WARNING,
                "Independent model label agrees with the primary proposal.",
                "model_disagreement",
            ),
            (
                "MODEL_CONFIDENCE",
                draft.confidence >= self.initial_confidence_min
                and reviewed.confidence >= self.review_confidence_min,
                FindingSeverity.WARNING,
                "Both model confidence values meet the curation threshold.",
                "low_model_confidence",
            ),
        ]
        return self._checks(CurationKind.RETRIEVAL, case_id, checks)

    def _validate_field(
        self,
        reviewed: FieldReviewedDraft,
    ) -> tuple[list[RuleFinding], list[str]]:
        draft = reviewed.draft
        field = draft.proposed_canonical_field
        value = draft.proposed_canonical_value
        field_config = self.canonical_fields.get(field)
        allowed_values = field_config.get("allowed") if field_config else None
        normalized_raw_field = re.sub(
            r"[^A-Z0-9]+", "_", draft.raw_field.upper()
        ).strip("_")
        compact_raw_value = draft.raw_value.replace(" ", "").upper()
        is_her2_ihc_2plus = (
            "HER2" in normalized_raw_field
            and "IHC" in normalized_raw_field
            and compact_raw_value in {"2", "2+", "IHC2+", "HER2IHC2+"}
        )
        is_erbb2_cna = (
            ("ERBB2" in normalized_raw_field or "HER2" in normalized_raw_field)
            and any(
                token in normalized_raw_field
                for token in ("CNA", "CNV", "COPY_NUMBER", "AMPLIFICATION")
            )
        )
        response_measure = any(
            token in normalized_raw_field for token in ("AUC", "IC50", "VIABILITY")
        )
        response_domain = draft.companion_fields.get("response_domain")
        auto_transform_valid = self._auto_transform_valid(draft)
        checks = [
            (
                "SOURCE_VERIFIED",
                draft.source_verification.status == VerificationStatus.VERIFIED,
                FindingSeverity.ERROR,
                "Source dataset was verified against its official source.",
                "source_unverified",
            ),
            (
                "INDEPENDENT_MODEL_AGREEMENT",
                reviewed.agreement and reviewed.preserves_medical_meaning,
                FindingSeverity.WARNING,
                "Independent model agrees and confirms preserved medical meaning.",
                "model_disagreement_or_semantic_change",
            ),
            (
                "MODEL_CONFIDENCE",
                draft.confidence >= self.initial_confidence_min
                and reviewed.confidence >= self.review_confidence_min,
                FindingSeverity.WARNING,
                "Both model confidence values meet the curation threshold.",
                "low_model_confidence",
            ),
            (
                "CANONICAL_FIELD_EXISTS",
                field_config is not None,
                FindingSeverity.ERROR,
                "Canonical field exists in the frozen schema.",
                "schema_field_invalid",
            ),
            (
                "CANONICAL_VALUE_ALLOWED",
                allowed_values is None or value in {str(item) for item in allowed_values},
                FindingSeverity.ERROR,
                "Canonical value is valid for the frozen field enum.",
                "schema_value_invalid",
            ),
            (
                "HER2_IHC_2PLUS",
                not (is_her2_ihc_2plus and field == "her2_status" and value == "Positive"),
                FindingSeverity.ERROR,
                "HER2 IHC 2+ is not mapped directly to Positive.",
                "medical_rule:HER2_IHC_2PLUS",
            ),
            (
                "ERBB2_CNA_NOT_IHC",
                not (is_erbb2_cna and field in {"her2_status", "her2_assay"}),
                FindingSeverity.ERROR,
                "ERBB2 CNA is kept separate from HER2 assay/status.",
                "medical_rule:ERBB2_CNA_NOT_IHC",
            ),
            (
                "CROSS_DOMAIN_RESPONSE",
                not response_measure
                or (
                    field in {"response", "response_type", "response_domain"}
                    and (
                        (field == "response_domain" and value == "preclinical_cell_line")
                        or response_domain == "preclinical_cell_line"
                    )
                ),
                FindingSeverity.ERROR,
                "AUC/IC50/viability is explicitly scoped to preclinical_cell_line.",
                "medical_rule:CROSS_DOMAIN_RESPONSE",
            ),
            (
                "AUTO_TRANSFORM_ALLOWLIST",
                not draft.allowed_auto_transform or auto_transform_valid,
                FindingSeverity.WARNING,
                "Automatic transform is supported by a deterministic allowlisted rule.",
                "auto_transform_not_allowlisted",
            ),
        ]
        findings, reasons = self._checks(CurationKind.FIELD, draft.case_id, checks)
        if field in self.high_risk_fields:
            reasons.append("high_risk_medical_field")
            findings.append(
                RuleFinding(
                    rule_id="HIGH_RISK_HUMAN_REVIEW",
                    kind=CurationKind.FIELD,
                    case_id=draft.case_id,
                    severity=FindingSeverity.WARNING,
                    passed=False,
                    message="High-risk canonical field requires human adjudication.",
                )
            )
        return findings, list(dict.fromkeys(reasons))

    def _validate_error(
        self,
        reviewed: ErrorReviewedDraft,
    ) -> tuple[list[RuleFinding], list[str]]:
        draft = reviewed.draft
        auto_repair_valid = (
            not draft.auto_repair_allowed
            or draft.error_type in self.auto_repair_error_types
        ) and not (
            draft.risk_level == RiskLevel.HIGH and draft.auto_repair_allowed
        )
        clean_control_valid = (
            draft.error_type != "clean_control"
            or (
                not draft.expected_detection
                and draft.expected_repair is None
                and not draft.auto_repair_allowed
            )
        )
        construction_integrity = self._error_construction_integrity(draft)
        checks = [
            (
                "SOURCE_VERIFIED",
                draft.source_verification.status == VerificationStatus.VERIFIED,
                FindingSeverity.ERROR,
                "Error seed source was verified against its official source.",
                "source_unverified",
            ),
            (
                "INDEPENDENT_MODEL_AGREEMENT",
                reviewed.agreement,
                FindingSeverity.WARNING,
                "Independent model agrees with error type and expected repair.",
                "model_disagreement",
            ),
            (
                "MODEL_CONFIDENCE",
                reviewed.confidence >= self.review_confidence_min,
                FindingSeverity.WARNING,
                "Independent review confidence meets the curation threshold.",
                "low_model_confidence",
            ),
            (
                "ERROR_CONSTRUCTION_INTEGRITY",
                construction_integrity,
                FindingSeverity.ERROR,
                "Synthetic error exactly matches an allowlisted deterministic mutation.",
                "invalid_error_construction",
            ),
            (
                "AUTO_REPAIR_ALLOWLIST",
                auto_repair_valid,
                FindingSeverity.ERROR,
                "Automatic repair is restricted to configured deterministic low-risk types.",
                "auto_repair_not_allowlisted",
            ),
            (
                "CLEAN_CONTROL_INVARIANT",
                clean_control_valid,
                FindingSeverity.ERROR,
                "Clean controls have no expected detection or repair.",
                "invalid_clean_control",
            ),
        ]
        findings, reasons = self._checks(CurationKind.ERROR, draft.draft_id, checks)
        if draft.error_type in self.high_risk_error_types:
            reasons.append(f"high_risk_error:{draft.error_type}")
            findings.append(
                RuleFinding(
                    rule_id="HIGH_RISK_HUMAN_REVIEW",
                    kind=CurationKind.ERROR,
                    case_id=draft.draft_id,
                    severity=FindingSeverity.WARNING,
                    passed=False,
                    message="High-risk error case requires human adjudication.",
                )
            )
        return findings, list(dict.fromkeys(reasons))

    def _auto_transform_valid(self, draft: FieldDraft) -> bool:
        field = draft.proposed_canonical_field
        expected = draft.proposed_canonical_value
        if field == "gene":
            normalized = self.gene_normalizer.normalize(draft.raw_value)
            return normalized.values.get("gene") == expected and normalized.confidence >= 0.98
        if field == "drug":
            normalized = self.drug_normalizer.normalize(draft.raw_value)
            return normalized.values.get("drug") == expected and normalized.confidence >= 0.98
        if draft.raw_value != expected and draft.raw_value.casefold() == expected.casefold():
            return "casing_normalization" in self.medical_rules["auto_fix"]
        return draft.raw_value == expected

    @staticmethod
    def _checks(
        kind: CurationKind,
        case_id: str,
        checks: list[tuple[str, bool, FindingSeverity, str, str]],
    ) -> tuple[list[RuleFinding], list[str]]:
        findings: list[RuleFinding] = []
        reasons: list[str] = []
        for rule_id, passed, severity, message, reason in checks:
            findings.append(
                RuleFinding(
                    rule_id=rule_id,
                    kind=kind,
                    case_id=case_id,
                    severity=severity,
                    passed=passed,
                    message=message if passed else f"FAILED: {message}",
                )
            )
            if not passed:
                reasons.append(reason)
        return findings, reasons

    def _review_status(
        self,
        *,
        draft_confidence: float,
        review_confidence: float,
        source_status: VerificationStatus,
        agreement: bool,
        high_risk: bool = False,
    ) -> CurationStatus:
        if (
            source_status != VerificationStatus.VERIFIED
            or not agreement
            or draft_confidence < self.initial_confidence_min
            or review_confidence < self.review_confidence_min
            or high_risk
        ):
            return CurationStatus.HUMAN_REVIEW_REQUIRED
        return CurationStatus.SECOND_REVIEWED

    def _initial_reasons(
        self,
        verification: SourceVerificationResult,
        confidence: float,
    ) -> list[str]:
        reasons = []
        if verification.status != VerificationStatus.VERIFIED:
            reasons.append("source_unverified")
        if confidence < self.initial_confidence_min:
            reasons.append("low_model_confidence")
        return reasons

    def _verify_cached(
        self,
        source: SourceReference,
        cache: dict[tuple[str, str, str, str], SourceVerificationResult],
    ) -> SourceVerificationResult:
        key = (
            source.source_id,
            source.source_database.value,
            source.accession,
            source.url,
        )
        if key not in cache:
            cache[key] = self.verifier.verify(source)
        return cache[key]

    def _refresh_retrieval_review(
        self,
        reviewed: RetrievalReviewedDraft,
        cache: dict[tuple[str, str, str, str], SourceVerificationResult],
    ) -> RetrievalReviewedDraft:
        self._require_independent(
            reviewed.draft.primary_model_id,
            reviewed.reviewer_model_id,
        )
        verification = self._verify_cached(
            reviewed.draft.source_verification.source,
            cache,
        )
        draft = reviewed.draft.model_copy(
            update={"source_verification": verification}
        )
        agreement = reviewed.reviewed_label == draft.proposed_label
        return reviewed.model_copy(
            update={
                "draft": draft,
                "agreement": agreement,
                "status": self._review_status(
                    draft_confidence=draft.confidence,
                    review_confidence=reviewed.confidence,
                    source_status=verification.status,
                    agreement=agreement,
                ),
            }
        )

    def _refresh_field_review(
        self,
        reviewed: FieldReviewedDraft,
        cache: dict[tuple[str, str, str, str], SourceVerificationResult],
    ) -> FieldReviewedDraft:
        self._require_independent(
            reviewed.draft.primary_model_id,
            reviewed.reviewer_model_id,
        )
        verification = self._verify_cached(
            reviewed.draft.source_verification.source,
            cache,
        )
        draft = reviewed.draft.model_copy(
            update={"source_verification": verification}
        )
        agreement = (
            reviewed.reviewed_canonical_field == draft.proposed_canonical_field
            and reviewed.reviewed_canonical_value == draft.proposed_canonical_value
            and reviewed.preserves_medical_meaning
        )
        return reviewed.model_copy(
            update={
                "draft": draft,
                "agreement": agreement,
                "status": self._review_status(
                    draft_confidence=draft.confidence,
                    review_confidence=reviewed.confidence,
                    source_status=verification.status,
                    agreement=agreement,
                    high_risk=(
                        draft.proposed_canonical_field in self.high_risk_fields
                    ),
                ),
            }
        )

    def _refresh_error_review(
        self,
        reviewed: ErrorReviewedDraft,
        cache: dict[tuple[str, str, str, str], SourceVerificationResult],
    ) -> ErrorReviewedDraft:
        self._require_independent(
            reviewed.draft.primary_actor_id,
            reviewed.reviewer_model_id,
        )
        verification = self._verify_cached(
            reviewed.draft.source_verification.source,
            cache,
        )
        draft = reviewed.draft.model_copy(
            update={"source_verification": verification}
        )
        agreement = (
            reviewed.reviewed_error_type == draft.error_type
            and reviewed.reviewed_expected_detection == draft.expected_detection
            and reviewed.reviewed_expected_repair == draft.expected_repair
            and reviewed.reviewed_auto_repair_allowed == draft.auto_repair_allowed
        )
        return reviewed.model_copy(
            update={
                "draft": draft,
                "agreement": agreement,
                "status": self._review_status(
                    draft_confidence=1.0,
                    review_confidence=reviewed.confidence,
                    source_status=verification.status,
                    agreement=agreement,
                    high_risk=(draft.error_type in self.high_risk_error_types),
                ),
            }
        )

    @staticmethod
    def _error_construction_integrity(draft) -> bool:
        try:
            observed = json.loads(draft.original_record)
            expected = (
                json.loads(draft.expected_repair)
                if draft.expected_repair is not None
                else None
            )
        except (TypeError, json.JSONDecodeError):
            return False
        source_id = draft.source_verification.source.source_id
        if draft.error_type == "clean_control":
            return (
                isinstance(observed, dict)
                and observed.get("source_id") == source_id
                and expected is None
                and not draft.expected_detection
                and not draft.auto_repair_allowed
            )
        if not isinstance(expected, dict) or not draft.expected_detection:
            return False
        if draft.error_type == "duplicate":
            observed_rows = observed.get("records") if isinstance(observed, dict) else None
            expected_rows = expected.get("records")
            return (
                isinstance(observed_rows, list)
                and len(observed_rows) == 2
                and observed_rows[0] == observed_rows[1]
                and expected_rows == [observed_rows[0]]
                and observed_rows[0].get("source_id") == source_id
            )
        if draft.error_type == "missing":
            if not isinstance(observed, dict) or expected.get("source_id") != source_id:
                return False
            missing = set(expected) - set(observed)
            return (
                len(missing) == 1
                and missing <= {"study_id", "disease", "raw_field", "raw_value"}
                and all(observed.get(key) == value for key, value in expected.items() if key in observed)
            )
        if draft.error_type == "gene_alias":
            aliases = {"ERBB2": "HER2", "TP53": "P53"}
            return GoldSetCurationService._single_field_mutation(
                observed,
                expected,
                "gene",
                aliases.get(str(expected.get("gene", "")).upper()),
                source_id,
            )
        if draft.error_type == "drug_alias":
            aliases = {
                "Trastuzumab": "Herceptin",
                "Pertuzumab": "Perjeta",
                "Alpelisib": "Piqray",
                "Fulvestrant": "Faslodex",
            }
            return GoldSetCurationService._single_field_mutation(
                observed,
                expected,
                "drug",
                aliases.get(str(expected.get("drug", ""))),
                source_id,
            )
        if draft.error_type == "schema_mapping_error":
            if not isinstance(observed, dict) or expected.get("source_id") != source_id:
                return False
            gene_to_drug = (
                "gene" in expected
                and "drug" not in expected
                and "gene" not in observed
                and observed.get("drug") == expected.get("gene")
            )
            drug_to_gene = (
                "drug" in expected
                and "gene" not in expected
                and "drug" not in observed
                and observed.get("gene") == expected.get("drug")
            )
            if not (gene_to_drug or drug_to_gene):
                return False
            ignored = {"gene", "drug"}
            return all(
                observed.get(key) == value
                for key, value in expected.items()
                if key not in ignored
            )
        if draft.error_type == "her2_assay_error":
            return (
                isinstance(observed, dict)
                and expected.get("source_id") == source_id
                and str(observed.get("her2_assay", "")).upper() == "IHC"
                and str(observed.get("her2_raw_value", "")).replace(" ", "")
                in {"2", "2+"}
                and observed.get("her2_status") == "Positive"
                and expected.get("her2_status") == "Equivocal"
                and GoldSetCurationService._equal_except(
                    observed, expected, {"her2_status"}
                )
            )
        if draft.error_type == "provenance_missing":
            return (
                isinstance(observed, dict)
                and "source_id" not in observed
                and expected.get("source_id") == source_id
                and GoldSetCurationService._equal_except(
                    observed, expected, {"source_id"}
                )
            )
        if draft.error_type == "patient_sample_conflict":
            expected_sample = expected.get("sample_id")
            return (
                isinstance(observed, dict)
                and expected.get("source_id") == source_id
                and isinstance(expected_sample, str)
                and observed.get("sample_id") == f"{expected_sample}__CONFLICT__"
                and GoldSetCurationService._equal_except(
                    observed, expected, {"sample_id"}
                )
            )
        return False

    @staticmethod
    def _single_field_mutation(
        observed: Any,
        expected: dict,
        field: str,
        mutated_value: str | None,
        source_id: str,
    ) -> bool:
        return (
            isinstance(observed, dict)
            and mutated_value is not None
            and expected.get("source_id") == source_id
            and observed.get(field) == mutated_value
            and GoldSetCurationService._equal_except(observed, expected, {field})
        )

    @staticmethod
    def _equal_except(left: dict, right: dict, ignored: set[str]) -> bool:
        return {
            key: value for key, value in left.items() if key not in ignored
        } == {key: value for key, value in right.items() if key not in ignored}

    def _validate_configuration(self) -> None:
        if self.canonical_schema.get("frozen") is not True:
            raise GoldSetCurationError(
                GoldSetCurationErrorCode.INVALID_CONFIGURATION,
                "Gold Set curation requires a frozen canonical schema.",
            )
        if not 0 <= self.initial_confidence_min <= 1 or not 0 <= self.review_confidence_min <= 1:
            raise GoldSetCurationError(
                GoldSetCurationErrorCode.INVALID_CONFIGURATION,
                "Gold Set confidence thresholds must be between 0 and 1.",
            )
        medical_auto_fix = set(self.medical_rules.get("auto_fix", []))
        required_medical_rules = {
            "duplicate": "exact_duplicate",
            "gene_alias": "gene_alias_exact",
            "drug_alias": "drug_alias_exact",
        }
        unauthorized = sorted(
            error_type
            for error_type in self.auto_repair_error_types
            if required_medical_rules.get(error_type) not in medical_auto_fix
        )
        if unauthorized:
            raise GoldSetCurationError(
                GoldSetCurationErrorCode.INVALID_CONFIGURATION,
                "Gold Set auto-repair cases exceed the medical auto-fix allowlist.",
                details={"error_types": unauthorized},
            )

    @staticmethod
    def _require_independent(primary_id: str, reviewer_id: str) -> None:
        if primary_id.casefold() == reviewer_id.casefold():
            raise GoldSetCurationError(
                GoldSetCurationErrorCode.INVALID_REVIEWER,
                "Independent review must use a different model or actor ID.",
                details={"primary_id": primary_id, "reviewer_id": reviewer_id},
            )

    @staticmethod
    def _require_unique(values: list[Any], label: str) -> None:
        seen: set[Any] = set()
        duplicates: list[str] = []
        for value in values:
            if value in seen and str(value) not in duplicates:
                duplicates.append(str(value))
            seen.add(value)
        if duplicates:
            raise GoldSetCurationError(
                GoldSetCurationErrorCode.INVALID_REQUEST,
                f"Duplicate {label} are not allowed.",
                details={"duplicates": duplicates},
            )

    @staticmethod
    def _id(prefix: str, *parts: str) -> str:
        material = "|".join(parts).encode("utf-8")
        return f"{prefix}:{hashlib.sha256(material).hexdigest()[:24]}"

    def _label_source(self, primary: str, reviewer: str) -> str:
        return (
            f"primary_model:{primary};independent_model:{reviewer};"
            f"rules:goldset_rules_v{self.rules['version']}"
        )

    @staticmethod
    def _notes(draft_id: str, verification: SourceVerificationResult) -> str:
        return (
            f"draft_id={draft_id};source_verification={verification.verification_id};"
            f"checked_url={verification.checked_url or verification.source.url}"
        )

    @staticmethod
    def _deduplicate_queue(queue: list[ReviewQueueItem]) -> list[ReviewQueueItem]:
        return list({item.queue_id: item for item in queue}.values())

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("top-level YAML value must be an object")
            return value
        except (OSError, ValueError, yaml.YAMLError) as exc:
            raise GoldSetCurationError(
                GoldSetCurationErrorCode.INVALID_CONFIGURATION,
                "Cannot load Gold Set curation configuration.",
                details={"path": str(path), "error": str(exc)},
            ) from exc
