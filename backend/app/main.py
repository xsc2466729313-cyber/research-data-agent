from __future__ import annotations

from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Response as FastAPIResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

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
    ModelComparisonReport,
    ModelEvaluationGenerateRequest,
    ModelEvaluationRunRequest,
    ModelEvaluationService,
)
from backend.app.export_service import DatasetExportFormat, MockDatasetExportService
from backend.app.evaluation import EvaluationError, EvaluationService, GoldSetCsvLoader
from backend.app.evaluation.models import (
    EvaluationRequest,
    EvaluationResult,
    GoldSetTemplateInspection,
)
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
from backend.app.integration import IntegrationError, NormalizationIntegrationPipeline
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
evaluation_service = EvaluationService()
goldset_loader = GoldSetCsvLoader()
goldset_curation_service = GoldSetCurationService()
repair_loop_service = RepairLoopService()
mock_export_service = MockDatasetExportService()
research_agent_service = ResearchAgentService()
qwen_session_registry = QwenSessionRegistry()
agent_export_service = AgentDatasetExportService()
api_check_service = ApiCheckService()
model_evaluation_service = ModelEvaluationService()
GOLDSET_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "goldset" / "templates"


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


def get_qwen_session_registry() -> QwenSessionRegistry:
    return qwen_session_registry


def get_api_check_service() -> ApiCheckService:
    return api_check_service


def get_model_evaluation_service() -> ModelEvaluationService:
    return model_evaluation_service


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "mode": (
            "qwen-agent+function-calling+live-adapters+research-dataset+"
            "traceability+quality-gate"
        ),
        "version": app.version,
    }


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


@app.post(
    "/api/evaluation/model-tests/generate",
    response_model=ModelComparisonReport,
)
def generate_model_evaluation_plan(
    payload: ModelEvaluationGenerateRequest,
    service: Annotated[ModelEvaluationService, Depends(get_model_evaluation_service)],
    registry: Annotated[QwenSessionRegistry, Depends(get_qwen_session_registry)],
) -> ModelComparisonReport:
    client = None
    if payload.qwen_session_id:
        client = registry.get(payload.qwen_session_id)
        if client is None:
            raise HTTPException(status_code=401, detail="千问临时会话不存在或已过期，请重新连接 API。")
    return service.generate(payload, qwen_client=client)


@app.post(
    "/api/evaluation/model-tests/run",
    response_model=ModelComparisonReport,
)
def run_model_evaluation(
    payload: ModelEvaluationRunRequest,
    service: Annotated[ModelEvaluationService, Depends(get_model_evaluation_service)],
    registry: Annotated[QwenSessionRegistry, Depends(get_qwen_session_registry)],
) -> ModelComparisonReport:
    if not payload.qwen_session_id:
        raise HTTPException(status_code=401, detail="真实多模型测试需要临时千问会话；计划模式不会填入成绩。")
    client = registry.get(payload.qwen_session_id)
    if client is None:
        raise HTTPException(status_code=401, detail="千问临时会话不存在或已过期，请重新连接 API。")
    try:
        return service.run(payload, client)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(
    "/api/evaluation/model-tests/{report_id}",
    response_model=ModelComparisonReport,
)
def get_model_evaluation(
    report_id: str,
    service: Annotated[ModelEvaluationService, Depends(get_model_evaluation_service)],
) -> ModelComparisonReport:
    report = service.get(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="多模型测试报告不存在或服务已重启。")
    return report


@app.get("/api/evaluation/model-tests/{report_id}/export/xlsx")
def export_model_evaluation(
    report_id: str,
    service: Annotated[ModelEvaluationService, Depends(get_model_evaluation_service)],
) -> Response:
    try:
        content = service.export_xlsx(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(report_id + '-多模型对比报告.xlsx')}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.post("/api/agent/tasks", response_model=AgentTaskResult)
def run_agent_task(
    payload: AgentTaskRequest,
    service: Annotated[ResearchAgentService, Depends(get_research_agent_service)],
    registry: Annotated[QwenSessionRegistry, Depends(get_qwen_session_registry)],
) -> AgentTaskResult:
    try:
        session_client: QwenClient | None = None
        if payload.qwen_session_id:
            session_client = registry.get(payload.qwen_session_id)
            if session_client is None:
                raise HTTPException(
                    status_code=401,
                    detail="千问临时会话不存在或已过期，请重新连接 API。",
                )
        return service.run(payload, qwen_client=session_client)
    except AgentConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AgentExecutionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
