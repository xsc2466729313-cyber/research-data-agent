from __future__ import annotations

from backend.app.literature.models import PaperRecord
from backend.app.research_planning.models import ResearchContract
from backend.app.source_broker.capability_profiler import CapabilityProfiler
from backend.app.source_broker.dataset_discovery import DatasetDiscovery
from backend.app.source_broker.models import SourcePlanningResult, SourcePlanRequest
from backend.app.source_broker.source_catalog import SeedSourceCatalog, default_source_catalog
from backend.app.source_broker.source_discovery import SourceDiscovery
from backend.app.source_broker.source_matcher import SourceMatcher
from backend.app.source_broker.source_selector import SourceSelector


class SourceBroker:
    def __init__(self, *, catalog: SeedSourceCatalog | None = None) -> None:
        self.catalog = catalog or default_source_catalog()
        self.source_discovery = SourceDiscovery(self.catalog)
        self.dataset_discovery = DatasetDiscovery(self.catalog)
        self.capability_profiler = CapabilityProfiler()
        self.matcher = SourceMatcher()
        self.selector = SourceSelector()

    def plan(
        self,
        contract: ResearchContract,
        papers: list[PaperRecord],
        request: SourcePlanRequest,
    ) -> SourcePlanningResult:
        sources = self.source_discovery.discover(contract, papers)
        candidates = self.capability_profiler.profile(
            self.dataset_discovery.discover(contract, papers)
        )
        matrix = self.matcher.build_matrix(contract, candidates)
        source_plan = self.selector.select(contract, candidates, matrix, request)
        return SourcePlanningResult(
            contract_id=contract.contract_id,
            sources=sources,
            dataset_candidates=candidates,
            coverage_matrix=matrix,
            source_plan=source_plan,
        )
