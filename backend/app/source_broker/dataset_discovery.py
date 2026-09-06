from __future__ import annotations

from backend.app.literature.models import PaperRecord
from backend.app.research_planning.models import ResearchContract
from backend.app.source_broker.models import DatasetCandidate, ResourceDescriptor
from backend.app.source_broker.source_catalog import SeedSourceCatalog
from backend.app.source_broker.source_discovery import SourceDiscovery


class DatasetDiscovery:
    def __init__(self, catalog: SeedSourceCatalog) -> None:
        self.catalog = catalog

    def discover(
        self,
        contract: ResearchContract,
        papers: list[PaperRecord],
    ) -> list[DatasetCandidate]:
        candidates: dict[str, DatasetCandidate] = {}
        if contract.data_granularity == "publication":
            source = self.catalog.source("zenodo")
            if source is not None:
                candidates["zenodo:runtime"] = DatasetCandidate(
                    dataset_id="zenodo:runtime",
                    source_id=source.source_id,
                    accession=None,
                    title="Zenodo 实时公开数据集目录（待按主题检索）",
                    source_url="https://zenodo.org/",
                    diseases=[],
                    declared_granularity=["publication"],
                    field_hints=["dataset_id", "title", "description", "file_count", "source_id"],
                    access_mode="OPEN_API",
                    resources=[
                        ResourceDescriptor(
                            resource_id="zenodo:runtime:api",
                            dataset_id="zenodo:runtime",
                            source_id=source.source_id,
                            resource_type="REST_API",
                            source_url="https://zenodo.org/api/records/",
                            access_mode="OPEN_API",
                            expected_format="JSON",
                        )
                    ],
                    capability_status="seed_requires_runtime_verification",
                    authority=source.authority,
                    traceability=source.traceability,
                    structuredness=source.structuredness,
                    cost=source.cost,
                )
        cancer_profile = SourceDiscovery._cancer_profile(contract)
        if cancer_profile is not None:
            candidates.update(
                {
                    item.dataset_id: item
                    for item in self.catalog.datasets()
                    if cancer_profile.key in item.diseases
                }
            )

        paper_ids_by_accession: dict[str, list[str]] = {}
        for paper in papers:
            for accession in paper.dataset_accessions:
                key = accession.strip().upper()
                if key.startswith("GSE"):
                    paper_ids_by_accession.setdefault(key, []).append(paper.paper_id)

        for accession, paper_ids in paper_ids_by_accession.items():
            dataset_id = f"geo:{accession}"
            existing = candidates.get(dataset_id) or self.catalog.dataset(dataset_id)
            if existing is not None:
                candidates[dataset_id] = existing.model_copy(
                    update={"discovery_evidence_ids": sorted(set(paper_ids))}
                )
                continue
            source = self.catalog.source("ncbi_geo")
            if source is None:
                continue
            source_url = f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={accession}"
            candidates[dataset_id] = DatasetCandidate(
                dataset_id=dataset_id,
                source_id=source.source_id,
                accession=accession,
                title=f"GEO Series {accession}",
                source_url=source_url,
                diseases=[cancer_profile.key] if cancer_profile is not None else [],
                declared_granularity=[],
                field_hints=[],
                access_mode="OPEN_API",
                discovery_evidence_ids=sorted(set(paper_ids)),
                resources=[
                    ResourceDescriptor(
                        resource_id=f"{dataset_id}:landing_page",
                        dataset_id=dataset_id,
                        source_id=source.source_id,
                        resource_type="DATASET_LANDING_PAGE",
                        source_url=source_url,
                        access_mode="OPEN_API",
                    )
                ],
                capability_status="literature_hint_requires_profiling",
                authority=source.authority,
                traceability=source.traceability,
                structuredness=0.0,
                cost=source.cost,
            )
        return sorted(candidates.values(), key=lambda item: item.dataset_id)
