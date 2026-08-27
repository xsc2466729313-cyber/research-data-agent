from __future__ import annotations

from datetime import datetime, timezone

from backend.app.agent.orchestrator import ResearchOrchestrator
from backend.app.integration.entity_matcher_v2 import EntityMatcherV2
from backend.app.integration.schema_matcher_v2 import SchemaMatcherV2
from backend.app.research_planning.models import ResearchTopic
from backend.app.research_planning.research_agent import ResearchAgent
from backend.app.retrieval.bm25 import BM25Retriever
from backend.app.retrieval.embedding import HashingDenseRetriever
from backend.app.retrieval.hybrid import HybridRetrieverV2
from backend.app.retrieval.query_expansion import expand_query
from backend.app.retrieval.reranker import LexicalReranker


def test_query_expansion_adds_domain_aliases_without_duplicates() -> None:
    expanded = expand_query("HER2 pCR")
    assert "HER2 pCR" in expanded
    assert "erbb2" in expanded
    assert "pathological complete response" in expanded
    assert expanded.count("erbb2") == 1


def test_bm25_and_dense_retrievers_return_ranked_indices() -> None:
    documents = ["PIK3CA mutation in breast cancer", "lung cancer EGFR", "HER2 response"]
    lexical = BM25Retriever(documents)
    dense = HashingDenseRetriever(documents)
    assert lexical.search("PIK3CA", top_k=2)[0][0] == 0
    assert dense.search("PIK3CA", top_k=2)[0][0] in range(len(documents))
    assert all(0 <= score <= 1 for _, score in dense.search("PIK3CA"))


def test_hybrid_retriever_and_reranker_respect_top_k() -> None:
    documents = ["HER2 positive breast cancer", "unrelated lung cancer", "HER2 treatment response"]
    retriever = HybridRetrieverV2(documents, use_reranker=True)
    result = retriever.search("HER2", top_k=1)
    assert len(result) == 1
    assert result[0][0] in (0, 2)
    reranked = LexicalReranker().rerank("HER2", documents, [0, 1, 2], top_k=2)
    assert len(reranked) == 2
    assert reranked[0][0] in (0, 2)


def test_orchestrator_routes_from_missing_question_to_quality_review() -> None:
    orchestrator = ResearchOrchestrator()
    assert orchestrator.decide().next_stage == "research_planning"
    assert orchestrator.decide(question="breast cancer").next_stage == "literature_search"
    assert orchestrator.decide(
        question="breast cancer", completed_stages={"literature_search"}
    ).next_stage == "research_planning"
    assert orchestrator.decide(
        question="breast cancer",
        contract_status="READY_FOR_SOURCE_PLANNING",
        completed_stages={"literature_search"},
    ).next_stage == "data_acquisition"
    assert orchestrator.decide(question="x", quality_gate="FAIL").next_stage == "quality_review"


def test_research_agent_marks_empty_evidence_as_provisional_plan() -> None:
    topic = ResearchTopic(
        topic_id="topic-1",
        topic="乳腺癌新辅助治疗",
        domain="oncology",
        disease="breast cancer",
        ambiguity_level="high",
        created_at=datetime.now(timezone.utc),
    )
    draft = ResearchAgent().plan(topic, [])
    assert draft.candidates
    assert draft.evidence_count == 0
    assert "待核验草案" in draft.note
    assert set(draft.required_field_ids) == {candidate.candidate_id for candidate in draft.candidates}


def test_schema_matcher_v2_exposes_safety_decisions() -> None:
    matcher = SchemaMatcherV2()
    matches = matcher.match(
        ["age"],
        ["patient_age", "her2_status"],
        source_types={"age": "int"},
        target_types={"patient_age": "int", "her2_status": "str"},
        source_values={"age": [60]},
        target_values={"patient_age": [60]},
    )
    assert matches[0].target_field == "patient_age"
    assert matches[0].decision in {"AUTO", "REVIEW"}
    assert matches[0].evidence["type"] == 1.0
    rejected = matcher._score("foo", "bar", {}, {}, {}, {})
    assert rejected.decision == "REJECT"


def test_entity_matcher_v2_blocks_cross_study_and_low_confidence_merges() -> None:
    matcher = EntityMatcherV2()
    same = matcher.match(
        [{"id": "l1", "study_id": "s1", "patient_id": "p1", "age": 60}],
        [{"id": "r1", "study_id": "s1", "patient_id": "p1", "age": 60}],
    )
    assert same[0].status == "AUTO"
    conflict = matcher.match(
        [{"id": "l1", "study_id": "s1", "patient_id": "p1", "age": 60}],
        [{"id": "r1", "study_id": "s2", "patient_id": "p1", "age": 60}],
    )
    assert conflict[0].status == "REJECT"
    low = matcher.match(
        [{"id": "l1", "study_id": "s1", "patient_id": "p1", "age": 60}],
        [{"id": "r1", "study_id": "s1", "patient_id": "p9", "age": 61}],
    )
    assert low[0].status == "REJECT"
