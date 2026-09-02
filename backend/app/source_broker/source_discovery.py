from __future__ import annotations

from backend.app.literature.models import PaperRecord
from backend.app.oncology import is_breast_cancer, resolve_cancer_profile
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
        if self._is_oncology_contract(contract):
            source_ids.update({"cbioportal", "ncbi_geo", "gdc"})
        if any(accession.upper().startswith("GSE") for paper in papers for accession in paper.dataset_accessions):
            source_ids.add("ncbi_geo")
        return [source for source in self.catalog.sources() if source.source_id in source_ids]

    @staticmethod
    def _is_breast_cancer_contract(contract: ResearchContract) -> bool:
        return is_breast_cancer(SourceDiscovery._contract_text(contract))

    @staticmethod
    def _cancer_profile(contract: ResearchContract):
        return resolve_cancer_profile(SourceDiscovery._contract_text(contract))

    @staticmethod
    def _is_oncology_contract(contract: ResearchContract) -> bool:
        text = SourceDiscovery._contract_text(contract).casefold()
        return SourceDiscovery._cancer_profile(contract) is not None or any(
            token in text for token in ("癌", "肿瘤", "cancer", "carcinoma", "sarcoma", "neoplasm")
        )

    @staticmethod
    def _contract_text(contract: ResearchContract) -> str:
        return " ".join([contract.topic, contract.research_question, contract.population])
