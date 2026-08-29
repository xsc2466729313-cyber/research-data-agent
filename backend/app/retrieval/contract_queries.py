from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.app.contracts.models import FrozenResearchContract
from backend.app.retrieval.models import RetrievalDocument


QUERY_TYPES = ("exact", "synonym", "clinical", "dataset", "outcome")


def expand_contract_queries(contract: FrozenResearchContract) -> list[dict[str, str]]:
    gene = contract.exposure.name if contract.exposure else ""
    outcome = contract.outcome.name if contract.outcome else "response"
    disease = contract.population.disease
    subtype = contract.population.subtype or ""
    templates = {
        "exact": " ".join(part for part in (disease, subtype, gene, outcome) if part),
        "synonym": " ".join(part for part in ("ERBB2" if "HER2" in subtype else gene, outcome, "pathological complete response") if part),
        "clinical": " ".join(part for part in (disease, contract.treatment_context or "treatment", outcome) if part),
        "dataset": " ".join(part for part in (disease, gene, "GEO GSE cohort", outcome) if part),
        "outcome": " ".join(part for part in (outcome, "pCR ORR survival", disease) if part),
    }
    now = datetime.now(timezone.utc).isoformat()
    queries = []
    for query_type in QUERY_TYPES:
        text = templates[query_type].strip()
        if not text:
            continue
        queries.append(
            {
                "query_id": f"q-{uuid4().hex[:10]}",
                "query_text": text,
                "query_type": query_type,
                "created_by": "requirement_agent",
                "timestamp": now,
            }
        )
    return queries


def documents_from_texts(rows: list[tuple[str, str, str]]) -> list[RetrievalDocument]:
    return [
        RetrievalDocument(doc_id=doc_id, source_id=source_id, text=text)
        for doc_id, source_id, text in rows
    ]
