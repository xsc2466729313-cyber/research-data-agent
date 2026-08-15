from __future__ import annotations

import hashlib

from backend.app.integration.errors import IntegrationError, IntegrationErrorCode
from backend.app.integration.models import (
    LinkDecision,
    LinkScope,
    LinkStatus,
    PatientSampleLinkCandidate,
)
from backend.app.normalization.models import NormalizedIdentity


class PatientSampleLinker:
    AUTO_LINK_THRESHOLD = 0.90

    def link(
        self,
        *,
        identities: list[NormalizedIdentity],
        candidates: list[PatientSampleLinkCandidate],
    ) -> list[LinkDecision]:
        by_id = {identity.raw_record_id: identity for identity in identities}
        decisions: dict[tuple[str, str], LinkDecision] = {}

        for left_index, left in enumerate(identities):
            for right in identities[left_index + 1 :]:
                decision = self._exact_decision(left=left, right=right)
                if decision is not None:
                    decisions[self._pair(left.raw_record_id, right.raw_record_id)] = decision

        for candidate in candidates:
            pair = self._pair(candidate.left_record_id, candidate.right_record_id)
            if candidate.left_record_id not in by_id or candidate.right_record_id not in by_id:
                raise IntegrationError(
                    IntegrationErrorCode.INVALID_REQUEST,
                    "Link candidate references an unknown or blocked raw record.",
                    details={
                        "left_record_id": candidate.left_record_id,
                        "right_record_id": candidate.right_record_id,
                    },
                )
            if pair in decisions and decisions[pair].status in {
                LinkStatus.LINKED,
                LinkStatus.LINKED_PATIENT_ONLY,
                LinkStatus.REJECTED,
            }:
                continue
            decisions[pair] = self._candidate_decision(
                left=by_id[candidate.left_record_id],
                right=by_id[candidate.right_record_id],
                candidate=candidate,
            )
        return list(decisions.values())

    def _exact_decision(
        self, *, left: NormalizedIdentity, right: NormalizedIdentity
    ) -> LinkDecision | None:
        if left.study_id != right.study_id:
            return None
        if (
            left.sample_id
            and right.sample_id
            and left.sample_id == right.sample_id
            and left.patient_id
            and right.patient_id
            and left.patient_id != right.patient_id
        ):
            return self._decision(
                left=left,
                right=right,
                scope=LinkScope.SAMPLE,
                confidence=1.0,
                method="identifier_contradiction_v1",
                status=LinkStatus.REJECTED,
                auto_merge=False,
                reason="Exact sample ID is attached to conflicting patient IDs.",
            )
        if left.sample_id and left.sample_id == right.sample_id:
            return self._decision(
                left=left,
                right=right,
                scope=LinkScope.SAMPLE,
                confidence=1.0,
                method="exact_study_sample_id_v1",
                status=LinkStatus.LINKED,
                auto_merge=True,
                reason="Study and sample identifiers match exactly.",
            )
        if left.patient_id and left.patient_id == right.patient_id:
            both_patient_level = left.sample_id is None and right.sample_id is None
            return self._decision(
                left=left,
                right=right,
                scope=LinkScope.PATIENT,
                confidence=1.0,
                method="exact_study_patient_id_v1",
                status=(
                    LinkStatus.LINKED
                    if both_patient_level
                    else LinkStatus.LINKED_PATIENT_ONLY
                ),
                auto_merge=both_patient_level,
                reason=(
                    "Patient identifiers match and both records are patient-level."
                    if both_patient_level
                    else "Patient identifiers match, but sample-specific records remain separate."
                ),
            )
        return None

    def _candidate_decision(
        self,
        *,
        left: NormalizedIdentity,
        right: NormalizedIdentity,
        candidate: PatientSampleLinkCandidate,
    ) -> LinkDecision:
        if left.study_id != right.study_id:
            return self._decision(
                left=left,
                right=right,
                scope=candidate.scope,
                confidence=candidate.confidence,
                method="candidate_rejected_v1",
                status=LinkStatus.REJECTED,
                auto_merge=False,
                reason="Cross-study candidate links are not automatically merged.",
            )
        if left.patient_id and right.patient_id and left.patient_id != right.patient_id:
            return self._decision(
                left=left,
                right=right,
                scope=candidate.scope,
                confidence=candidate.confidence,
                method="candidate_identifier_contradiction_v1",
                status=LinkStatus.REJECTED,
                auto_merge=False,
                reason="Candidate contradicts explicit patient identifiers.",
            )
        if (
            candidate.scope == LinkScope.SAMPLE
            and left.sample_id
            and right.sample_id
            and left.sample_id != right.sample_id
        ):
            return self._decision(
                left=left,
                right=right,
                scope=candidate.scope,
                confidence=candidate.confidence,
                method="candidate_identifier_contradiction_v1",
                status=LinkStatus.REJECTED,
                auto_merge=False,
                reason="Candidate contradicts explicit sample identifiers.",
            )
        if candidate.confidence < self.AUTO_LINK_THRESHOLD:
            return self._decision(
                left=left,
                right=right,
                scope=candidate.scope,
                confidence=candidate.confidence,
                method="candidate_confidence_gate_v1",
                status=LinkStatus.UNRESOLVED,
                auto_merge=False,
                reason=(
                    f"Confidence is below the {self.AUTO_LINK_THRESHOLD:.2f} "
                    "automatic-link threshold."
                ),
            )
        patient_only = candidate.scope == LinkScope.PATIENT and (
            left.sample_id is not None or right.sample_id is not None
        )
        return self._decision(
            left=left,
            right=right,
            scope=candidate.scope,
            confidence=candidate.confidence,
            method="high_confidence_candidate_v1",
            status=(
                LinkStatus.LINKED_PATIENT_ONLY if patient_only else LinkStatus.LINKED
            ),
            auto_merge=not patient_only,
            reason=(
                "High-confidence patient link retained without merging sample records."
                if patient_only
                else f"High-confidence candidate supported by: {candidate.basis}"
            ),
        )

    def _decision(
        self,
        *,
        left: NormalizedIdentity,
        right: NormalizedIdentity,
        scope: LinkScope,
        confidence: float,
        method: str,
        status: LinkStatus,
        auto_merge: bool,
        reason: str,
    ) -> LinkDecision:
        pair = self._pair(left.raw_record_id, right.raw_record_id)
        token = f"{pair[0]}|{pair[1]}|{scope.value}|{method}"
        return LinkDecision(
            link_id=f"link:{hashlib.sha256(token.encode('utf-8')).hexdigest()[:24]}",
            left_record_id=pair[0],
            right_record_id=pair[1],
            scope=scope,
            confidence=confidence,
            method=method,
            status=status,
            auto_merge_allowed=auto_merge,
            reason=reason,
        )

    @staticmethod
    def _pair(left: str, right: str) -> tuple[str, str]:
        return tuple(sorted((left, right)))
