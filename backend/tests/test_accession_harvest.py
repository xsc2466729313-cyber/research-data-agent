from __future__ import annotations

from types import SimpleNamespace

from backend.app.agent.accession_harvest import (
    catalog_query,
    extract_gse_accessions,
    harvest_from_raw_results,
    literature_query,
)
from backend.app.models import ResearchSpec


def _spec() -> ResearchSpec:
    return ResearchSpec(
        task_id="harvest-test",
        research_goal="研究 HER2 阳性乳腺癌中 PIK3CA 突变是否影响治疗响应",
        disease="Breast Cancer",
        subtype="HER2-positive",
        genes=["PIK3CA"],
        drugs=["Trastuzumab"],
        outcomes=["treatment_response"],
        required_data_types=["clinical", "mutation", "treatment_response"],
    )


def test_extract_gse_accessions_from_abstract() -> None:
    text = "We analyzed GSE76360 and GSE50948; GSM123 is a sample not a series."
    assert extract_gse_accessions(text) == ["GSE76360", "GSE50948"]


def test_harvest_ranks_catalog_hits_by_question_tokens() -> None:
    spec = _spec()
    catalog = SimpleNamespace(
        records=[
            SimpleNamespace(accession="GSE111", title="colon cancer RNA-seq", summary=""),
            SimpleNamespace(
                accession="GSE222",
                title="HER2 positive breast cancer PIK3CA trastuzumab response",
                summary="pCR after neoadjuvant therapy",
            ),
        ]
    )
    literature = SimpleNamespace(
        query="breast cancer",
        records=[
            SimpleNamespace(
                title="Independent cohort GSE333",
                abstract="No mutation data.",
            )
        ],
    )
    harvested = harvest_from_raw_results(
        [("search_geo_catalog", catalog), ("search_europe_pmc", literature)],
        spec,
    )
    assert harvested[0] == "GSE222"
    assert "GSE333" in harvested


def test_catalog_query_includes_response_and_gene() -> None:
    query = catalog_query(_spec())
    assert "PIK3CA" in query
    assert "response" in query.casefold() or "pCR" in query
    assert "GSE" in literature_query(_spec())
