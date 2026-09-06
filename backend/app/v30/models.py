from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from backend.app.contracts.models import FrozenResearchContract
from backend.app.models import ApiModel


class RouteKind(str, Enum):
    CHAT = "CHAT"
    CONCEPT_QA = "CONCEPT_QA"
    CLARIFY = "CLARIFY"
    PLAN = "PLAN"


class RouteDecision(ApiModel):
    route: RouteKind
    domain: str
    fallback: bool = False
    reason: str
    confidence: float = 0.0


class ResearchGoal(ApiModel):
    object: str | None = None
    target: str | None = None
    domain: str | None = None
    raw_text: str | None = None


class DataNeedSuggestion(ApiModel):
    category: str
    description: str
    retrieval_status: str = "not_retrieved"


class ClarifyingQuestion(ApiModel):
    question_id: str
    question: str
    options: list[str] = []


class ClarificationRecord(ApiModel):
    question_id: str
    question: str
    answer: str | None = None


class MemorySnapshot(ApiModel):
    session_id: str
    goal: ResearchGoal | None = None
    clarifications: list[ClarificationRecord] = []
    constraints: list[str] = []


class MemoryPatch(ApiModel):
    goal: ResearchGoal | None = None
    clarifications: list[ClarificationRecord] | None = None
    constraints: list[str] | None = None


class RouteRequest(ApiModel):
    message: str = ""
    session_id: str | None = None


class SessionCreateResponse(ApiModel):
    session_id: str
    memory: MemorySnapshot


class CopilotTurnRequest(ApiModel):
    message: str = ""
    session_id: str | None = None


class CopilotTurnResponse(ApiModel):
    session_id: str
    route: RouteDecision
    understood_goal: ResearchGoal | None = None
    suggested_data_needs: list[DataNeedSuggestion] = []
    clarifying_questions: list[ClarifyingQuestion] = []
    ready_for_planner: bool = False
    user_visible_reply: str
    blocked_reason: str | None = None
    memory: MemorySnapshot


class PlanRequest(ApiModel):
    session_id: str
    question_override: str | None = None


class PlanningV2View(ApiModel):
    question_generation_source: str
    candidate_count: int
    selected_question: str | None = None
    unresolved_questions: list[str] = []
    notice: str
    fallback_template_only: bool = True


class PlanResponse(ApiModel):
    session_id: str
    compiled_from_session: bool = True
    ready_for_planner: bool = True
    domain: str
    topic: str
    used_existing_services: list[str] = []
    contract_id: str | None = None
    contract_status: str | None = None
    research_goal: str | None = None
    clarify_topic_id: str | None = None
    candidate_count: int = 0
    contract: FrozenResearchContract | None = None
    planning_v2: PlanningV2View | None = None
    notice: str
    memory: MemorySnapshot


class RegistrySource(ApiModel):
    source_key: str
    display_name: str
    domain: str
    resource_kind: str
    modalities: list[str] = []
    fetch_binding: str | None = None
    discovery_binding: str | None = None
    status: str
    integrate_eligible: bool = False


class RegistrySourceList(ApiModel):
    sources: list[RegistrySource] = []
    notice: str = "Registry 只描述来源能力，不是数据源本身，也不会取数。"


class DiscoverRequest(ApiModel):
    domain: str
    topic: str = ""
    contract_id: str | None = None
    required_modalities: list[str] = []
    field_gaps: list[str] = []


class DiscoveryLocator(ApiModel):
    locator_type: str
    value: str | None = None
    note: str = ""


class FieldHypothesis(ApiModel):
    field: str
    hypothesis: str
    coverage_claimed: bool = False
    coverage_status: str = "unknown"


class DiscoveryCandidate(ApiModel):
    candidate_id: str
    source_key: str
    resource_kind: str
    locator: DiscoveryLocator
    source_id: str
    discovered_from: str
    field_hypotheses: list[FieldHypothesis] = []
    verification_status: str
    next_action: str
    registry_status: str
    integrate_eligible: bool = False


class DiscoverResponse(ApiModel):
    domain: str
    topic: str
    candidates: list[DiscoveryCandidate] = []
    notice: str
    fetched: bool = False
    integrated: bool = False


class SelectionContract(ApiModel):
    research_goal: str = ""
    required_fields: list[str] = []
    domain: str = "oncology"
    contract_id: str | None = None
    response_domain: str = "clinical"
    data_granularity: str = "patient"


class SourceSelectionRequest(ApiModel):
    candidates: list[DiscoveryCandidate]
    contract: SelectionContract
    constraints: dict[str, Any] | list[str] = Field(default_factory=dict)


class RankedSourceCandidate(ApiModel):
    candidate_id: str
    source_key: str
    verification_status: str
    registry_status: str
    reason: str
    reason_code: str
    hypothesized_fields: list[str] = []
    candidate: DiscoveryCandidate


class SelectedSourcePlan(ApiModel):
    selected_candidates: list[RankedSourceCandidate] = []
    rejected_candidates: list[RankedSourceCandidate] = []
    coverage_summary: dict[str, Any] = {}
    selection_reason: list[str] = []
    join_risk: list[str] = []
    response_domain: str = "clinical"
    fetched: bool = False
    integrated: bool = False
    notice: str = ""


class SchemaPackRequest(ApiModel):
    domain: str
    research_goal: str = ""
    topic: str = ""
    required_fields: list[str] = []
    selected_sources: list[str] = []
    contract_id: str | None = None


class SchemaPackField(ApiModel):
    name: str
    field_description: str
    data_type: str
    required: bool
    source_requirements: list[str] = []
    risk_level: str
    allowed: list[str] = []
    frozen: bool = False


class SchemaPack(ApiModel):
    schema_pack_id: str
    domain: str
    entity_type: str
    binding: str
    status: str
    fields: list[SchemaPackField] = []
    selected_sources: list[str] = []
    row_count: int = 0
    generates_data: bool = False
    canonical_schema_path: str | None = None
    notice: str = ""


class SchemaMatchRequest(ApiModel):
    schema_pack_id: str
    source_fields: list[str]
    source_types: dict[str, str] = Field(default_factory=dict)


class FieldMapping(ApiModel):
    source_field: str
    target_field: str
    confidence: float
    status: str
    risk_level: str


class FieldMappingResult(ApiModel):
    schema_pack_id: str
    domain: str
    mappings: list[FieldMapping] = []
    matcher_version: str
    row_count: int = 0
    generates_data: bool = False
    notice: str = ""


class GraphNode(ApiModel):
    node_id: str
    node_type: str
    label: str
    refs: dict[str, Any] = Field(default_factory=dict)
    reasons: list[str] = []


class GraphEdge(ApiModel):
    edge_id: str
    edge_type: str
    from_id: str
    to_id: str
    reason: str = ""


class EvidenceGraph(ApiModel):
    graph_id: str
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    notice: str = "投影层只记录来源选择、字段映射与质量标记原因，不替代 EvidenceBuilder，不含患者关系或事实值。"
    replaces_evidence_builder: bool = False
    contains_patient_edges: bool = False
    copies_fact_values: bool = False


class GraphProjectRequest(ApiModel):
    goal: ResearchGoal | None = None
    contract: SelectionContract | None = None
    candidates: list[DiscoveryCandidate] = []
    selection: SelectedSourcePlan | None = None
    schema_pack: SchemaPack | None = None
    mappings: FieldMappingResult | None = None
    constraints: list[str] = []


class GraphWhyResponse(ApiModel):
    graph_id: str
    finding_id: str
    statement: str
    why: list[str] = []
    path: list[GraphNode] = []
    edges: list[GraphEdge] = []
    forbidden_edges_present: bool = False


class FigureUnderstandRequest(ApiModel):
    source_id: str | None = None
    figure_id: str = ""
    caption: str = ""
    optional_image_reference: str | None = None
    graph_id: str | None = None


class FigureUnderstandingResult(ApiModel):
    source_id: str
    figure_id: str = ""
    caption: str = ""
    figure_type: str
    x_axis: str = ""
    y_axis: str = ""
    legend_summary: str = ""
    extractability: str
    digitization_possible: bool = False
    confidence: float
    status: str
    enters_primary_table: bool = False
    notice: str = "理解演示，非主表数据。即使可数字化也不写入 CanonicalRecord。"
    graph_id: str | None = None
    row_count: int = 0
    generates_data: bool = False


class PreviewSourceRef(ApiModel):
    source_key: str
    candidate_id: str = ""
    hypothesized_fields: list[str] = []
    verification_status: str = "unverified"
    registry_status: str = "active"


class IntegrationPreviewRequest(ApiModel):
    selected_sources: list[PreviewSourceRef] | list[str] = Field(default_factory=list)
    schema_pack_id: str
    field_mappings: list[FieldMapping] = []
    contract_id: str | None = None
    domain: str = ""
    response_domain: str = "clinical"
    research_goal: str = ""
    data_granularity: str = "patient"


class AdapterCandidate(ApiModel):
    source_key: str
    fetch_binding: str | None = None
    integrate_eligible: bool = False
    would_invoke: bool = False
    note: str = ""


class IntegrationPlan(ApiModel):
    plan_id: str
    contract_id: str | None = None
    schema_pack_id: str
    sources: list[str] = []
    selected_sources: list[str] = []
    adapter_candidates: list[AdapterCandidate] = []
    field_mappings: list[FieldMapping] = []
    field_requirements: list[str] = []
    expected_outputs: list[str] = []
    join_policy: str
    execution_allowed: bool = False
    fetched: bool = False
    integrated: bool = False
    generates_data: bool = False
    row_count: int = 0
    medical_constraints: list[str] = []
    notice: str = "这是执行前规划，不是数据执行。execution_allowed=false。"


class ExecutionRequestPreview(ApiModel):
    plan_id: str
    contract_id: str | None = None
    schema_pack_id: str
    selected_sources: list[str] = []
    tool_candidates: list[str] = []
    required_fields: list[str] = []
    execution_ready: bool = False
    executed: bool = False
    join_policy: str = ""
    medical_constraints: list[str] = []
    field_mappings: list[FieldMapping] = []
    generates_data: bool = False
    row_count: int = 0
    fetched: bool = False
    integrated: bool = False
    domain: str = ""
    question: str = ""
    notice: str = "已编译为旧执行系统可理解的请求预览，尚未调用旧执行引擎。"


class ExecutionResult(ApiModel):
    task_id: str
    status: str
    export_available: bool = False
    quality_status: str = ""
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    domain: str = "oncology"
    executed: bool = True
    schema_pack_id: str = ""
    selected_sources: list[str] = []
    tool_candidates: list[str] = []
    required_fields: list[str] = []
    join_policy: str = ""
    medical_constraints: list[str] = []
    export_formats: list[str] = []
    notice: str = "已转调现有执行链。v30 不直接调用 Adapter。"
