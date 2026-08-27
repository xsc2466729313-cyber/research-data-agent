from __future__ import annotations

from backend.app.literature.models import PaperRecord
from backend.app.research_planning.models import ResearchContract
from backend.app.source_broker.models import SourceCapability
from backend.app.source_broker.source_catalog import SeedSourceCatalog


class SourceDiscovery:
    def __init__(self, catalog: SeedSourceCatalog) -> None:
        self.catalog = catalog

    def discover(
        self,
        contract: ResearchContract,
        papers: list[PaperRecord],
    ) -> list[SourceCapability]:
        source_ids: set[str] = set()
        if self._is_breast_cancer_contract(contract):
            source_ids.update({"cbioportal", "ncbi_geo", "gdc"})
        if any(accession.upper().startswith("GSE") for paper in papers for accession in paper.dataset_accessions):
            source_ids.add("ncbi_geo")
        return [source for source in self.catalog.sources() if source.source_id in source_ids]

    @staticmethod
    def _is_breast_cancer_contract(contract: ResearchContract) -> bool:
        text = " ".join(
            [contract.topic, contract.research_question, contract.population]
        ).casefold()
        return "breast cancer" in text or "乳腺癌" in text
