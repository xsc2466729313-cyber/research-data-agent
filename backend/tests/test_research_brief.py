from datetime import datetime, timezone

from backend.app.agent.accession_harvest import needs_clinical_outcome
from backend.app.agent.competition_report import CompetitionReportBuilder
from backend.app.agent.dataset_builder import ResearchDatasetBuilder
from backend.app.agent.models import AgentTaskRequest, AgentTaskResult
from backend.app.agent.research_brief import ResearchBriefBuilder
from backend.app.agent.service import ResearchAgentService
from backend.app.agent.study_design import StudyDesignBuilder
from backend.app.models import ResearchSpec


QUESTION = (
    "PIK3CA 热点突变谱在 METABRIC 与 TCGA-BRCA 中是否具有可重复性？"
    "其与 ER、HER2 和分子亚型的关系是否一致？"
)
SURVIVAL_QUESTION = "PIK3CA 突变与乳腺癌 OS/RFS 的关系是否受到 ER 状态或 IntClust 分型的调节？"


def _spec(question: str = QUESTION) -> ResearchSpec:
    service = ResearchAgentService()
    return service._enrich_research_spec(service._deterministic_spec(question, "task-pik3ca-repro"), question)


def test_reproducibility_question_does_not_become_treatment_response() -> None:
    spec = _spec()
    brief = ResearchBriefBuilder().build(QUESTION, spec)

    assert "treatment_response" not in spec.outcomes
    assert needs_clinical_outcome(spec) is False
    assert spec.genes == ["PIK3CA"]
    assert spec.subtype is None
    assert brief.research_type_id == "cross_cohort_reproducibility"
    assert brief.needs_clinical_outcome is False
    primary = {field.field_id: field for field in brief.fields if field.priority == "primary"}
    assert "pik3ca_mutation" in primary
    assert "pik3ca_variants" in primary
    assert "er_status" in primary
    assert "her2_status" in primary
    assert "subtype" in primary
    named = {cohort.name for cohort in brief.named_cohorts if cohort.role == "named_primary"}
    assert named == {"METABRIC", "TCGA-BRCA"}


def test_named_cohorts_are_searched_before_geo_response_sets() -> None:
    spec = _spec()
    brief = ResearchBriefBuilder().build(QUESTION, spec)
    request = AgentTaskRequest(
        question=QUESTION,
        use_qwen=False,
        data_mode="plan_only",
        max_sources=6,
        max_records=200,
    )
    calls = ResearchAgentService()._deterministic_tool_calls(spec, request, brief)
    cbio = [call for call in calls if call["name"] == "search_cbioportal"]
    study_ids = [call["arguments"]["study_id"] for call in cbio]

    assert calls[0]["name"] == "search_cbioportal"
    assert "brca_metabric" in study_ids
    assert "brca_tcga_pan_can_atlas_2018" in study_ids
    assert "search_geo" not in {call["name"] for call in calls}
    assert "breast_alpelisib_2020" not in study_ids


def test_study_design_marks_question_nouns_as_primary() -> None:
    spec = _spec()
    brief = ResearchBriefBuilder().build(QUESTION, spec)
    rows = [
        {
            "study_id": "brca_metabric",
            "patient_id": "P1",
            "sample_id": "S1",
            "disease": "乳腺癌",
            "pik3ca_mutation": 1,
            "pik3ca_variants": "H1047R",
            "er_status": "阳性",
            "her2_status": "阴性",
            "subtype": "Luminal A",
            "sample_type": "原发肿瘤",
        }
    ]
    dataset = ResearchDatasetBuilder()._dataset_from_rows(rows, name="METABRIC", unit="患者", spec=spec)
    design, _cohort = StudyDesignBuilder().build(
        spec,
        dataset,
        ResearchDatasetBuilder()._readiness(dataset, spec),
        [],
        [],
        brief=brief,
    )
    by_id = {variable.variable_id: variable for variable in design.required_variables}

    assert design.research_type_id == "cross_cohort_reproducibility"
    assert "treatment_response" not in design.outcome
    assert by_id["pik3ca_mutation"].priority == "primary"
    assert by_id["er_status"].priority == "primary"
    assert by_id["her2_status"].priority == "primary"
    assert by_id["subtype"].priority == "primary"
    assert by_id["pik3ca_mutation"].required is True
    assert "outcome" not in by_id or by_id["outcome"].required is False


def test_survival_moderation_question_covers_question_nouns() -> None:
    spec = _spec(SURVIVAL_QUESTION)
    brief = ResearchBriefBuilder().build(SURVIVAL_QUESTION, spec)
    primary = {field.field_id: field for field in brief.fields if field.priority == "primary"}
    request = AgentTaskRequest(
        question=SURVIVAL_QUESTION,
        use_qwen=False,
        data_mode="plan_only",
        max_sources=6,
        max_records=200,
    )
    calls = ResearchAgentService()._deterministic_tool_calls(spec, request, brief)
    study_ids = [
        call["arguments"]["study_id"]
        for call in calls
        if call["name"] == "search_cbioportal"
    ]

    assert spec.genes == ["PIK3CA"]
    assert "survival" in spec.outcomes
    assert "treatment_response" not in spec.outcomes
    assert needs_clinical_outcome(spec) is True
    assert brief.research_type_id == "survival_analysis"
    assert "pik3ca_mutation" in primary
    assert "os_status" in primary
    assert "dfs_status" in primary
    assert "er_status" in primary
    assert "intclust" in primary
    assert any(cohort.study_id == "brca_metabric" for cohort in brief.named_cohorts)
    assert calls[0]["name"] == "search_cbioportal"
    assert study_ids[0] == "brca_metabric"
    assert "breast_alpelisib_2020" not in study_ids
    assert "search_geo" not in {call["name"] for call in calls}
    assert "IntClust" in brief.analysis_plan or "调节" in brief.analysis_plan
    catalog = next(call for call in calls if call["name"] == "search_geo_catalog")
    query = catalog["arguments"]["query"].casefold()
    assert "pik3ca" in query
    assert any(token in query for token in ("intclust", "rfs", "os", "overall survival"))
    assert "pcr" not in query
    assert brief.keywords
    assert any("IntClust" in item or "intclust" in item.casefold() for item in brief.keywords)


def test_keyword_driven_search_is_not_tied_to_one_example_question() -> None:
    question = "GATA3 突变与 PAM50 亚型在乳腺癌中的分布是否一致？"
    spec = _spec(question)
    brief = ResearchBriefBuilder().build(question, spec)
    request = AgentTaskRequest(
        question=question,
        use_qwen=False,
        data_mode="plan_only",
        max_sources=6,
        max_records=200,
    )
    calls = ResearchAgentService()._deterministic_tool_calls(spec, request, brief)
    catalog = next(call for call in calls if call["name"] == "search_geo_catalog")
    query = catalog["arguments"]["query"]

    assert spec.genes == ["GATA3"]
    assert "treatment_response" not in spec.outcomes
    assert "GATA3" in query
    assert "PAM50" in query
    assert "pCR" not in query
    assert "pcr" not in query.casefold()
    assert calls[0]["name"] == "search_cbioportal"
    assert "search_geo" not in {call["name"] for call in calls}


def test_value_assessment_does_not_fail_for_missing_pcr() -> None:
    spec = _spec()
    brief = ResearchBriefBuilder().build(QUESTION, spec)
    rows = [
        {
            "study_id": "brca_metabric",
            "patient_id": f"P{index}",
            "sample_id": f"S{index}",
            "disease": "乳腺癌",
            "pik3ca_mutation": index % 2,
            "pik3ca_variants": "E545K" if index % 2 else "WT",
            "er_status": "阳性" if index % 3 else "阴性",
            "her2_status": "阴性",
            "subtype": "Luminal A" if index % 2 else "Basal",
            "sample_type": "原发肿瘤",
        }
        for index in range(40)
    ]
    companion_rows = [
        {
            "study_id": "brca_tcga_pan_can_atlas_2018",
            "patient_id": f"TCGA-{index}",
            "sample_id": f"TS{index}",
            "disease": "乳腺癌",
            "pik3ca_mutation": 1,
            "er_status": "阳性",
            "her2_status": "阴性",
            "subtype": "Luminal B",
            "sample_type": "原发肿瘤",
        }
        for index in range(12)
    ]
    builder = ResearchDatasetBuilder()
    dataset = builder._dataset_from_rows(rows, name="METABRIC", unit="患者", spec=spec).model_copy(
        update={"study_key": "brca_metabric"}
    )
    companion = builder._dataset_from_rows(companion_rows, name="TCGA-BRCA", unit="患者", spec=spec).model_copy(
        update={"study_key": "brca_tcga_pan_can_atlas_2018"}
    )
    assessment = ResearchBriefBuilder().assess(brief, dataset, [companion])
    readiness = builder._readiness(dataset, spec)
    result = AgentTaskResult(
        task_id="value-test",
        status="完成",
        agent_mode="确定性科研规划",
        model_provider="test",
        model_name="test",
        used_qwen=False,
        notice="",
        research_spec=spec,
        research_brief=brief,
        value_assessment=assessment,
        plan=[],
        tool_calls=[],
        candidate_sources=[],
        source_items=[],
        modeling_dataset=dataset,
        source_datasets=[companion],
        readiness=readiness,
        summary_zh="",
        created_at=datetime.now(timezone.utc),
    )
    analysis = CompetitionReportBuilder._scientific_usability(result)

    assert assessment.status in {"有科研价值", "部分可用"}
    assert "pCR" not in assessment.judgment
    assert "信息不足" not in (analysis.status if analysis else "")
    assert analysis is not None
    assert analysis.target_column in {"pik3ca_mutation", "pik3ca_variants"}
    assert {finding.variable for finding in analysis.findings} & {"er_status", "her2_status", "subtype"}
