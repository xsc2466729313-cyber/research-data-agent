from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import Field

from backend.app.contracts.models import (
    ClarifyRequest,
    ClarifyResponse,
    ContractCreateRequest,
    ContractFreezeRequest,
    FrozenResearchContract,
)
from backend.app.critic import CriticAgent, CriticReport
from backend.app.models import ApiModel
from backend.app.parsers import ParseRequest, ParseResult, ParserRegistry
from backend.app.requirement_agent import RequirementAgentService
from backend.app.research_planning.service import ResearchPlanningNotFoundError
from backend.app.retrieval.contract_queries import expand_contract_queries
from backend.app.retrieval.models import RetrievalRequest, RetrievalResponse
from backend.app.retrieval.service import RetrievalServiceV2
from backend.app.rules import RulePackEngine
from backend.app.source_broker.models import DatasetCandidate, FieldCoverageCell, FieldCoverageMatrix
from backend.app.source_registry_v2 import WeightedSetCoverOptimizer


class ReviewItem(ApiModel):
    review_id: str = Field(default="")
    category: Literal["identity", "her2", "repair", "provenance"]
    summary: str
    status: Literal["OPEN", "ACCEPTED", "REJECTED", "EDITED", "DEFERRED"] = "OPEN"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReviewDecisionRequest(ApiModel):
    decision: Literal["ACCEPT", "REJECT", "EDIT", "DEFER"]
    note: str | None = None


class CriticRequest(ApiModel):
    contract: FrozenResearchContract | None = None
    required_coverage: dict[str, float] = Field(default_factory=dict)
    target_match: bool | None = None
    row_count: int = 0
    forbidden_join: bool = False
    unresolved_identity: bool = False
    provenance_complete: bool = True


class DiscoveryOptimizeRequest(ApiModel):
    required_fields: list[str] = Field(min_length=1)
    candidates: list[DatasetCandidate]
    cells: list[FieldCoverageCell]
    max_selected: int = Field(default=3, ge=1, le=6)


class FieldEvidenceResponse(ApiModel):
    record_id: str
    field: str
    normalized_value: Any = None
    raw_field: str | None = None
    raw_value: Any = None
    source_id: str | None = None
    transform_type: str = "RULE"
    rule_validated: bool = True
    agent_proposed: bool = False


def mount_v3_routes(
    app: FastAPI,
    *,
    requirement_agent: RequirementAgentService,
    parser_registry: ParserRegistry,
    retrieval_service: RetrievalServiceV2,
    critic: CriticAgent,
    rules: RulePackEngine,
    optimizer: WeightedSetCoverOptimizer,
) -> None:
    reviews: dict[str, ReviewItem] = {}

    app.state.requirement_agent = requirement_agent
    app.state.parser_registry = parser_registry
    app.state.retrieval_service = retrieval_service
    app.state.critic = critic
    app.state.rules = rules
    app.state.optimizer = optimizer
    app.state.reviews = reviews

    def _planning_error(exc: Exception) -> HTTPException:
        if isinstance(exc, ResearchPlanningNotFoundError):
            return HTTPException(status_code=404, detail=str(exc))
        return HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/v3/research/clarify", response_model=ClarifyResponse)
    def clarify_research(payload: ClarifyRequest) -> ClarifyResponse:
        return app.state.requirement_agent.clarify(payload)

    @app.post("/api/v3/research/contracts", response_model=FrozenResearchContract)
    def create_research_contract(payload: ContractCreateRequest) -> FrozenResearchContract:
        try:
            return app.state.requirement_agent.create_contract(payload)
        except Exception as exc:
            raise _planning_error(exc) from exc

    @app.post("/api/v3/research/contracts/{contract_id}/freeze", response_model=FrozenResearchContract)
    def freeze_research_contract(contract_id: str, payload: ContractFreezeRequest) -> FrozenResearchContract:
        if not payload.confirmed:
            raise HTTPException(status_code=422, detail="冻结 Research Contract 需要 confirmed=true。")
        try:
            return app.state.requirement_agent.freeze(contract_id)
        except Exception as exc:
            raise _planning_error(exc) from exc

    @app.get("/api/v3/research/contracts/{contract_id}", response_model=FrozenResearchContract)
    def get_frozen_contract(contract_id: str) -> FrozenResearchContract:
        try:
            return app.state.requirement_agent.get(contract_id)
        except Exception as exc:
            raise _planning_error(exc) from exc

    @app.post("/api/v3/discovery/sources")
    def optimize_sources(payload: DiscoveryOptimizeRequest) -> dict[str, object]:
        matrix = FieldCoverageMatrix(
            contract_id="inline",
            field_ids=payload.required_fields,
            dataset_ids=[item.dataset_id for item in payload.candidates],
            cells=payload.cells,
            notice="运行时覆盖仍需官方接口复核。",
        )
        selected, policies, warnings = app.state.optimizer.select(
            required_fields=payload.required_fields,
            candidates=payload.candidates,
            matrix=matrix,
            max_selected=payload.max_selected,
        )
        return {
            "selected_dataset_ids": selected,
            "join_policies": [item.model_dump(mode="json") for item in policies],
            "warnings": warnings,
            "notice": "固定队列策略只作 fallback；此处按覆盖、权威和 Join 约束选择来源。",
        }

    @app.post("/api/v3/parsing/run", response_model=ParseResult)
    def parse_content(payload: ParseRequest) -> ParseResult:
        return app.state.parser_registry.parse(payload)

    @app.post("/api/v3/retrieval/search", response_model=RetrievalResponse)
    def search_hybrid(payload: RetrievalRequest) -> RetrievalResponse:
        request = payload
        if payload.method == "bm25":
            request = payload.model_copy(update={"method": "hybrid_rerank"})
        try:
            return app.state.retrieval_service.search(request)
        except Exception:
            fallback = payload.model_copy(update={"method": "hashing_dense_fallback"})
            response = app.state.retrieval_service.search(fallback)
            telemetry = response.telemetry.model_copy(
                update={"notice": "BGE/Reranker 不可用，已显式回退 hashing；这不是语义检索成绩。"}
            )
            return response.model_copy(update={"telemetry": telemetry})

    @app.post("/api/v3/critic/diagnose", response_model=CriticReport)
    def critic_diagnose(payload: CriticRequest) -> CriticReport:
        return app.state.critic.diagnose(
            contract=payload.contract,
            required_coverage=payload.required_coverage,
            target_match=payload.target_match,
            row_count=payload.row_count,
            forbidden_join=payload.forbidden_join,
            unresolved_identity=payload.unresolved_identity,
            provenance_complete=payload.provenance_complete,
        )

    @app.get("/api/v3/research/contracts/{contract_id}/queries")
    def contract_queries(contract_id: str) -> dict[str, object]:
        try:
            contract = app.state.requirement_agent.get(contract_id)
        except Exception as exc:
            raise _planning_error(exc) from exc
        return {"contract_id": contract_id, "queries": expand_contract_queries(contract)}

    @app.get("/api/v3/review")
    def list_reviews() -> dict[str, object]:
        return {"items": [item.model_dump(mode="json") for item in app.state.reviews.values()]}

    @app.post("/api/v3/review", response_model=ReviewItem)
    def create_review(payload: ReviewItem) -> ReviewItem:
        item = payload.model_copy(update={"review_id": payload.review_id or f"review-{uuid4().hex[:10]}"})
        app.state.reviews[item.review_id] = item
        return item

    @app.post("/api/v3/review/{review_id}/decision", response_model=ReviewItem)
    def decide_review(review_id: str, payload: ReviewDecisionRequest) -> ReviewItem:
        item = app.state.reviews.get(review_id)
        if item is None:
            raise HTTPException(status_code=404, detail="审核项不存在。")
        mapping = {"ACCEPT": "ACCEPTED", "REJECT": "REJECTED", "EDIT": "EDITED", "DEFER": "DEFERRED"}
        updated = item.model_copy(update={"status": mapping[payload.decision]})
        app.state.reviews[review_id] = updated
        return updated

    @app.get("/api/v3/evidence/field/{record_id}/{field}", response_model=FieldEvidenceResponse)
    def field_evidence(record_id: str, field: str, source_id: str | None = None, raw_value: str | None = None) -> FieldEvidenceResponse:
        blocked = app.state.rules.block_publish_without_provenance(source_id, field, raw_value)
        return FieldEvidenceResponse(
            record_id=record_id,
            field=field,
            normalized_value=raw_value,
            raw_field=field,
            raw_value=raw_value,
            source_id=source_id,
            rule_validated=not blocked,
            transform_type="RULE",
        )

    @app.get("/api/v3/rules/publication-gates")
    def publication_gates() -> dict[str, object]:
        return {"gates": app.state.rules.publication_gates()}
