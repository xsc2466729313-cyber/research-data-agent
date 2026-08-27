from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import backend.app.main as main_module
from backend.app.literature import (
    EuropePMCProvider,
    LiteratureAgent,
    LiteratureProviderTrace,
    LiteratureSearchRequest,
    LiteratureSearchResult,
    PaperRecord,
)
from backend.app.rag import (
    EvidenceQueryRequest,
    PaperChunker,
    RAGEvaluationCase,
    RAGEvaluationRequest,
)
from backend.app.research_planning import ResearchPlanningService, TopicCreateRequest
from backend.app.sources.discovery import DiscoveryAdapter


def _paper() -> PaperRecord:
    return PaperRecord(
        paper_id="europepmc:PMC-RAG-TEST",
        source_id="europepmc:PMC-RAG-TEST",
        provider="europe_pmc",
        title="PIK3CA and pCR in HER2-positive breast cancer",
        abstract="PIK3CA mutation was associated with neoadjuvant treatment response.",
        source_url="https://europepmc.org/article/PMC/PMC-RAG-TEST",
        sections={
            "methods": (
                "Patients with HER2-positive breast cancer received neoadjuvant treatment. "
                "PIK3CA mutation was measured before treatment and pathological complete "
                "response (pCR) was the primary outcome. Logistic regression reported odds ratios."
            ),
            "data_availability": "De-identified expression data are available in GEO under GSE12345.",
            "results": "PIK3CA-mutant tumours had a lower observed pCR rate.",
        },
        dataset_accessions=["GSE12345"],
    )


class _StubProvider:
    name = "stub"
    configured = True

    def search(self, request: LiteratureSearchRequest) -> LiteratureSearchResult:
        now = datetime.now(timezone.utc)
        return LiteratureSearchResult(
            provider=self.name,
            query=request.query,
            papers=[_paper()],
            trace=LiteratureProviderTrace(
                provider=self.name,
                query=request.query,
                requested_at=now,
                completed_at=now,
                status="success",
                source_url="https://example.org/search",
                result_count=1,
            ),
        )


def _service() -> ResearchPlanningService:
    return ResearchPlanningService(literature_agent=LiteratureAgent(providers=[_StubProvider()]))


def _planned_service() -> tuple[ResearchPlanningService, str, str]:
    service = _service()
    topic = service.create_topic(TopicCreateRequest(topic="乳腺癌新辅助治疗"))
    service.scan_literature(topic.topic_id, main_module.LiteratureScanRequest(max_records=10))
    candidates = service.question_candidates(topic.topic_id).candidates
    selected = next(candidate for candidate in candidates if "PIK3CA" in candidate.question)
    contract = service.select_question(selected.candidate_id, main_module.QuestionSelectionRequest())
    return service, topic.topic_id, contract.contract_id


def test_structure_aware_chunking_preserves_source_and_raw_values() -> None:
    chunks = PaperChunker(max_chars=240, overlap_chars=30).chunk("topic-test", [_paper()])

    assert chunks
    assert chunks[0].section == "methods"
    assert chunks[0].section_priority < next(
        chunk.section_priority for chunk in chunks if chunk.section == "abstract"
    )
    assert all(chunk.source_id == "europepmc:PMC-RAG-TEST" for chunk in chunks)
    assert all(chunk.source_url.startswith("https://europepmc.org/") for chunk in chunks)
    assert all(chunk.raw_field and chunk.raw_value == chunk.text for chunk in chunks)
    assert all(chunk.end_char > chunk.start_char for chunk in chunks)


def test_hybrid_rag_graph_and_frozen_gold_evaluation_are_evidence_linked() -> None:
    service, topic_id, contract_id = _planned_service()

    report = service.build_rag_index(
        topic_id,
        main_module.RAGIndexRequest(contract_id=contract_id),
    )
    response = service.query_evidence(
        topic_id,
        EvidenceQueryRequest(
            query="PIK3CA mutation pCR logistic regression",
            field_id="pik3ca_mutation",
            top_k=5,
        ),
    )
    graph = service.knowledge_graph(topic_id)

    assert report.chunk_count >= 5
    assert report.paper_count == 1
    assert report.vector_backend == "memory-cosine"
    assert report.embedding_backend == "hashing-lexical-v1"
    assert response.evidence_found is True
    assert response.hits[0].section == "methods"
    assert response.hits[0].source_id == "europepmc:PMC-RAG-TEST"
    assert response.hits[0].graph_score == 1.0
    assert response.hits[0].source_url.startswith("https://europepmc.org/")
    chinese_response = service.query_evidence(
        topic_id,
        EvidenceQueryRequest(
            query="为什么把 pCR 作为主要结局？",
            field_id="pcr",
            top_k=3,
        ),
    )
    assert chinese_response.hits[0].section == "methods"
    assert "pCR" in chinese_response.hits[0].text
    assert any(node.node_id == "field:pik3ca_mutation" for node in graph.nodes)
    assert any(
        edge.target == "field:pik3ca_mutation" and edge.relation == "DEFINES"
        for edge in graph.edges
    )
    assert any(node.node_type == "Dataset" and node.label == "GSE12345" for node in graph.nodes)

    evaluation = service.evaluate_rag(
        topic_id,
        RAGEvaluationRequest(
            gold_set_id="planning-rag-gold",
            gold_set_version="1.0.0",
            gold_set_frozen=True,
            top_k=5,
            cases=[
                RAGEvaluationCase(
                    case_id="case-pik3ca",
                    query="PIK3CA mutation pCR logistic regression",
                    field_id="pik3ca_mutation",
                    expected_source_ids=["europepmc:PMC-RAG-TEST"],
                    expected_sections=["methods"],
                )
            ],
        ),
    )
    assert evaluation.metrics.recall_at_k == 1.0
    assert evaluation.metrics.mrr == 1.0
    assert evaluation.metrics.ndcg_at_k == 1.0
    assert evaluation.metrics.evidence_hit_rate == 1.0
    assert "不替代项目冻结 SDTI" in evaluation.notice


def test_rag_evaluation_rejects_unfrozen_gold_set() -> None:
    with pytest.raises(ValidationError, match="reviewed and frozen"):
        RAGEvaluationRequest(
            gold_set_id="draft",
            gold_set_version="0.1",
            gold_set_frozen=False,
            cases=[
                RAGEvaluationCase(
                    case_id="case-1",
                    query="PIK3CA evidence",
                    expected_source_ids=["europepmc:PMC-RAG-TEST"],
                )
            ],
        )


def test_europe_pmc_fulltext_sections_and_acquisition_trace_are_preserved() -> None:
    fulltext_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <article><body>
      <sec><title>Methods</title><p>pCR was the primary endpoint after treatment.</p></sec>
      <sec><title>Data availability</title><p>Data are available under GSE99999.</p></sec>
    </body></article>"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/PMC123/fullTextXML"):
            return httpx.Response(200, content=fulltext_xml, request=request)
        return httpx.Response(
            200,
            json={
                "hitCount": 1,
                "resultList": {
                    "result": [
                        {
                            "id": "PMC123",
                            "pmcid": "PMC123",
                            "title": "Open access breast cancer study",
                            "abstractText": "A neoadjuvant breast cancer study.",
                            "inEPMC": True,
                        }
                    ]
                },
            },
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = EuropePMCProvider(DiscoveryAdapter(client=client)).search(
        LiteratureSearchRequest(query="breast cancer pCR", max_records=5)
    )
    client.close()

    paper = result.papers[0]
    assert paper.sections["methods"].startswith("pCR was the primary endpoint")
    assert paper.sections["data_availability"].endswith("GSE99999.")
    assert "GSE99999" in paper.dataset_accessions
    assert paper.raw_metadata["fulltext_fetch_status"] == "success"
    assert paper.acquisition_traces[0].query == "fulltext:PMC123"
    assert paper.acquisition_traces[0].source_url.endswith("/PMC123/fullTextXML")


def test_phase_two_api_returns_chunks_graph_relations_and_real_metric_values(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "research_planning_service", _service())
    client = TestClient(main_module.app)

    topic = client.post("/api/research/topics", json={"topic": "乳腺癌新辅助治疗"}).json()
    topic_id = topic["topic_id"]
    scan = client.post(
        f"/api/research/topics/{topic_id}/literature-scan",
        json={"max_records": 10},
    ).json()
    assert scan["scan"]["papers"][0]["source_id"] == "europepmc:PMC-RAG-TEST"

    candidates = client.get(f"/api/research/topics/{topic_id}/question-candidates").json()["candidates"]
    selected = next(candidate for candidate in candidates if "PIK3CA" in candidate["question"])
    contract = client.post(
        f"/api/research/questions/{selected['candidate_id']}/select",
        json={},
    ).json()

    index = client.post(
        f"/api/research/topics/{topic_id}/rag-index",
        json={"contract_id": contract["contract_id"]},
    )
    assert index.status_code == 200
    assert index.json()["chunk_count"] >= 5

    evidence = client.post(
        f"/api/research/topics/{topic_id}/evidence-query",
        json={
            "query": "PIK3CA mutation pCR logistic regression",
            "field_id": "pik3ca_mutation",
            "top_k": 3,
        },
    )
    assert evidence.status_code == 200
    assert evidence.json()["hits"][0]["section"] == "methods"
    assert evidence.json()["hits"][0]["graph_score"] == 1.0

    graph = client.get(f"/api/research/topics/{topic_id}/knowledge-graph")
    assert graph.status_code == 200
    assert any(edge["relation"] == "DEFINES" for edge in graph.json()["edges"])

    evaluation = client.post(
        f"/api/research/topics/{topic_id}/rag-evaluate",
        json={
            "gold_set_id": "planning-rag-gold",
            "gold_set_version": "1.0.0",
            "gold_set_frozen": True,
            "top_k": 3,
            "cases": [
                {
                    "case_id": "case-pik3ca",
                    "query": "PIK3CA mutation pCR logistic regression",
                    "field_id": "pik3ca_mutation",
                    "expected_source_ids": ["europepmc:PMC-RAG-TEST"],
                    "expected_sections": ["methods"],
                }
            ],
        },
    )
    assert evaluation.status_code == 200
    assert evaluation.json()["metrics"] == {
        "recall_at_k": 1.0,
        "mrr": 1.0,
        "ndcg_at_k": 1.0,
        "evidence_hit_rate": 1.0,
    }

    rejected = client.post(
        f"/api/research/topics/{topic_id}/rag-evaluate",
        json={
            "gold_set_id": "draft",
            "gold_set_version": "0.1",
            "gold_set_frozen": False,
            "cases": [
                {
                    "case_id": "case-1",
                    "query": "PIK3CA evidence",
                    "expected_source_ids": ["europepmc:PMC-RAG-TEST"],
                }
            ],
        },
    )
    assert rejected.status_code == 422
