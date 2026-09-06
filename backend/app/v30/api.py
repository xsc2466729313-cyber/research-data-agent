from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from backend.app.research_planning_v2 import ResearchPlanningV2Service
from backend.app.v30.memory.service import SessionNotFoundError
from backend.app.v30.models import (
    CopilotTurnRequest,
    CopilotTurnResponse,
    DiscoverRequest,
    DiscoverResponse,
    EvidenceGraph,
    FieldMappingResult,
    FigureUnderstandingResult,
    FigureUnderstandRequest,
    GraphProjectRequest,
    GraphWhyResponse,
    ExecutionRequestPreview,
    ExecutionResult,
    IntegrationPlan,
    IntegrationPreviewRequest,
    MemorySnapshot,
    PlanRequest,
    PlanResponse,
    RegistrySourceList,
    RouteDecision,
    RouteRequest,
    SchemaMatchRequest,
    SchemaPack,
    SchemaPackRequest,
    SelectedSourcePlan,
    SessionCreateResponse,
    SourceSelectionRequest,
)
from backend.app.v30.bridges.execution import ExecutionBridge
from backend.app.v30.discovery.service import DiscoveryFacade
from backend.app.v30.figures.service import FigureUnderstandingService, SourceIdRequiredError
from backend.app.v30.graph.service import GraphService
from backend.app.v30.graph.store import GraphNotFoundError
from backend.app.v30.integration.executor import (
    ExecutionNotReadyError,
    OncologyIntegrateNotAllowedError,
    RunnerNotInjectedError,
)
from backend.app.v30.integration.service import IntegrationPreviewService
from backend.app.v30.planner.service import PlannerFacade, PlannerNotReadyError
from backend.app.v30.registry.service import SourceRegistryService
from backend.app.v30.runtime import V30Runtime
from backend.app.v30.matcher_bridge.service import SchemaMatcherBridge
from backend.app.v30.schema_generator.service import SchemaPackGenerator, SchemaPackNotFoundError
from backend.app.v30.source_selection.service import SourceSelectionService


def mount_v30_routes(app: FastAPI) -> None:
    runtime = getattr(app.state, "v30_runtime", None)
    if runtime is None:
        runtime = V30Runtime()
        app.state.v30_runtime = runtime
    if getattr(app.state, "research_planning_v2", None) is None:
        app.state.research_planning_v2 = ResearchPlanningV2Service()
    if getattr(app.state, "v30_registry", None) is None:
        app.state.v30_registry = SourceRegistryService()
    if getattr(app.state, "v30_schema_generator", None) is None:
        app.state.v30_schema_generator = SchemaPackGenerator()
    if getattr(app.state, "v30_graph", None) is None:
        app.state.v30_graph = GraphService()

    @app.post("/api/v30/sessions", response_model=SessionCreateResponse)
    def create_v30_session() -> SessionCreateResponse:
        memory = runtime.create_session()
        return SessionCreateResponse(session_id=memory.session_id, memory=memory)

    @app.get("/api/v30/sessions/{session_id}/memory", response_model=MemorySnapshot)
    def get_v30_memory(session_id: str) -> MemorySnapshot:
        try:
            return runtime.get_memory(session_id)
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"session not found: {exc}") from exc

    @app.post("/api/v30/route", response_model=RouteDecision)
    def route_v30_message(payload: RouteRequest) -> RouteDecision:
        return runtime.route(payload)

    @app.post("/api/v30/copilot/turn", response_model=CopilotTurnResponse)
    def copilot_turn(payload: CopilotTurnRequest) -> CopilotTurnResponse:
        return runtime.turn(payload)

    @app.post("/api/v30/plan", response_model=PlanResponse)
    def plan_v30_session(payload: PlanRequest):
        try:
            planner = PlannerFacade(
                requirement_agent=app.state.requirement_agent,
                planning_v2=app.state.research_planning_v2,
            )
            return runtime.plan(payload, planner=planner)
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"session not found: {exc}") from exc
        except PlannerNotReadyError:
            return JSONResponse(status_code=422, content={"error": "research_goal_not_ready"})

    @app.get("/api/v30/registry/sources", response_model=RegistrySourceList)
    def list_v30_registry_sources(
        domain: str | None = None,
        status: str | None = None,
        integrate_eligible: bool | None = None,
    ) -> RegistrySourceList:
        return app.state.v30_registry.list_sources(
            domain=domain,
            status=status,
            integrate_eligible=integrate_eligible,
        )

    @app.post("/api/v30/discover", response_model=DiscoverResponse)
    def discover_v30_sources(payload: DiscoverRequest) -> DiscoverResponse:
        discovery = DiscoveryFacade(registry=app.state.v30_registry)
        return discovery.discover(payload)

    @app.post("/api/v30/source-selection", response_model=SelectedSourcePlan)
    def select_v30_sources(payload: SourceSelectionRequest) -> SelectedSourcePlan:
        selector = SourceSelectionService(registry=app.state.v30_registry)
        return selector.select(payload)

    @app.post("/api/v30/schema-packs/generate", response_model=SchemaPack)
    def generate_v30_schema_pack(payload: SchemaPackRequest) -> SchemaPack:
        try:
            return app.state.v30_schema_generator.generate(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/v30/schema-packs/{schema_pack_id}", response_model=SchemaPack)
    def get_v30_schema_pack(schema_pack_id: str) -> SchemaPack:
        try:
            return app.state.v30_schema_generator.get(schema_pack_id)
        except SchemaPackNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"schema pack not found: {exc}") from exc

    @app.post("/api/v30/schema-packs/match", response_model=FieldMappingResult)
    def match_v30_schema_pack(payload: SchemaMatchRequest) -> FieldMappingResult:
        bridge = SchemaMatcherBridge(generator=app.state.v30_schema_generator)
        try:
            return bridge.map_fields(payload)
        except SchemaPackNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"schema pack not found: {exc}") from exc

    @app.post("/api/v30/graphs/project", response_model=EvidenceGraph)
    def project_v30_graph(payload: GraphProjectRequest) -> EvidenceGraph:
        return app.state.v30_graph.project(payload)

    @app.get("/api/v30/graphs/{graph_id}", response_model=EvidenceGraph)
    def get_v30_graph(graph_id: str) -> EvidenceGraph:
        try:
            return app.state.v30_graph.get(graph_id)
        except GraphNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"graph not found: {exc}") from exc

    @app.get("/api/v30/graphs/{graph_id}/why/{finding_id}", response_model=GraphWhyResponse)
    def get_v30_graph_why(graph_id: str, finding_id: str) -> GraphWhyResponse:
        try:
            return app.state.v30_graph.why(graph_id, finding_id)
        except GraphNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"graph finding not found: {exc}") from exc

    @app.post("/api/v30/figures/understand", response_model=FigureUnderstandingResult)
    def understand_v30_figure(payload: FigureUnderstandRequest):
        try:
            return FigureUnderstandingService(graph=app.state.v30_graph).understand(payload)
        except SourceIdRequiredError:
            return JSONResponse(status_code=422, content={"error": "source_id_required"})

    @app.post("/api/v30/integration/preview", response_model=IntegrationPlan)
    def preview_v30_integration(payload: IntegrationPreviewRequest) -> IntegrationPlan:
        preview = IntegrationPreviewService(
            registry=app.state.v30_registry,
            generator=app.state.v30_schema_generator,
        )
        try:
            return preview.preview(payload)
        except SchemaPackNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"schema pack not found: {exc}") from exc

    @app.post("/api/v30/integration/prepare", response_model=ExecutionRequestPreview)
    def prepare_v30_execution(payload: IntegrationPlan) -> ExecutionRequestPreview:
        return ExecutionBridge(
            registry=app.state.v30_registry,
            generator=app.state.v30_schema_generator,
        ).prepare(payload)

    @app.post("/api/v30/integration/execute", response_model=ExecutionResult)
    def execute_v30_integration(payload: ExecutionRequestPreview):
        try:
            return ExecutionBridge(
                registry=app.state.v30_registry,
                generator=app.state.v30_schema_generator,
            ).execute(payload, runner=getattr(app.state, "research_agent", None))
        except OncologyIntegrateNotAllowedError:
            return JSONResponse(status_code=422, content={"error": "only_oncology_integrate_supported"})
        except ExecutionNotReadyError:
            return JSONResponse(status_code=422, content={"error": "execution_not_ready"})
        except RunnerNotInjectedError:
            return JSONResponse(status_code=503, content={"error": "old_runner_not_injected"})
