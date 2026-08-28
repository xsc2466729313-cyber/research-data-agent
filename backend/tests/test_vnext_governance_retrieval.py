from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from fastapi.testclient import TestClient

from backend.app.governance import (
    DecisionSource,
    DecisionStatus,
    EvidenceRecord,
    SafetyDecisionRequest,
    SafetyLayer,
)
from backend.app.main import app
from backend.app.retrieval import RetrievalDocument, RetrievalRequest, RetrievalServiceV2
from backend.app.retrieval.dense import SentenceTransformerDenseRetriever
from backend.app.retrieval.reranker import CrossEncoderReranker
from backend.app.vnext_config import load_vnext_config


def _evidence() -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id="evidence:1",
        source_id="geo:GSE76360",
        raw_field="characteristics_ch1.2",
        raw_value="HER2 positive",
        transformation="exact_source_field_copy",
        model_or_rule="source_parser",
        version="1.0",
        created_at=datetime.now(timezone.utc),
    )


def test_vnext_thresholds_and_retrieval_weights_load_from_config() -> None:
    settings = load_vnext_config()
    assert settings.governance.auto_confidence_threshold == 0.90
    assert settings.retrieval.default_method == "bm25"
    assert settings.retrieval.bm25_weight + settings.retrieval.dense_weight == 1.0


def test_real_backend_adapters_can_be_verified_with_injected_models() -> None:
    class FakeEmbeddingModel:
        def encode(self, texts, **kwargs):
            return np.asarray([[1.0, 0.0] if "PIK3CA" in text else [0.0, 1.0] for text in texts])

    dense = SentenceTransformerDenseRetriever(
        ["PIK3CA breast cancer", "weather"],
        model_name="test-semantic-model",
        model=FakeEmbeddingModel(),
        query_instruction="",
    )
    assert dense.search("PIK3CA", 1)[0][0] == 0

    class FakeCrossEncoder:
        def predict(self, pairs, **kwargs):
            return np.asarray([2.0 if "PIK3CA" in document else -2.0 for _, document in pairs])

    reranker = CrossEncoderReranker(model_name="test-reranker", model=FakeCrossEncoder())
    assert reranker.rerank("mutation", ["weather", "PIK3CA"], [0, 1], 1)[0][0] == 1


def test_safety_layer_allows_only_evidenced_rule_clean_high_confidence_proposal() -> None:
    result = SafetyLayer().evaluate(
        SafetyDecisionRequest(
            proposal_id="proposal:valid",
            task_type="schema_mapping",
            candidate={"source_field": "patient_age", "target_field": "patient_age"},
            confidence=0.96,
            evidence=[_evidence()],
            decision_source=DecisionSource.ALGORITHM,
            model_version="schema-matcher-v3-candidate",
        )
    )
    assert result.decision.status is DecisionStatus.AUTO
    assert result.review_record is None
    assert len(result.decision.audit.input_hash) == 64
    assert all(item.outcome.value == "PASS" for item in result.decision.rule_validation)


def test_safety_layer_blocks_missing_evidence_and_unsafe_her2_mapping() -> None:
    missing = SafetyLayer().evaluate(
        SafetyDecisionRequest(
            proposal_id="proposal:no-evidence",
            task_type="schema_mapping",
            candidate={"field": "stage"},
            confidence=0.99,
            evidence=[],
            decision_source=DecisionSource.QWEN,
            model_name="qwen",
            model_version="configured-model",
        )
    )
    assert missing.decision.status is DecisionStatus.REJECT
    assert "MISSING_EVIDENCE" in {item.rule_id for item in missing.decision.rule_validation}

    unsafe = SafetyLayer().evaluate(
        SafetyDecisionRequest(
            proposal_id="proposal:unsafe-her2",
            task_type="medical_normalization",
            candidate={"her2_assay": "IHC", "her2_raw_value": "2+", "her2_status": "Positive"},
            confidence=0.99,
            evidence=[_evidence()],
            decision_source=DecisionSource.QWEN,
            model_name="qwen",
            model_version="configured-model",
        )
    )
    assert unsafe.decision.status is DecisionStatus.REJECT
    assert "HER2_IHC_2PLUS" in {item.rule_id for item in unsafe.decision.rule_validation}


def test_safety_layer_creates_review_queue_record_for_review_band() -> None:
    result = SafetyLayer().evaluate(
        SafetyDecisionRequest(
            proposal_id="proposal:ambiguous",
            task_type="entity_link",
            candidate={"left_study_id": "study-1", "right_study_id": "study-1"},
            confidence=0.80,
            evidence=[_evidence()],
            decision_source=DecisionSource.ALGORITHM,
            model_version="entity-candidate-v1",
        )
    )
    assert result.decision.status is DecisionStatus.REVIEW
    assert result.review_record is not None
    assert result.review_record.proposal_id == "proposal:ambiguous"


def test_entity_proposal_cannot_bypass_patient_sample_linker() -> None:
    result = SafetyLayer().evaluate(
        SafetyDecisionRequest(
            proposal_id="proposal:entity-no-final-gate",
            task_type="entity_link",
            candidate={"left_study_id": "study-1", "right_study_id": "study-1"},
            confidence=0.99,
            evidence=[_evidence()],
            decision_source=DecisionSource.QWEN,
            model_name="qwen",
            model_version="configured-model",
        )
    )
    assert result.decision.status is DecisionStatus.REVIEW
    assert "PATIENT_SAMPLE_LINKER_GATE" in {item.rule_id for item in result.decision.rule_validation}


def test_retrieval_v2_returns_traceable_scores_and_discloses_fallback() -> None:
    service = RetrievalServiceV2()
    result = service.search(
        RetrievalRequest(
            query_id="query:1",
            query="HER2 pCR breast cancer",
            top_k=2,
            method="hashing_dense_fallback",
            documents=[
                RetrievalDocument(doc_id="doc:1", source_id="pmc:1", text="HER2 breast cancer pathological complete response"),
                RetrievalDocument(doc_id="doc:2", source_id="pmc:2", text="EGFR lung cancer survival"),
                RetrievalDocument(doc_id="doc:3", source_id="pmc:3", text="ERBB2 neoadjuvant response"),
            ],
        )
    )
    assert result.results[0].doc_id in {"doc:1", "doc:3"}
    assert result.results[0].source_id.startswith("pmc:")
    assert [item.rank for item in result.results] == [1, 2]
    assert "hashing_dense_fallback" in result.method
    assert result.telemetry.qwen_invoked is False
    assert "not a semantic-model result" in result.telemetry.notice
    assert result.audit.dataset_manifest == "inline-request"


def test_retrieval_v2_default_main_path_does_not_invoke_hashing() -> None:
    result = RetrievalServiceV2().search(
        RetrievalRequest(
            query_id="query:bm25-default",
            query="PIK3CA",
            top_k=1,
            documents=[RetrievalDocument(doc_id="doc:1", source_id="source:1", text="PIK3CA mutation")],
        )
    )
    assert result.method == "bm25_v1"
    assert result.telemetry.dense_backend == "not-invoked"
    assert result.results[0].rerank_score == 0.0


def test_vnext_api_returns_business_decisions_not_only_http_200() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v2/retrieval/search",
        json={
            "query_id": "api-query",
            "query": "PIK3CA breast cancer",
            "top_k": 1,
            "method": "bm25",
            "documents": [
                {"doc_id": "relevant", "source_id": "source:1", "text": "PIK3CA mutation breast cancer"},
                {"doc_id": "other", "source_id": "source:2", "text": "weather forecast"},
            ],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["results"][0]["doc_id"] == "relevant"
    assert payload["telemetry"]["dense_backend"] == "not-invoked"
    assert payload["telemetry"]["qwen_invocation_rate"] == 0.0
