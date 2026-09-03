from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated
from urllib.parse import quote
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Response as FastAPIResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from backend.app.agent import (
    AgentConfigurationError,
    AgentConfigurationStatus,
    AgentDatasetExportService,
    AgentExecutionError,
    AgentExportFormat,
    AgentTaskRequest,
    AgentTaskResult,
    ApiCheckRequest,
    ApiCheckResult,
    ApiCheckService,
    QwenClient,
    QwenClientError,
    QwenSessionRegistry,
    QwenSessionRequest,
    QwenSessionStatus,
    ResearchAgentService,
    ResearchTaskCreated,
    ResearchTaskSpec,
    ResearchTaskStatus,
    QualityGateReport,
    ClosedLoopRequest,
    ClosedLoopResponse,
    ClosedLoopService,
)
from backend.app.agent.loop_store import LoopStateStore
from backend.app.export_service import DatasetExportFormat, MockDatasetExportService
from backend.app.evaluation import EvaluationError, EvaluationService, GoldSetCsvLoader
from backend.app.evaluation.overview import EvaluationOverview, build_evaluation_overview
from backend.app.evaluation.models import (
    EvaluationRequest,
    EvaluationResult,
    GoldSetTemplateInspection,
)
from backend.app.evaluation.official_run import OfficialEvaluationLaunch, run_official_evaluation
from backend.app.goldset import GoldSetCurationError, GoldSetCurationService
from backend.app.goldset.models import (
    ErrorConstructionRequest,
    ErrorConstructionResult,
    ErrorReviewedDraft,
    ErrorSecondReviewRequest,
    FieldInitialLabelRequest,
    FieldInitialLabelResult,
    FieldReviewedDraft,
    FieldSecondReviewRequest,
    GoldSetRuleValidationRequest,
    GoldSetRuleValidationResult,
    RetrievalInitialLabelRequest,
    RetrievalInitialLabelResult,
    RetrievalReviewedDraft,
    RetrievalSecondReviewRequest,
    SourceReference,
    SourceVerificationResult,
)
from backend.app.models import MockPipelineResult, ResearchQuestion
from backend.app.governance import SafetyDecisionRequest, SafetyDecisionResult, SafetyLayer
from backend.app.literature import LiteratureScanRequest
from backend.app.retrieval import RetrievalRequest, RetrievalResponse, RetrievalServiceV2
from backend.app.rag import (
    EvidenceQueryRequest,
    EvidenceQueryResponse,
    RAGEvaluationRequest,
    RAGEvaluationResult,
    RAGIndexNotFoundError,
    RAGIndexReport,
    RAGIndexRequest,
    ScientificGraphSnapshot,
)
from backend.app.research_planning import (
    LiteratureScanResponse,
    QuestionCandidateList,
    QuestionSelectionRequest,
    ResearchContract,
    ResearchPlanningNotFoundError,
    ResearchPlanningService,
    ResearchTopic,
    TopicCreateRequest,
)
from backend.app.research_planning_v2 import ResearchPlanningV2Request, ResearchPlanningV2Response, ResearchPlanningV2Service
from backend.app.quality_v2 import (
    ErrorDetectionResult,
    QualityApplyRequest,
    QualityReviewRequest,
    QualityReviewResponse,
    QualityV2Service,
    RepairCandidateResult,
)
from backend.app.quality_v2.models import SafeApplyResult
from backend.app.requirement_agent import RequirementAgentService
from backend.app.contracts.models import ContractFreezeRequest
from backend.app.parsers import ParserRegistry
from backend.app.critic import CriticAgent
from backend.app.rules import RulePackEngine
from backend.app.source_registry_v2 import WeightedSetCoverOptimizer
from backend.app.source_broker import SourcePlanningResult, SourcePlanRequest
from backend.app.v3_api import mount_v3_routes
from backend.app.integration import (
    IntegrationError,
    EntityMatcherV3,
    EntityMatcherV2Plus,
    EntityMatcherV3Request,
    EntityMatcherV3Response,
    PatientSampleLinker,
    NormalizationIntegrationPipeline,
    SchemaMatcherV3,
    SchemaMatcherV2Plus,
    SchemaMatcherV3Request,
    SchemaMatcherV3Response,
)
from backend.app.integration.models import (
    NormalizationIntegrationRequest,
    NormalizationIntegrationResult,
)
from backend.app.repair import RepairError, RepairLoopService
from backend.app.repair.models import (
    ErrorClassificationResult,
    RepairLoopResult,
    RepairRequest,
)
from backend.app.services.mock_pipeline import MockPipeline, UnsupportedMockQuestion
from backend.app.sources.aact import AACTAdapterError, AACTClinicalTrialsAdapter
from backend.app.sources.aact.models import AACTAdapterRequest, AACTAdapterResult
from backend.app.sources.cbioportal import CBioPortalAdapter, CBioPortalAdapterError
from backend.app.sources.cbioportal.models import (
    CBioPortalAdapterRequest,
    CBioPortalAdapterResult,
)
from backend.app.sources.civic import CIViCAdapter, CIViCAdapterError
from backend.app.sources.civic.models import CIViCAdapterRequest, CIViCAdapterResult
from backend.app.sources.gdc import GDCAdapter, GDCAdapterError
from backend.app.sources.gdc.models import GDCAdapterRequest, GDCAdapterResult
from backend.app.sources.geo import GEOAdapter, GEOAdapterError
from backend.app.sources.geo.models import GEOAdapterRequest, GEOAdapterResult


logger = logging.getLogger(__name__)


app = FastAPI(
    title="Breast Cancer Research Data Agent",
    version="2.0.0-qwen-agent",
    description=(
        "Qwen-powered breast cancer research data agent with function calling, "
        "live public-database tools, research-ready cohort construction, Chinese "
        "data annotations, traceable quality controls, and CSV/Parquet/Excel export."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8888",
        "http://127.0.0.1:8888",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
        "http://localhost:8002",
        "http://127.0.0.1:8002",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

pipeline = MockPipeline()
gdc_adapter = GDCAdapter()
geo_adapter = GEOAdapter()
cbioportal_adapter = CBioPortalAdapter()
aact_adapter = AACTClinicalTrialsAdapter()
civic_adapter = CIViCAdapter()
normalization_pipeline = NormalizationIntegrationPipeline()
schema_matcher_v3 = SchemaMatcherV3()
entity_matcher_v3 = EntityMatcherV3()
schema_matcher_v2plus = SchemaMatcherV2Plus()
entity_matcher_v2plus = EntityMatcherV2Plus()
evaluation_service = EvaluationService()
goldset_loader = GoldSetCsvLoader()
goldset_curation_service = GoldSetCurationService()
repair_loop_service = RepairLoopService()
mock_export_service = MockDatasetExportService()
research_agent_service = ResearchAgentService()
closed_loop_service = ClosedLoopService(
    research_agent_service,
    store=LoopStateStore(Path(__file__).resolve().parents[2] / "data" / "state" / "agent.sqlite3"),
)
research_planning_service = ResearchPlanningService()
requirement_agent_service = RequirementAgentService(planning=research_planning_service)
parser_registry = ParserRegistry()
critic_agent = CriticAgent()
rule_pack_engine = RulePackEngine()
source_optimizer = WeightedSetCoverOptimizer()
qwen_session_registry = QwenSessionRegistry()
agent_export_service = AgentDatasetExportService()
api_check_service = ApiCheckService()
vnext_safety_layer = SafetyLayer()
retrieval_service_v2 = RetrievalServiceV2()
research_planning_v2_service = ResearchPlanningV2Service()
quality_v2_service = QualityV2Service()
GOLDSET_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "goldset" / "templates"

mount_v3_routes(
    app,
    requirement_agent=requirement_agent_service,
    parser_registry=parser_registry,
    retrieval_service=retrieval_service_v2,
    critic=critic_agent,
    rules=rule_pack_engine,
    optimizer=source_optimizer,
)


def get_gdc_adapter() -> GDCAdapter:
    return gdc_adapter


def get_geo_adapter() -> GEOAdapter:
    return geo_adapter


def get_cbioportal_adapter() -> CBioPortalAdapter:
    return cbioportal_adapter


def get_aact_adapter() -> AACTClinicalTrialsAdapter:
    return aact_adapter


def get_civic_adapter() -> CIViCAdapter:
    return civic_adapter


def get_normalization_pipeline() -> NormalizationIntegrationPipeline:
    return normalization_pipeline


def get_evaluation_service() -> EvaluationService:
    return evaluation_service


def get_goldset_curation_service() -> GoldSetCurationService:
    return goldset_curation_service


def get_repair_loop_service() -> RepairLoopService:
    return repair_loop_service


def get_research_agent_service() -> ResearchAgentService:
    return research_agent_service


def get_closed_loop_service() -> ClosedLoopService:
    return closed_loop_service


def get_research_planning_service() -> ResearchPlanningService:
    return research_planning_service


def get_qwen_session_registry() -> QwenSessionRegistry:
    return qwen_session_registry


def resolve_qwen_session_client(
    payload: AgentTaskRequest,
    registry: QwenSessionRegistry,
) -> QwenClient | None:
    if not payload.qwen_session_id:
        return None
    client = registry.get(payload.qwen_session_id)
    if client is not None:
        if client.settings.provider != "qwen":
            raise HTTPException(
                status_code=422,
                detail="在线科研任务与两轮闭环仅支持千问会话；DeepSeek 仅可由独立消融脚本替换中间智能体进行对比，不进入生产主链。",
            )
        return client
    if payload.allow_deterministic_fallback or not payload.use_qwen:
        logger.warning("Ignoring stale Qwen session id because fallback is allowed")
        return None
    raise HTTPException(
        status_code=401,
        detail="千问临时会话不存在或已过期，请重新连接 API。",
    )


def get_api_check_service() -> ApiCheckService:
    return api_check_service


def get_quality_v2_service() -> QualityV2Service:
    return quality_v2_service


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "mode": (
            "qwen-agent+function-calling+live-adapters+research-dataset+"
            "traceability+quality-gate+v3-mainline"
        ),
        "version": app.version,
    }


@app.get("/api/agent/architecture")
def agent_architecture() -> dict[str, object]:
    """Expose the runtime Agent boundaries for UI, audit and evaluation."""

    return {
        "architecture_type": "bounded_hybrid_multi_agent_orchestration",
        "architecture_label": "有边界的混合式多 Agent 编排",
        "summary": "一个任务级主 Agent 统一推进，多职责专用 Agent/控制器协作，事实获取、标准化和医学安全由确定性模块负责。",
        "roles": [
            {
                "id": "task_agent",
                "name": "任务级主 Agent",
                "component": "ResearchAgentService",
                "responsibility": "接收任务、编排模型规划和工具、汇总结果、生成科研数据包",
                "does_not": "不直接生成患者事实，不绕过质量门",
            },
            {
                "id": "planning_agents",
                "name": "问题与研究规划 Agent",
                "component": "Qwen Function Calling / ResearchIntentAgent / ResearchFormulationAgent",
                "responsibility": "拆解研究对象、暴露、结局、字段和候选来源",
                "does_not": "不下载数据，不修改原始记录，不做发布裁决",
            },
            {
                "id": "collection_agent",
                "name": "采集与缺口 Agent",
                "component": "CollectionAgent + GoalLoopController",
                "responsibility": "观察缺口、诊断原因、选择尚未尝试的方法和停止条件",
                "does_not": "不跨研究填补患者，不把知识证据当患者事实",
            },
            {
                "id": "critic_agent",
                "name": "独立批评 Agent",
                "component": "CriticAgent",
                "responsibility": "独立检查研究合同、字段覆盖、结局域和证据完整度",
                "does_not": "不直接改写数据，高风险问题进入 review",
            },
            {
                "id": "quality_gate",
                "name": "质量 Agent 与医学规则门",
                "component": "QualityAgent / QualityV2Service / medical_rules.yaml",
                "responsibility": "执行确定性质量、医学安全和发布准入检查",
                "does_not": "不接受模型自证，不自动修复高风险事实",
            },
            {
                "id": "closed_loop",
                "name": "闭环控制器",
                "component": "ClosedLoopService",
                "responsibility": "保存轮次状态，按缺口生成下一轮合法动作，防止重复和空转",
                "does_not": "不修改事实字段，不代替独立审查",
            },
        ],
        "deterministic_modules": [
            "GDC/GEO/cBioPortal/AACT/CIViC/DepMap official adapters",
            "ResearchDatasetBuilder and Schema/Entity Matchers",
            "DataAlignmentAuditor",
            "frozen medical_rules.yaml and RulePackEngine",
        ],
        "context_isolation": [
            "task_id and per-round input/output hashes",
            "study_id/patient_id/sample_id source namespaces",
            "planner, adapter, critic and gate write boundaries",
            "temporary in-memory Qwen sessions",
        ],
        "parallel_policy": {
            "can_parallelize": [
                "independent read-only source lookups sharing one ResearchSpec",
                "candidate retrieval and source health checks without shared writes",
            ],
            "must_serialize": [
                "closed-loop follow-up decisions",
                "shared dataset/entity index writes and merge points",
                "Critic, Quality Gate and medical safety decisions",
            ],
            "current_runtime": "controlled_serial_tool_execution_with_explicit_parallel_tool_intent",
        },
        "independent_validation": [
            "Adapter and schema validation",
            "Critic contract and evidence diagnosis",
            "Quality Agent and frozen medical safety gate",
        ],
        "when_not_to_use_multi_agent": [
            "single-source metadata lookup",
            "deterministic format conversion, normalization or deduplication",
            "strict reproducible offline benchmark baseline",
            "small low-latency request without cross-step reasoning",
        ],
    }


@app.post("/api/v2/governance/decide", response_model=SafetyDecisionResult)
def evaluate_vnext_proposal(payload: SafetyDecisionRequest) -> SafetyDecisionResult:
    """Apply the non-bypassable VNext provenance and medical safety gate."""

    return vnext_safety_layer.evaluate(payload)


@app.post("/api/v2/retrieval/search", response_model=RetrievalResponse)
def search_vnext_documents(payload: RetrievalRequest) -> RetrievalResponse:
    """Run audited retrieval while explicitly disclosing offline fallbacks."""

    return retrieval_service_v2.search(payload)


@app.post("/api/v2/research/plan", response_model=ResearchPlanningV2Response)
def plan_research_v2(payload: ResearchPlanningV2Request) -> ResearchPlanningV2Response:
    """Produce structured questions, variables and study design with source labeling."""

    return research_planning_v2_service.plan(payload)


@app.post("/api/v2/agent/closed-loop", response_model=ClosedLoopResponse)
def run_agent_closed_loop(
    payload: ClosedLoopRequest,
    service: Annotated[ClosedLoopService, Depends(get_closed_loop_service)],
    registry: Annotated[QwenSessionRegistry, Depends(get_qwen_session_registry)],
) -> ClosedLoopResponse:
    """Run bounded self-correction using the previous round's diagnostics."""

    session_client = resolve_qwen_session_client(payload.initial_request, registry)
    try:
        return service.run(payload, qwen_client=session_client)
    except AgentConfigurationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AgentExecutionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/v2/agent/closed-loop/{loop_id}", response_model=ClosedLoopResponse)
def get_agent_closed_loop(
    loop_id: str,
    service: Annotated[ClosedLoopService, Depends(get_closed_loop_service)],
) -> ClosedLoopResponse:
    result = service.get(loop_id)
    if result is None:
        raise HTTPException(status_code=404, detail="闭环任务不存在或服务已重启。")
    return result


@app.get("/api/v2/agent/memory")
def get_agent_memory(
    service: Annotated[ClosedLoopService, Depends(get_closed_loop_service)],
    limit: int = 20,
) -> dict:
    return {"memory": service.recall_memory(limit=limit)}


@app.post("/api/v2/quality/review", response_model=QualityReviewResponse)
def review_quality_v2(
    payload: QualityReviewRequest,
    service: Annotated[QualityV2Service, Depends(get_quality_v2_service)],
) -> QualityReviewResponse:
    return service.review(payload)


@app.post("/api/v2/quality/detect", response_model=ErrorDetectionResult)
def detect_quality_errors_v2(
    payload: QualityReviewRequest,
    service: Annotated[QualityV2Service, Depends(get_quality_v2_service)],
):
    return service.detect(payload)


@app.post("/api/v2/quality/candidates", response_model=RepairCandidateResult)
def generate_quality_candidates_v2(
    payload: QualityReviewRequest,
    service: Annotated[QualityV2Service, Depends(get_quality_v2_service)],
):
    return service.candidates(payload)


@app.post("/api/v2/quality/apply", response_model=SafeApplyResult)
def apply_quality_repairs_v2(
    payload: QualityApplyRequest,
    service: Annotated[QualityV2Service, Depends(get_quality_v2_service)],
):
    return service.apply(payload)


@app.post("/api/v2/schema/match", response_model=SchemaMatcherV3Response)
def match_schema_v3(payload: SchemaMatcherV3Request) -> SchemaMatcherV3Response:
    matches = schema_matcher_v3.match(
        payload.source_fields,
        payload.target_fields,
        source_types=payload.source_types,
        target_types=payload.target_types,
        source_values=payload.source_values,
        target_values=payload.target_values,
        source_table=payload.source_table,
        target_table=payload.target_table,
        source_descriptions=payload.source_descriptions,
        target_descriptions=payload.target_descriptions,
    )
    return SchemaMatcherV3Response(
        matcher_version=schema_matcher_v3.VERSION,
        matches=[{
            "source_field": item.source_field,
            "target_field": item.target_field,
            "confidence": item.confidence,
            "evidence": item.evidence,
            "decision": item.decision,
            "decision_source": item.decision_source,
            "judge_reason": item.judge_reason,
        } for item in matches],
        qwen_invocation_count=schema_matcher_v3.qwen_invocation_count,
    )


@app.post("/api/v2/entity/match", response_model=EntityMatcherV3Response)
def match_entity_v3(payload: EntityMatcherV3Request) -> EntityMatcherV3Response:
    matches = entity_matcher_v3.match(
        payload.left,
        payload.right,
        id_field=payload.id_field,
        study_field=payload.study_field,
        patient_sample_linker=PatientSampleLinker() if payload.linker_authorized else None,
    )
    return EntityMatcherV3Response(
        matcher_version=entity_matcher_v3.VERSION,
        matches=[{
            "left_record_id": item.left_record_id,
            "right_record_id": item.right_record_id,
            "similarity_features": item.similarity_features,
            "model_confidence": item.model_confidence,
            "decision": item.decision,
            "basis": item.basis,
            "safety_rule_hits": item.safety_rule_hits,
            "candidate_generated": item.candidate_generated,
        } for item in matches],
        learned_invocation_count=entity_matcher_v3.learned_invocation_count,
    )


@app.post("/api/v2/schema/match-v2plus", response_model=SchemaMatcherV3Response)
def match_schema_v2plus(payload: SchemaMatcherV3Request) -> SchemaMatcherV3Response:
    matches = schema_matcher_v2plus.match(
        payload.source_fields, payload.target_fields,
        source_types=payload.source_types, target_types=payload.target_types,
        source_values=payload.source_values, target_values=payload.target_values,
        source_table=payload.source_table, target_table=payload.target_table,
        source_descriptions=payload.source_descriptions, target_descriptions=payload.target_descriptions,
    )
    return SchemaMatcherV3Response(
        matcher_version=schema_matcher_v2plus.VERSION,
        matches=[{
            "source_field": item.source_field, "target_field": item.target_field,
            "confidence": item.confidence, "evidence": item.evidence,
            "decision": item.decision, "decision_source": item.decision_source,
            "safety_rule_hits": item.safety_rule_hits,
        } for item in matches],
        qwen_invocation_count=0,
    )


@app.post("/api/v2/entity/match-v2plus", response_model=EntityMatcherV3Response)
def match_entity_v2plus(payload: EntityMatcherV3Request) -> EntityMatcherV3Response:
    matches = entity_matcher_v2plus.match(
        payload.left, payload.right, id_field=payload.id_field, study_field=payload.study_field,
        linker_authorized=payload.linker_authorized,
    )
    return EntityMatcherV3Response(
        matcher_version=entity_matcher_v2plus.VERSION,
        matches=[{
            "left_record_id": item.left_record_id, "right_record_id": item.right_record_id,
            "model_confidence": item.confidence, "decision": item.decision,
            "reason": item.reason, "similarity_features": item.similarity_features,
            "safety_rule_hits": item.safety_rule_hits, "decision_source": item.decision_source,
        } for item in matches],
        learned_invocation_count=0,
    )


@app.get(
    "/api/agent/configuration",
    response_model=AgentConfigurationStatus,
)
def get_agent_configuration(
    service: Annotated[ResearchAgentService, Depends(get_research_agent_service)],
) -> AgentConfigurationStatus:
    return service.configuration()


@app.post("/api/agent/qwen-sessions", response_model=QwenSessionStatus)
def create_qwen_session(
    payload: QwenSessionRequest,
    registry: Annotated[QwenSessionRegistry, Depends(get_qwen_session_registry)],
) -> QwenSessionStatus:
    try:
        return registry.create(payload)
    except QwenClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.delete("/api/agent/qwen-sessions/{session_id}", status_code=204)
def delete_qwen_session(
    session_id: str,
    registry: Annotated[QwenSessionRegistry, Depends(get_qwen_session_registry)],
) -> FastAPIResponse:
    registry.delete(session_id)
    return FastAPIResponse(status_code=204)


@app.post("/api/agent/api-check", response_model=ApiCheckResult)
def check_agent_api(
    payload: ApiCheckRequest,
    service: Annotated[ApiCheckService, Depends(get_api_check_service)],
) -> ApiCheckResult:
    return service.check(payload)


@app.post("/api/agent/tasks", response_model=AgentTaskResult)
def run_agent_task(
    payload: AgentTaskRequest,
    service: Annotated[ResearchAgentService, Depends(get_research_agent_service)],
    registry: Annotated[QwenSessionRegistry, Depends(get_qwen_session_registry)],
) -> AgentTaskResult:
    request_id = f"agent-request-{uuid4().hex[:12]}"
    try:
        session_client = resolve_qwen_session_client(payload, registry)
        return service.run(payload, qwen_client=session_client)
    except AgentConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AgentExecutionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValidationError as exc:
        logger.exception("Agent result validation failed request_id=%s", request_id)
        raise HTTPException(
            status_code=502,
            detail=f"科研结果校验失败（请求编号：{request_id}）：{exc.error_count()} 处字段不合法。",
        ) from exc
    except AttributeError as exc:
        logger.exception("Agent result mapping failed request_id=%s", request_id)
        raise HTTPException(
            status_code=502,
            detail=f"数据源结果解析失败（请求编号：{request_id}）。已隔离未知工具结果，请重启后端后再试。",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        # Keep the browser response actionable while retaining the full traceback in server logs.
        logger.exception("Unexpected agent task failure request_id=%s", request_id)
        raise HTTPException(
            status_code=500,
            detail=(
                f"科研任务执行失败（请求编号：{request_id}）：{type(exc).__name__}。"
                "请重启后端后强制刷新；若持续失败，请提供该请求编号。"
            ),
        ) from exc


@app.post("/api/research/topics", response_model=ResearchTopic)
def create_research_topic(
    payload: TopicCreateRequest,
    service: Annotated[ResearchPlanningService, Depends(get_research_planning_service)],
) -> ResearchTopic:
    return service.create_topic(payload)


@app.post(
    "/api/research/topics/{topic_id}/literature-scan",
    response_model=LiteratureScanResponse,
)
def scan_research_topic_literature(
    topic_id: str,
    payload: LiteratureScanRequest,
    service: Annotated[ResearchPlanningService, Depends(get_research_planning_service)],
) -> LiteratureScanResponse:
    try:
        return service.scan_literature(topic_id, payload)
    except ResearchPlanningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(
    "/api/research/topics/{topic_id}/question-candidates",
    response_model=QuestionCandidateList,
)
def get_research_question_candidates(
    topic_id: str,
    service: Annotated[ResearchPlanningService, Depends(get_research_planning_service)],
) -> QuestionCandidateList:
    try:
        return service.question_candidates(topic_id)
    except ResearchPlanningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/research/questions/{candidate_id}/select", response_model=ResearchContract)
def select_research_question(
    candidate_id: str,
    payload: QuestionSelectionRequest,
    service: Annotated[ResearchPlanningService, Depends(get_research_planning_service)],
) -> ResearchContract:
    try:
        return service.select_question(candidate_id, payload)
    except ResearchPlanningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/research/contracts/{contract_id}", response_model=ResearchContract)
def get_research_contract(
    contract_id: str,
    service: Annotated[ResearchPlanningService, Depends(get_research_planning_service)],
) -> ResearchContract:
    try:
        return service.get_contract(contract_id)
    except ResearchPlanningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/research/contracts/{contract_id}/freeze", response_model=ResearchContract)
def freeze_planning_contract(
    contract_id: str,
    payload: ContractFreezeRequest,
    service: Annotated[ResearchPlanningService, Depends(get_research_planning_service)],
) -> ResearchContract:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="冻结 Research Contract 需要 confirmed=true。")
    try:
        return service.freeze_contract(contract_id)
    except ResearchPlanningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(
    "/api/research/contracts/{contract_id}/source-plan",
    response_model=SourcePlanningResult,
)
def create_research_source_plan(
    contract_id: str,
    payload: SourcePlanRequest,
    service: Annotated[ResearchPlanningService, Depends(get_research_planning_service)],
) -> SourcePlanningResult:
    try:
        return service.plan_sources(contract_id, payload)
    except ResearchPlanningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(
    "/api/research/source-plans/{source_plan_id}",
    response_model=SourcePlanningResult,
)
def get_research_source_plan(
    source_plan_id: str,
    service: Annotated[ResearchPlanningService, Depends(get_research_planning_service)],
) -> SourcePlanningResult:
    try:
        return service.get_source_plan(source_plan_id)
    except ResearchPlanningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(
    "/api/research/topics/{topic_id}/rag-index",
    response_model=RAGIndexReport,
)
def build_research_planning_rag(
    topic_id: str,
    payload: RAGIndexRequest,
    service: Annotated[ResearchPlanningService, Depends(get_research_planning_service)],
) -> RAGIndexReport:
    try:
        return service.build_rag_index(topic_id, payload)
    except (ResearchPlanningNotFoundError, RAGIndexNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/api/research/topics/{topic_id}/evidence-query",
    response_model=EvidenceQueryResponse,
)
def query_research_evidence(
    topic_id: str,
    payload: EvidenceQueryRequest,
    service: Annotated[ResearchPlanningService, Depends(get_research_planning_service)],
) -> EvidenceQueryResponse:
    try:
        return service.query_evidence(topic_id, payload)
    except (ResearchPlanningNotFoundError, RAGIndexNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(
    "/api/research/topics/{topic_id}/knowledge-graph",
    response_model=ScientificGraphSnapshot,
)
def get_research_knowledge_graph(
    topic_id: str,
    service: Annotated[ResearchPlanningService, Depends(get_research_planning_service)],
) -> ScientificGraphSnapshot:
    try:
        return service.knowledge_graph(topic_id)
    except (ResearchPlanningNotFoundError, RAGIndexNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(
    "/api/research/topics/{topic_id}/rag-evaluate",
    response_model=RAGEvaluationResult,
)
def evaluate_research_planning_rag(
    topic_id: str,
    payload: RAGEvaluationRequest,
    service: Annotated[ResearchPlanningService, Depends(get_research_planning_service)],
) -> RAGEvaluationResult:
    try:
        return service.evaluate_rag(topic_id, payload)
    except (ResearchPlanningNotFoundError, RAGIndexNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/research/task", response_model=ResearchTaskCreated)
def create_research_task(
    payload: AgentTaskRequest,
    service: Annotated[ResearchAgentService, Depends(get_research_agent_service)],
    registry: Annotated[QwenSessionRegistry, Depends(get_qwen_session_registry)],
) -> ResearchTaskCreated:
    session_client = resolve_qwen_session_client(payload, registry)
    status = service.start(payload, qwen_client=session_client)
    return ResearchTaskCreated(task_id=status.task_id, status=status.status)


@app.get("/api/task/status/{task_id}", response_model=ResearchTaskStatus)
def get_research_task_status(
    task_id: str,
    service: Annotated[ResearchAgentService, Depends(get_research_agent_service)],
) -> ResearchTaskStatus:
    status = service.status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="科研任务不存在或服务已重启。")
    return status


@app.get("/api/task/spec/{task_id}", response_model=ResearchTaskSpec)
def get_research_task_spec(
    task_id: str,
    service: Annotated[ResearchAgentService, Depends(get_research_agent_service)],
) -> ResearchTaskSpec:
    result = service.get(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="科研方案尚未生成，或不存在该任务。")
    return ResearchTaskSpec(
        task_id=result.task_id,
        question_parse=result.parsed_question,
        study_design=result.study_design,
    )


@app.get("/api/task/report/{task_id}", response_model=QualityGateReport)
def get_research_task_report(
    task_id: str,
    service: Annotated[ResearchAgentService, Depends(get_research_agent_service)],
) -> QualityGateReport:
    result = service.get(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="质量报告尚未生成，或不存在该任务。")
    if result.quality_gate_report is None:
        raise HTTPException(status_code=404, detail="当前任务没有质量门报告。")
    return result.quality_gate_report


@app.get("/api/agent/tasks/latest", response_model=AgentTaskResult)
def get_latest_agent_task(
    service: Annotated[ResearchAgentService, Depends(get_research_agent_service)],
) -> AgentTaskResult:
    result = service.latest()
    if result is None:
        raise HTTPException(status_code=404, detail="还没有已完成的科研任务，或服务已重启。")
    return result


@app.get("/api/agent/tasks/{task_id}", response_model=AgentTaskResult)
def get_agent_task(
    task_id: str,
    service: Annotated[ResearchAgentService, Depends(get_research_agent_service)],
) -> AgentTaskResult:
    result = service.get(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="科研任务不存在或服务已重启。")
    return result


@app.get("/api/agent/tasks/{task_id}/export/{file_format}")
def export_agent_task(
    task_id: str,
    file_format: AgentExportFormat,
    service: Annotated[ResearchAgentService, Depends(get_research_agent_service)],
) -> Response:
    result = service.get(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="科研任务不存在或服务已重启。")
    try:
        exported = agent_export_service.export(result, file_format)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=exported.content,
        media_type=exported.media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(exported.filename)}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.post("/api/tasks/mock", response_model=MockPipelineResult)
def run_mock_task(payload: ResearchQuestion) -> MockPipelineResult:
    try:
        return pipeline.run(payload.question)
    except UnsupportedMockQuestion as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"Mock pipeline failed: {exc}") from exc


@app.post("/api/tasks/mock/export/{file_format}")
def export_mock_task(
    file_format: DatasetExportFormat,
    payload: ResearchQuestion,
) -> Response:
    try:
        result = pipeline.run(payload.question)
        exported = mock_export_service.export(result, file_format)
        return Response(
            content=exported.content,
            media_type=exported.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{exported.filename}"',
                "X-Content-Type-Options": "nosniff",
            },
        )
    except UnsupportedMockQuestion as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"Mock export failed: {exc}") from exc


@app.post("/api/adapters/gdc", response_model=GDCAdapterResult)
def run_gdc_adapter(
    payload: GDCAdapterRequest,
    adapter: Annotated[GDCAdapter, Depends(get_gdc_adapter)],
) -> GDCAdapterResult:
    try:
        return adapter.run(payload)
    except GDCAdapterError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc


@app.post("/api/adapters/geo", response_model=GEOAdapterResult)
def run_geo_adapter(
    payload: GEOAdapterRequest,
    adapter: Annotated[GEOAdapter, Depends(get_geo_adapter)],
) -> GEOAdapterResult:
    try:
        return adapter.run(payload)
    except GEOAdapterError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc


@app.post("/api/adapters/cbioportal", response_model=CBioPortalAdapterResult)
def run_cbioportal_adapter(
    payload: CBioPortalAdapterRequest,
    adapter: Annotated[CBioPortalAdapter, Depends(get_cbioportal_adapter)],
) -> CBioPortalAdapterResult:
    try:
        return adapter.run(payload)
    except CBioPortalAdapterError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc


@app.post("/api/adapters/aact", response_model=AACTAdapterResult)
def run_aact_adapter(
    payload: AACTAdapterRequest,
    adapter: Annotated[AACTClinicalTrialsAdapter, Depends(get_aact_adapter)],
) -> AACTAdapterResult:
    try:
        return adapter.run(payload)
    except AACTAdapterError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc


@app.post("/api/adapters/civic", response_model=CIViCAdapterResult)
def run_civic_adapter(
    payload: CIViCAdapterRequest,
    adapter: Annotated[CIViCAdapter, Depends(get_civic_adapter)],
) -> CIViCAdapterResult:
    try:
        return adapter.run(payload)
    except CIViCAdapterError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc


@app.post(
    "/api/integration/normalize",
    response_model=NormalizationIntegrationResult,
)
def run_normalization_integration(
    payload: NormalizationIntegrationRequest,
    service: Annotated[
        NormalizationIntegrationPipeline,
        Depends(get_normalization_pipeline),
    ],
) -> NormalizationIntegrationResult:
    try:
        return service.run(payload)
    except IntegrationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc


@app.get("/api/evaluation/overview", response_model=EvaluationOverview)
def get_evaluation_overview(
    agent: Annotated[ResearchAgentService, Depends(get_research_agent_service)],
) -> EvaluationOverview:
    inspection = goldset_loader.inspect(GOLDSET_TEMPLATE_DIR)
    return build_evaluation_overview(
        latest_task=agent.latest(),
        goldset_row_counts=inspection.row_counts,
    )


@app.get(
    "/api/evaluation/goldset/templates",
    response_model=GoldSetTemplateInspection,
)
def inspect_goldset_templates() -> GoldSetTemplateInspection:
    try:
        return goldset_loader.inspect(GOLDSET_TEMPLATE_DIR)
    except EvaluationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc


@app.post("/api/evaluation/run", response_model=EvaluationResult)
def run_evaluation(
    payload: EvaluationRequest,
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> EvaluationResult:
    try:
        return service.run(payload)
    except EvaluationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc


@app.post("/api/evaluation/official-run", response_model=EvaluationResult)
def run_official_goldset_evaluation(
    payload: OfficialEvaluationLaunch | None = None,
) -> EvaluationResult:
    body = payload or OfficialEvaluationLaunch()
    retrieval = body.retrieval if body.retrieval in {"planner", "agent"} else "planner"
    try:
        return run_official_evaluation(
            evaluation_id=body.evaluation_id,
            retrieval=retrieval,
            use_qwen=body.use_qwen,
            allow_deterministic_fallback=body.allow_deterministic_fallback,
        )
    except EvaluationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/evaluation/artifacts/{evaluation_id}/{artifact_name}")
def get_evaluation_artifact(
    evaluation_id: str,
    artifact_name: str,
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> FileResponse:
    try:
        path = service.get_artifact(evaluation_id, artifact_name)
    except EvaluationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc
    media_type = "application/json" if artifact_name == "metrics.json" else "text/markdown"
    return FileResponse(path, media_type=media_type, filename=artifact_name)


@app.post(
    "/api/goldset/sources/verify",
    response_model=SourceVerificationResult,
)
def verify_goldset_source(
    payload: SourceReference,
    service: Annotated[
        GoldSetCurationService,
        Depends(get_goldset_curation_service),
    ],
) -> SourceVerificationResult:
    try:
        return service.verify_source(payload)
    except GoldSetCurationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc


@app.post(
    "/api/goldset/retrieval/initial-label",
    response_model=RetrievalInitialLabelResult,
)
def initial_label_retrieval_gold(
    payload: RetrievalInitialLabelRequest,
    service: Annotated[
        GoldSetCurationService,
        Depends(get_goldset_curation_service),
    ],
) -> RetrievalInitialLabelResult:
    try:
        return service.initial_label_retrieval(payload)
    except GoldSetCurationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc


@app.post(
    "/api/goldset/fields/initial-label",
    response_model=FieldInitialLabelResult,
)
def initial_label_field_gold(
    payload: FieldInitialLabelRequest,
    service: Annotated[
        GoldSetCurationService,
        Depends(get_goldset_curation_service),
    ],
) -> FieldInitialLabelResult:
    try:
        return service.initial_label_fields(payload)
    except GoldSetCurationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc


@app.post(
    "/api/goldset/errors/construct",
    response_model=ErrorConstructionResult,
)
def construct_goldset_error_cases(
    payload: ErrorConstructionRequest,
    service: Annotated[
        GoldSetCurationService,
        Depends(get_goldset_curation_service),
    ],
) -> ErrorConstructionResult:
    try:
        return service.construct_error_cases(payload)
    except GoldSetCurationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc


@app.post(
    "/api/goldset/reviews/retrieval",
    response_model=RetrievalReviewedDraft,
)
def review_retrieval_gold(
    payload: RetrievalSecondReviewRequest,
    service: Annotated[
        GoldSetCurationService,
        Depends(get_goldset_curation_service),
    ],
) -> RetrievalReviewedDraft:
    try:
        return service.review_retrieval(payload)
    except GoldSetCurationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc


@app.post(
    "/api/goldset/reviews/field",
    response_model=FieldReviewedDraft,
)
def review_field_gold(
    payload: FieldSecondReviewRequest,
    service: Annotated[
        GoldSetCurationService,
        Depends(get_goldset_curation_service),
    ],
) -> FieldReviewedDraft:
    try:
        return service.review_field(payload)
    except GoldSetCurationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc


@app.post(
    "/api/goldset/reviews/error",
    response_model=ErrorReviewedDraft,
)
def review_error_gold(
    payload: ErrorSecondReviewRequest,
    service: Annotated[
        GoldSetCurationService,
        Depends(get_goldset_curation_service),
    ],
) -> ErrorReviewedDraft:
    try:
        return service.review_error(payload)
    except GoldSetCurationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc


@app.post(
    "/api/goldset/validate",
    response_model=GoldSetRuleValidationResult,
)
def validate_goldset_rules(
    payload: GoldSetRuleValidationRequest,
    service: Annotated[
        GoldSetCurationService,
        Depends(get_goldset_curation_service),
    ],
) -> GoldSetRuleValidationResult:
    try:
        return service.validate_rules(payload)
    except GoldSetCurationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc


@app.post(
    "/api/repair/classify",
    response_model=ErrorClassificationResult,
)
def classify_repair_errors(
    payload: RepairRequest,
    service: Annotated[RepairLoopService, Depends(get_repair_loop_service)],
) -> ErrorClassificationResult:
    try:
        return service.classify(payload)
    except RepairError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc


@app.post(
    "/api/repair/run",
    response_model=RepairLoopResult,
)
def run_repair_loop(
    payload: RepairRequest,
    service: Annotated[RepairLoopService, Depends(get_repair_loop_service)],
) -> RepairLoopResult:
    try:
        return service.run(payload)
    except RepairError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc


FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
