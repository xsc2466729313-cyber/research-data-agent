from __future__ import annotations

from backend.app.source_broker.models import DatasetCandidate


class CapabilityProfiler:
    """Expose declared seed/hint capabilities without pretending they were live-verified."""

    def profile(self, candidates: list[DatasetCandidate]) -> list[DatasetCandidate]:
        return [
            candidate.model_copy(
                update={
                    "field_hints": sorted(set(candidate.field_hints)),
                    "declared_granularity": sorted(set(candidate.declared_granularity)),
                }
            )
            for candidate in candidates
        ]
