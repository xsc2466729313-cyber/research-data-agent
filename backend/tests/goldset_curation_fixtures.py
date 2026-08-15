from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from backend.app.goldset.models import (
    FieldInitialLabelRequest,
    FieldLabelProposal,
    RetrievalInitialLabelRequest,
    RetrievalLabelProposal,
    SourceReference,
    SourceVerificationResult,
    VerificationStatus,
)


def gdc_source(*, source_id: str = "gdc:TCGA-BRCA") -> SourceReference:
    return SourceReference(
        source_id=source_id,
        source_database="gdc",
        accession="TCGA-BRCA",
        url="https://api.gdc.cancer.gov/projects/TCGA-BRCA",
    )


class StubSourceVerifier:
    def verify(self, source: SourceReference) -> SourceVerificationResult:
        verified = "unverified" not in source.source_id
        digest = hashlib.sha256(source.accession.encode("utf-8")).hexdigest()
        return SourceVerificationResult(
            verification_id=f"fixture-verification:{digest[:24]}",
            source=source,
            status=(
                VerificationStatus.VERIFIED
                if verified
                else VerificationStatus.FAILED
            ),
            checked_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            checked_url=source.url,
            http_status=200 if verified else 404,
            response_sha256=digest,
            reason=(
                "fixture official source verified"
                if verified
                else "fixture official source missing"
            ),
        )


def retrieval_request(
    *,
    source: SourceReference | None = None,
    confidence: float = 0.96,
) -> RetrievalInitialLabelRequest:
    return RetrievalInitialLabelRequest(
        model_id="model-a",
        proposals=[
            RetrievalLabelProposal(
                question_id="q1",
                research_question="HER2 breast cancer fixture research question",
                source=source or gdc_source(),
                proposed_label="relevant",
                confidence=confidence,
                rationale="The fixture project contains breast cancer source data.",
            )
        ],
    )


def safe_field_request() -> FieldInitialLabelRequest:
    return FieldInitialLabelRequest(
        model_id="model-a",
        proposals=[
            FieldLabelProposal(
                case_id="field-gene-alias",
                source=gdc_source(),
                raw_field="gene_symbol",
                raw_value="HER2",
                proposed_canonical_field="gene",
                proposed_canonical_value="ERBB2",
                allowed_auto_transform=True,
                confidence=0.99,
                rationale="Exact deterministic gene alias.",
            )
        ],
    )


def unsafe_her2_field_request() -> FieldInitialLabelRequest:
    return FieldInitialLabelRequest(
        model_id="model-a",
        proposals=[
            FieldLabelProposal(
                case_id="field-unsafe-her2",
                source=gdc_source(),
                raw_field="HER2_IHC",
                raw_value="2+",
                proposed_canonical_field="her2_status",
                proposed_canonical_value="Positive",
                allowed_auto_transform=True,
                confidence=0.99,
                rationale="Deliberately unsafe fixture proposal.",
            )
        ],
    )
