from __future__ import annotations

from types import SimpleNamespace

from backend.app.agent.accession_harvest import (
    asks_pcr,
    asks_treatment,
    catalog_query,
    extract_gse_accessions,
    harvest_from_raw_results,
    literature_query,
    needs_clinical_outcome,
    question_asks_survival,
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


def test_pcr_only_outcome_still_searches_response_cohorts() -> None:
    spec = ResearchSpec(
        task_id="tnbc-harvest",
        research_goal="研究三阴性乳腺癌中 BRCA1/BRCA2 突变与新辅助化疗病理完全缓解（pCR）的关系",
        disease="Breast Cancer",
        subtype="Triple-negative",
        genes=["BRCA1", "BRCA2"],
        outcomes=["pCR"],
        required_data_types=["clinical", "mutation"],
    )
    catalog = SimpleNamespace(
        records=[
            SimpleNamespace(accession="GSE111", title="TCGA BRCA mutation landscape", summary="copy number only"),
            SimpleNamespace(
                accession="GSE999",
                title="TNBC neoadjuvant chemotherapy pCR BRCA1",
                summary="triple-negative breast cancer pathological complete response",
            ),
        ]
    )
    harvested = harvest_from_raw_results([("search_geo_catalog", catalog)], spec)
    assert harvested[0] == "GSE999"
    query = catalog_query(spec)
    assert "pCR" in query or "response" in query.casefold()
    assert asks_pcr(spec) is True
    assert asks_treatment(spec) is False
    assert needs_clinical_outcome(spec) is True


def test_os_rfs_abbreviations_count_as_survival_outcome() -> None:
    question = "PIK3CA 突变与乳腺癌 OS/RFS 的关系是否受到 ER 状态或 IntClust 分型的调节？"
    spec = ResearchSpec(
        task_id="os-rfs",
        research_goal=question,
        disease="Breast Cancer",
        genes=["PIK3CA"],
        outcomes=[],
        required_data_types=["clinical", "mutation"],
    )
    assert question_asks_survival(question) is True
    assert needs_clinical_outcome(spec) is True
    assert asks_treatment(spec) is False
    query = catalog_query(spec, extra_terms=["PIK3CA", "OS", "RFS", "IntClust", "ER"])
    lowered = query.casefold()
    assert "pik3ca" in lowered
    assert "intclust" in lowered or "rfs" in lowered
    assert "overall survival" in lowered or "relapse-free" in lowered
    assert "pcr" not in lowered


def test_catalog_query_follows_new_question_keywords() -> None:
    spec = ResearchSpec(
        task_id="gata3-pam50",
        research_goal="GATA3 突变与 PAM50 亚型在乳腺癌中的分布是否一致？",
        disease="Breast Cancer",
        genes=["GATA3"],
        outcomes=[],
        required_data_types=["clinical", "mutation"],
    )
    query = catalog_query(spec, extra_terms=["GATA3", "PAM50"])
    assert "GATA3" in query
    assert "PAM50" in query
    assert "pCR" not in query
    assert "pcr" not in query.casefold()
    assert "response" not in query.casefold()
