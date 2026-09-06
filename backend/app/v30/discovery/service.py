from __future__ import annotations

from backend.app.v30.models import (
    DiscoverRequest,
    DiscoverResponse,
    DiscoveryCandidate,
    DiscoveryLocator,
    FieldHypothesis,
    RegistrySource,
)
from backend.app.v30.registry.service import SourceRegistryService

_LOCATOR_SCHEMES = {
    "geo": ("accession_scheme", "GSE"),
    "gdc": ("project_id_scheme", "TCGA-project"),
    "cbioportal": ("study_id_scheme", "cbioportal-study"),
    "europe_pmc": ("literature_query", None),
    "aact": ("nct_id_scheme", "NCT"),
    "civic": ("evidence_query", None),
}


class DiscoveryFacade:
    """Turn a domain + gaps into honest source candidates. Never fetches or verifies fields."""

    def __init__(self, registry: SourceRegistryService | None = None) -> None:
        self.registry = registry or SourceRegistryService()

    def discover(self, request: DiscoverRequest) -> DiscoverResponse:
        domain = request.domain.strip()
        sources = self._matching_sources(domain, request.required_modalities)
        candidates = [self._candidate(source, request) for source in sources]
        return DiscoverResponse(
            domain=domain,
            topic=request.topic,
            candidates=candidates,
            notice=(
                "这些条目只是来源候选，尚未核验，也没有取数。"
                "field_hypotheses 只是可能相关的假说，不表示字段已经存在。"
            ),
            fetched=False,
            integrated=False,
        )

    def _matching_sources(self, domain: str, required_modalities: list[str]) -> list[RegistrySource]:
        wanted = {item.strip() for item in required_modalities if item.strip()}
        matched: list[RegistrySource] = []
        for source in self.registry.list_sources(domain=domain).sources:
            if wanted and not wanted.intersection(source.modalities) and source.resource_kind != "literature":
                continue
            matched.append(source)
        return matched

    def _candidate(self, source: RegistrySource, request: DiscoverRequest) -> DiscoveryCandidate:
        verification = self._verification_status(source)
        return DiscoveryCandidate(
            candidate_id=f"disc-{source.domain}-{source.source_key}",
            source_key=source.source_key,
            resource_kind=source.resource_kind,
            locator=self._locator(source),
            source_id=f"registry:{source.source_key}",
            discovered_from="registry",
            field_hypotheses=self._hypotheses(source, request.field_gaps),
            verification_status=verification,
            next_action=self._next_action(source, verification),
            registry_status=source.status,
            integrate_eligible=False,
        )

    @staticmethod
    def _verification_status(source: RegistrySource) -> str:
        if source.status in {"planned", "catalog_only"} or source.domain in {"astronomy", "materials"}:
            return "catalog_only"
        return "unverified"

    @staticmethod
    def _next_action(source: RegistrySource, verification: str) -> str:
        if source.status == "planned":
            return "reject"
        if verification == "catalog_only":
            return "request_upload"
        if source.fetch_binding:
            return "fetch_via_adapter"
        return "reject"

    @staticmethod
    def _locator(source: RegistrySource) -> DiscoveryLocator:
        locator_type, value = _LOCATOR_SCHEMES.get(source.source_key, ("catalog", None))
        if source.status == "planned":
            return DiscoveryLocator(
                locator_type="planned",
                value=None,
                note=f"{source.display_name} 仍为 planned，没有可执行取数入口。",
            )
        if source.status == "catalog_only":
            return DiscoveryLocator(
                locator_type="catalog",
                value=None,
                note=f"{source.display_name} 仅有目录能力描述，本步未检索、未取数。",
            )
        return DiscoveryLocator(
            locator_type=locator_type,
            value=value,
            note=f"{source.display_name} 候选来自 Registry，尚未用 Adapter 核验具体资源。",
        )

    @staticmethod
    def _hypotheses(source: RegistrySource, field_gaps: list[str]) -> list[FieldHypothesis]:
        gaps = [item.strip() for item in field_gaps if item.strip()]
        if not gaps:
            return [
                FieldHypothesis(
                    field=modality,
                    hypothesis=f"{source.display_name} 可能提供 {modality}，尚未核验。",
                    coverage_claimed=False,
                    coverage_status="unknown",
                )
                for modality in source.modalities
            ]
        return [
            FieldHypothesis(
                field=gap,
                hypothesis=f"{source.display_name} 可能对应缺口 {gap}；这只是假说，不是字段已经存在的证明。",
                coverage_claimed=False,
                coverage_status="unknown",
            )
            for gap in gaps
        ]
