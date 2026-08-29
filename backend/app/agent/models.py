from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import Field, SecretStr

from backend.app.models import ApiModel, CandidateSource, ResearchSpec, SourceItem


class AgentDataMode(str, Enum):
    LIVE = "live"
    PLAN_ONLY = "plan_only"


class AgentTaskRequest(ApiModel):
    question: str = Field(min_length=5, max_length=2000)
    use_qwen: bool = True
    allow_deterministic_fallback: bool = True
    data_mode: AgentDataMode = AgentDataMode.LIVE
    preferred_sources: list[str] = Field(default_factory=list, max_length=20)
    focus_accessions: list[str] = Field(default_factory=list, max_length=20)
    focus_tools: list[str] = Field(default_factory=list, max_length=20)
    remap_outcome_aliases: bool = False
    # This is a budget for retrieval entries, not the number of database
    # types. One task may inspect several GEO accessions or cBioPortal studies.
    max_sources: int = Field(default=8, ge=1, le=20)
    max_records: int = Field(default=10_000, ge=10, le=10_000)
    iterative_collection: bool = True
    max_collection_rounds: int = Field(default=8, ge=1, le=12)
    qwen_session_id: str | None = Field(default=None, min_length=20, max_length=100)


class QwenSessionRequest(ApiModel):
    provider: Literal["qwen"] = "qwen"
    api_key: SecretStr = Field(min_length=10, max_length=500)
    base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        min_length=12,
        max_length=500,
    )
    model: str = Field(default="qwen3.8-max", min_length=2, max_length=100)
    workspace_id: str | None = Field(default=None, max_length=200)
    timeout_seconds: float = Field(default=120, ge=5, le=300)


class QwenSessionStatus(ApiModel):
    session_id: str
    connected: bool = True
    provider: str
    model: str
    base_url: str
    workspace_configured: bool
    expires_at: datetime
    secret_persisted_by_application: bool = False
    message: str


class AgentConfigurationStatus(ApiModel):
    provider: str = "阿里云百炼 / 千问"
    configured: bool
    model: str
    base_url_configured: bool
    workspace_configured: bool
    function_calling: bool = True
    secret_persisted_by_application: bool = False
    message: str


class AgentPlanStep(ApiModel):
    step_id: str
    label: str
    status: str
    detail: str


class AgentToolCall(ApiModel):
    call_id: str
    tool_name: str
    tool_label: str
    arguments: dict[str, Any]
    status: str
    source_count: int = Field(default=0, ge=0)
    record_count: int = Field(default=0, ge=0)
    message: str
    started_at: datetime
    completed_at: datetime


class DatasetColumn(ApiModel):
    name: str
    label_zh: str
    data_type: str
    role: str
    source_field: str | None = None
    description: str


class ModelingDataset(ApiModel):
    name: str
    unit_of_analysis: str
    columns: list[DatasetColumn]
    rows: list[dict[str, Any]]
    row_count: int = Field(ge=0)
    patient_count: int = Field(ge=0)
    sample_count: int = Field(ge=0)
    target_column: str | None = None
    class_distribution: dict[str, int] = Field(default_factory=dict)
    dataset_role: str = "primary"
    study_key: str | None = None


class AnalysisReadinessReport(ApiModel):
    status: str
    analysis_ready: bool
    row_count: int = Field(ge=0)
    feature_count: int = Field(ge=0)
    target_column: str | None = None
    target_missing_rate: float | None = Field(default=None, ge=0, le=1)
    field_completeness_rate: float | None = Field(default=None, ge=0, le=1)
    target_match: bool = False
    target_match_rate: float | None = Field(default=None, ge=0, le=1)
    requested_variable_coverage_rate: float | None = Field(default=None, ge=0, le=1)
    repeated_patient_count: int = Field(default=0, ge=0)
    duplicate_row_count: int = Field(default=0, ge=0)
    cleaned_value_count: int = Field(default=0, ge=0)
    excluded_orphan_record_count: int = Field(default=0, ge=0)
    cleaning_actions: list[str] = Field(default_factory=list)
    split_strategy: str
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class StudyVariable(ApiModel):
    variable_id: str
    label: str
    role: str
    required: bool = False
    available: bool = False
    priority: str = "secondary"
    coverage_rate: float | None = Field(default=None, ge=0, le=1)
    matched_fields: list[str] = Field(default_factory=list)
    companion_sources: list[str] = Field(default_factory=list)
    note: str


class DataSourceRecommendation(ApiModel):
    database: str
    purpose: str
    data_domains: list[str] = Field(default_factory=list)
    availability: str
    selected: bool = False
    source_ids: list[str] = Field(default_factory=list)
    note: str


class StudyDesignReport(ApiModel):
    status: str
    generation_note: str = ""
    research_type: str
    research_type_id: str
    population: str
    exposure: str
    outcome: str
    covariates: list[str] = Field(default_factory=list)
    analysis_unit: str
    model_expression: str
    cohort_rules: list[str] = Field(default_factory=list)
    required_variables: list[StudyVariable] = Field(default_factory=list)
    variable_coverage_rate: float | None = Field(default=None, ge=0, le=1)
    data_source_recommendations: list[DataSourceRecommendation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class CohortFilterStep(ApiModel):
    step_id: str
    label: str
    rule_type: str
    criterion: str
    before_count: int = Field(ge=0)
    after_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    status: str
    note: str


class CohortConstructionReport(ApiModel):
    status: str
    execution_mode: str = "live"
    rule_status: str = "待执行"
    has_observed_rows: bool = False
    not_run_reason: str | None = None
    source_row_count: int = Field(ge=0)
    final_row_count: int = Field(ge=0)
    patient_count: int = Field(ge=0)
    sample_count: int = Field(ge=0)
    inclusion_criteria: list[str] = Field(default_factory=list)
    exclusion_criteria: list[str] = Field(default_factory=list)
    filter_steps: list[CohortFilterStep] = Field(default_factory=list)
    variable_coverage_rate: float | None = Field(default=None, ge=0, le=1)
    patient_linkage_f1: float | None = Field(default=None, ge=0, le=1)
    response_domains: list[str] = Field(default_factory=list)
    quality_gate: str
    publish_allowed: bool = False
    notes: list[str] = Field(default_factory=list)


class CollectionFieldEvidence(ApiModel):
    source_name: str
    source_id: str | None = None
    status: str
    matched_fields: list[str] = Field(default_factory=list)
    note: str


class CollectionGap(ApiModel):
    variable_id: str
    label: str
    role: str
    required: bool
    coverage_rate: float | None = Field(default=None, ge=0, le=1)
    matched_fields: list[str] = Field(default_factory=list)
    reason: str
    suggested_sources: list[str] = Field(default_factory=list)
    field_evidence: list[CollectionFieldEvidence] = Field(default_factory=list)


class CollectionSearchAction(ApiModel):
    action_id: str
    tool_name: str
    source_name: str
    priority: int = Field(ge=1, le=20)
    rationale: str
    status: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    strategy_id: str | None = None
    strategy_label: str | None = None


class AgentGoalStatus(ApiModel):
    goal_id: str
    label: str
    required: bool = True
    met: bool = False
    evidence: str = ""


class CollectionIteration(ApiModel):
    round_number: int = Field(ge=1)
    phase: str
    status: str
    quality_gate: str
    source_names: list[str] = Field(default_factory=list)
    source_count: int = Field(ge=0)
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    available_fields: list[str] = Field(default_factory=list)
    missing_critical_fields: list[str] = Field(default_factory=list)
    missing_recommended_fields: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    field_evidence: list[CollectionFieldEvidence] = Field(default_factory=list)
    note: str
    diagnosis: str | None = None
    diagnosis_label: str | None = None
    decision: str | None = None
    strategy_ids: list[str] = Field(default_factory=list)
    goals_met: list[str] = Field(default_factory=list)
    goals_open: list[str] = Field(default_factory=list)


class CollectionAgentReport(ApiModel):
    enabled: bool = True
    status: str
    quality_gate: str
    max_rounds: int = Field(ge=1)
    completed_rounds: int = Field(ge=0)
    iterations: list[CollectionIteration] = Field(default_factory=list)
    critical_gaps: list[CollectionGap] = Field(default_factory=list)
    recommended_gaps: list[CollectionGap] = Field(default_factory=list)
    next_actions: list[CollectionSearchAction] = Field(default_factory=list)
    source_coverage: dict[str, str] = Field(default_factory=dict)
    note: str
    stop_reason: str = ""
    diagnosis: str | None = None
    goals: list[AgentGoalStatus] = Field(default_factory=list)
    strategies_tried: list[str] = Field(default_factory=list)


class DataAlignmentSource(ApiModel):
    source_id: str
    source_name: str
    source_type: str
    accession: str | None = None
    url: str | None = None
    role: str
    row_count: int = Field(ge=0)
    patient_count: int = Field(ge=0)
    sample_count: int = Field(ge=0)
    study_ids: list[str] = Field(default_factory=list)
    note: str


class DataAlignmentReport(ApiModel):
    status: str
    scope: str
    identity_namespace: str
    alignment_basis: list[str] = Field(default_factory=list)
    row_count: int = Field(ge=0)
    patient_count: int = Field(ge=0)
    sample_count: int = Field(ge=0)
    study_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    patient_id_coverage_rate: float | None = Field(default=None, ge=0, le=1)
    sample_id_coverage_rate: float | None = Field(default=None, ge=0, le=1)
    same_study: bool | None = None
    same_source: bool | None = None
    unresolved_identity_row_count: int = Field(ge=0)
    duplicate_identity_count: int = Field(ge=0)
    cross_source_join_performed: bool = False
    cross_source_join_status: str
    primary_source_names: list[str] = Field(default_factory=list)
    sources: list[DataAlignmentSource] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    note: str
    entity_match_status: str = "REVIEW"
    entity_match_note: str = ""


class ParsedResearchQuestion(ApiModel):
    disease: str
    population: str
    exposure: str
    outcome: str
    required_variables: list[str] = Field(default_factory=list)
    research_type: str | None = None


class QualityGateLayer(ApiModel):
    gate_id: str
    label: str
    decision: str
    checks: list[str] = Field(default_factory=list)
    evidence: str


class QualityGateReport(ApiModel):
    overall: str
    publish_allowed: bool = False
    layers: list[QualityGateLayer] = Field(default_factory=list)
    cohort_f1: float | None = Field(default=None, ge=0, le=1)
    cohort_plan_f1: float | None = Field(default=None, ge=0, le=1)
    variable_coverage: float | None = Field(default=None, ge=0, le=1)
    traceability: float | None = Field(default=None, ge=0, le=1)
    research_fitness: float | None = Field(default=None, ge=0, le=1)
    note: str


class ResearchTaskStatus(ApiModel):
    task_id: str
    status: str
    stage: str
    progress: int = Field(ge=0, le=100)
    message: str
    error: str | None = None
    created_at: datetime


class ResearchTaskCreated(ApiModel):
    task_id: str
    status: str = "running"


class ResearchTaskSpec(ApiModel):
    task_id: str
    question_parse: ParsedResearchQuestion | None = None
    study_design: StudyDesignReport | None = None


class PrioritizedField(ApiModel):
    field_id: str
    label: str
    priority: str
    reason: str
    aliases: list[str] = Field(default_factory=list)


class NamedCohort(ApiModel):
    name: str
    study_id: str = ""
    project_id: str = ""
    tool_name: str
    role: str = "named_primary"


class ResearchBrief(ApiModel):
    research_type_id: str
    research_type: str
    primary_question: str
    named_cohorts: list[NamedCohort] = Field(default_factory=list)
    fields: list[PrioritizedField] = Field(default_factory=list)
    search_strategy: str = ""
    analysis_plan: str = ""
    needs_clinical_outcome: bool = False
    keywords: list[str] = Field(default_factory=list)


class DataValueAssessment(ApiModel):
    status: str
    judgment: str
    primary_coverage: float | None = Field(default=None, ge=0, le=1)
    named_cohorts_hit: list[str] = Field(default_factory=list)
    named_cohorts_missing: list[str] = Field(default_factory=list)
    missing_primary_fields: list[str] = Field(default_factory=list)
    next_step: str = ""


class AgentTaskResult(ApiModel):
    task_id: str
    status: str
    agent_mode: str
    model_provider: str
    model_name: str
    # Production uses Qwen. This neutral marker exists so the isolated
    # planner-replacement ablation can record its actual experimental model.
    used_model: bool = False
    used_qwen: bool
    notice: str
    research_spec: ResearchSpec
    parsed_question: ParsedResearchQuestion | None = None
    research_brief: ResearchBrief | None = None
    value_assessment: DataValueAssessment | None = None
    plan: list[AgentPlanStep]
    tool_calls: list[AgentToolCall]
    candidate_sources: list[CandidateSource]
    source_items: list[SourceItem]
    modeling_dataset: ModelingDataset
    source_datasets: list[ModelingDataset] = Field(default_factory=list)
    readiness: AnalysisReadinessReport
    study_design: StudyDesignReport | None = None
    cohort_construction: CohortConstructionReport | None = None
    collection_agent: CollectionAgentReport | None = None
    data_alignment: DataAlignmentReport | None = None
    quality_gate_report: QualityGateReport | None = None
    competition_report: "CompetitionAlignmentReport | None" = None
    critic_report: Any | None = None
    summary_zh: str
    created_at: datetime


class CompetitionMetric(ApiModel):
    name: str
    value: float | None = Field(default=None, ge=0, le=1)
    display_value: str
    target: str | None = None
    status: str
    detail: str


class CompetitionAblationRow(ApiModel):
    variant: str
    removed_component: str
    expected_effect: str
    observed_effect: str
    note: str
    diagnostic_score: float | None = None
    delta_from_full: float | None = None


class CompetitionVariantScore(ApiModel):
    variant_id: str
    label: str
    diagnostic_score: float | None = None
    status: str
    note: str
    is_primary: bool = False


class CompetitionRagLayer(ApiModel):
    layer: str
    implementation: str
    why_it_matters: str
    observable_effect: str


class CompetitionVisualNode(ApiModel):
    node_id: str
    label: str
    node_type: str
    group: str
    weight: int = Field(default=1, ge=0)
    status: str | None = None
    detail: str | None = None


class CompetitionVisualEdge(ApiModel):
    source: str
    target: str
    label: str
    relation_type: str
    strength: float = Field(default=1.0, ge=0, le=1)
    detail: str | None = None


class CompetitionRagFlowNode(ApiModel):
    node_id: str
    label: str
    layer: str
    order: int = Field(ge=1)
    status: str
    detail: str


class CompetitionRagFlowEdge(ApiModel):
    source: str
    target: str
    label: str
    detail: str | None = None


class CompetitionRagMatch(ApiModel):
    match_id: str
    database: str
    dataset_id: str
    dataset_name: str
    data_type: str
    accession: str | None = None
    sample_count: int | None = Field(default=None, ge=0)
    match_score: float = Field(ge=0, le=1)
    display_score: str
    status: str
    selected: bool = False
    signals: dict[str, float] = Field(default_factory=dict)
    matched_facets: list[str] = Field(default_factory=list)
    rationale: str


class ScientificUsabilityFinding(ApiModel):
    variable: str
    outcome: str
    method: str
    n: int = Field(ge=0)
    display_score: str
    score: float | None = Field(default=None, ge=0, le=1)
    status: str
    interpretation: str
    group_counts: dict[str, int] = Field(default_factory=dict)


class ScientificUsabilityAnalysis(ApiModel):
    title: str
    status: str
    sample_size: int = Field(ge=0)
    target_column: str | None = None
    feature_count: int = Field(ge=0)
    methods: list[str] = Field(default_factory=list)
    findings: list[ScientificUsabilityFinding] = Field(default_factory=list)
    interpretation: str
    caveats: list[str] = Field(default_factory=list)


class UnifiedEvaluationLayer(ApiModel):
    layer_id: str
    label: str
    purpose: str
    status: str
    primary_outputs: list[str] = Field(default_factory=list)
    evidence_requirement: str


class TaskAdaptiveFitnessReport(ApiModel):
    evaluation_contract_id: str
    frozen_before_run: bool
    status: str
    fitness_score: float | None = Field(default=None, ge=0, le=100)
    dimensions: list[CompetitionMetric] = Field(default_factory=list)
    quality_gate: str
    publish_allowed: bool = False
    gap_feedback: list[str] = Field(default_factory=list)
    note: str


class ModelComparisonRow(ApiModel):
    method_id: str
    method_label: str
    base_model_id: str | None = None
    status: str
    sdti_status: str
    fitness_score: float | None = Field(default=None, ge=0, le=100)
    quality_gate: str
    publish_allowed: bool = False
    observed_metrics: dict[str, float | str | None] = Field(default_factory=dict)
    note: str


class HorizontalComparisonTable(ApiModel):
    table_id: str
    title: str
    status: str
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    note: str


class StratifiedEvaluationRow(ApiModel):
    stratum_name: str
    stratum_label_zh: str | None = None
    stratum_value: str
    stratum_value_label_zh: str | None = None
    n: int = Field(ge=0)
    metrics: dict[str, float | str | None] = Field(default_factory=dict)
    quality_gate: str
    publish_allowed: bool = False
    note: str


class UnifiedEvaluationReport(ApiModel):
    version: str
    status: str
    no_fake_scores_notice: str
    layers: list[UnifiedEvaluationLayer] = Field(default_factory=list)
    task_adaptive_fitness: TaskAdaptiveFitnessReport
    model_comparison: list[ModelComparisonRow] = Field(default_factory=list)
    horizontal_comparisons: list[HorizontalComparisonTable] = Field(default_factory=list)
    stratified_comparisons: list[StratifiedEvaluationRow] = Field(default_factory=list)
    required_next_runs: list[str] = Field(default_factory=list)

class CompetitionGraphSummary(ApiModel):
    enabled: bool
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    relation_types: list[str] = Field(default_factory=list)
    entity_types: list[str] = Field(default_factory=list)
    note: str


class CompetitionChecklistItem(ApiModel):
    label: str
    status: str
    detail: str


class CompetitionAlignmentReport(ApiModel):
    competition_name: str
    track: str
    direction: str
    problem_focus: str
    unified_evaluation: UnifiedEvaluationReport | None = None
    metrics: list[CompetitionMetric] = Field(default_factory=list)
    ablation_rows: list[CompetitionAblationRow] = Field(default_factory=list)
    variant_scores: list[CompetitionVariantScore] = Field(default_factory=list)
    rag_layers: list[CompetitionRagLayer] = Field(default_factory=list)
    knowledge_graph: CompetitionGraphSummary
    rag_flow_nodes: list[CompetitionRagFlowNode] = Field(default_factory=list)
    rag_flow_edges: list[CompetitionRagFlowEdge] = Field(default_factory=list)
    rag_matches: list[CompetitionRagMatch] = Field(default_factory=list)
    graph_nodes: list[CompetitionVisualNode] = Field(default_factory=list)
    graph_edges: list[CompetitionVisualEdge] = Field(default_factory=list)
    scientific_usability: ScientificUsabilityAnalysis | None = None
    improvement_highlights: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    submission_checklist: list[CompetitionChecklistItem] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    summary: str


AgentTaskResult.model_rebuild()
