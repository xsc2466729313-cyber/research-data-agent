from backend.app.agent.accession_harvest import catalog_query, literature_query
from backend.app.agent.goal_loop import GoalLoopController
from backend.app.agent.models import AnalysisReadinessReport, CollectionGap, ModelingDataset
from backend.app.agent.search_planner import question_search_terms
from backend.app.models import ResearchSpec


QUESTION_SPEC = ResearchSpec(
    task_id="goal-loop-test",
    research_goal="研究 HER2 阳性乳腺癌中 PIK3CA 突变是否影响治疗响应",
    disease="Breast Cancer",
    subtype="HER2-positive",
    genes=["PIK3CA"],
    outcomes=["treatment_response"],
    required_data_types=["clinical", "mutation", "treatment_response"],
)


def _dataset(name: str, rows: int, target: str | None = None) -> ModelingDataset:
    empty = ModelingDataset(
        name=name,
        unit_of_analysis="患者",
        columns=[],
        rows=[{} for _ in range(rows)],
        row_count=rows,
        patient_count=rows,
        sample_count=rows,
        target_column=target,
    )
    return empty


def test_outcome_mismatch_switches_to_geo_response_cohort() -> None:
    loop = GoalLoopController()
    readiness = AnalysisReadinessReport(
        status="研究结局不匹配",
        analysis_ready=False,
        row_count=848,
        feature_count=10,
        split_strategy="按患者编号分组",
        target_match=False,
        requested_variable_coverage_rate=0.7,
    )
    decision = loop.decide(
        spec=QUESTION_SPEC,
        dataset=_dataset("METABRIC", 848),
        readiness=readiness,
        gaps=[
            CollectionGap(
                variable_id="outcome",
                label="研究结局",
                role="结局",
                required=True,
                coverage_rate=0.0,
                reason="METABRIC 无治疗响应",
            )
        ],
        attempted_calls={'search_cbioportal:{"gene_symbols": ["PIK3CA"], "max_records": 100, "study_id": "brca_metabric"}'},
        max_records=100,
        round_number=1,
        max_rounds=5,
    )

    assert decision.action == "continue"
    assert decision.diagnosis == "outcome_mismatch"
    assert decision.actions
    assert decision.actions[0].arguments["study_id"] == "breast_alpelisib_2020"


def test_pcr_only_spec_still_diagnoses_outcome_mismatch_and_switches_geo() -> None:
    loop = GoalLoopController()
    spec = ResearchSpec(
        task_id="tnbc-pcr",
        research_goal="研究三阴性乳腺癌中 BRCA1/BRCA2 突变与新辅助化疗病理完全缓解（pCR）的关系",
        disease="Breast Cancer",
        subtype="Triple-negative",
        genes=["BRCA1", "BRCA2"],
        outcomes=["pCR"],
        required_data_types=["clinical", "mutation"],
    )
    readiness = AnalysisReadinessReport(
        status="研究结局不匹配",
        analysis_ready=False,
        row_count=848,
        feature_count=10,
        split_strategy="按患者编号分组",
        target_match=False,
        requested_variable_coverage_rate=1.0,
    )
    decision = loop.decide(
        spec=spec,
        dataset=_dataset("TCGA-BRCA", 848),
        readiness=readiness,
        gaps=[
            CollectionGap(
                variable_id="outcome",
                label="研究结局",
                role="结局",
                required=True,
                coverage_rate=0.0,
                reason="当前主表无 pCR",
            )
        ],
        attempted_calls={'search_cbioportal:{"gene_symbols": ["BRCA1", "BRCA2"], "max_records": 200, "study_id": "brca_tcga_pan_can_atlas_2018"}'},
        max_records=200,
        round_number=1,
        max_rounds=5,
    )

    assert decision.diagnosis == "outcome_mismatch"
    assert decision.action == "continue"
    assert decision.actions[0].tool_name == "search_geo"
    assert decision.actions[0].arguments["accession"] == "GSE25066"


def test_stops_partial_when_response_cohort_cannot_legally_gain_mutation() -> None:
    loop = GoalLoopController()
    readiness = AnalysisReadinessReport(
        status="可支持治疗响应分析，分子暴露待同队列补充",
        analysis_ready=True,
        row_count=50,
        feature_count=8,
        split_strategy="按患者编号分组",
        target_match=True,
        requested_variable_coverage_rate=0.0,
    )
    terms = question_search_terms(QUESTION_SPEC.research_goal, QUESTION_SPEC)
    attempted = {
        loop.call_key({"name": "search_cbioportal", "arguments": {"study_id": "breast_alpelisib_2020", "gene_symbols": ["PIK3CA"], "max_records": 100}}),
        loop.call_key({"name": "search_cbioportal", "arguments": {"study_id": "brca_mskcc_2019", "gene_symbols": ["PIK3CA"], "max_records": 100}}),
        loop.call_key({"name": "search_cbioportal", "arguments": {"study_id": "brca_metabric", "gene_symbols": ["PIK3CA"], "max_records": 100}}),
        loop.call_key({"name": "search_geo", "arguments": {"accession": "GSE76360", "max_files": 5}}),
        loop.call_key({"name": "search_geo_catalog", "arguments": {"query": catalog_query(QUESTION_SPEC, extra_terms=terms), "max_records": 20}}),
        loop.call_key({"name": "search_europe_pmc", "arguments": {"query": literature_query(QUESTION_SPEC, extra_terms=terms), "max_records": 20}}),
    }
    decision = loop.decide(
        spec=QUESTION_SPEC,
        dataset=_dataset("GSE76360", 50, "treatment_response"),
        readiness=readiness,
        gaps=[
            CollectionGap(
                variable_id="pik3ca_mutation",
                label="PIK3CA 突变",
                role="暴露",
                required=True,
                coverage_rate=0.0,
                reason="GEO 队列无 PIK3CA",
            )
        ],
        attempted_calls=attempted,
        max_records=100,
        round_number=2,
        max_rounds=5,
        cohort=type("Cohort", (), {"final_row_count": 48})(),
    )

    assert decision.action == "stop_partial"
    assert decision.quality_gate == "PARTIAL"
    assert not decision.actions
    assert any(goal.goal_id == "matched_outcome" and goal.met for goal in decision.goals)
    assert any(goal.goal_id == "same_cohort_exposure" and not goal.met for goal in decision.goals)


def test_missing_mutation_switches_to_same_patient_response_mutation_cohort() -> None:
    loop = GoalLoopController()
    readiness = AnalysisReadinessReport(
        status="可支持治疗响应分析，分子暴露待同队列补充",
        analysis_ready=True,
        row_count=50,
        feature_count=8,
        split_strategy="按患者编号分组",
        target_match=True,
        requested_variable_coverage_rate=0.0,
    )
    decision = loop.decide(
        spec=QUESTION_SPEC,
        dataset=_dataset("GSE76360", 50, "treatment_response"),
        readiness=readiness,
        gaps=[
            CollectionGap(
                variable_id="pik3ca_mutation",
                label="PIK3CA 突变",
                role="暴露",
                required=True,
                coverage_rate=0.0,
                reason="GEO 队列无 PIK3CA",
            )
        ],
        attempted_calls={
            loop.call_key({"name": "search_geo", "arguments": {"accession": "GSE76360", "max_files": 5}}),
        },
        max_records=100,
        round_number=2,
        max_rounds=8,
        cohort=type("Cohort", (), {"final_row_count": 48})(),
    )

    assert decision.action == "continue"
    assert decision.diagnosis == "missing_same_cohort_exposure"
    assert decision.actions
    assert decision.actions[0].arguments["study_id"] == "breast_alpelisib_2020"


def test_complete_dual_pack_fetches_independent_clinical_table() -> None:
    loop = GoalLoopController()
    readiness = AnalysisReadinessReport(
        status="可支持治疗响应分析",
        analysis_ready=True,
        row_count=51,
        feature_count=12,
        split_strategy="按患者编号分组",
        target_match=True,
        requested_variable_coverage_rate=1.0,
    )
    decision = loop.decide(
        spec=QUESTION_SPEC,
        dataset=_dataset("Alpelisib", 51, "treatment_response"),
        readiness=readiness,
        gaps=[
            CollectionGap(
                variable_id="age",
                label="年龄",
                role="协变量",
                required=False,
                coverage_rate=0.0,
                reason="主表未发布年龄",
            )
        ],
        attempted_calls={
            loop.call_key(
                {
                    "name": "search_cbioportal",
                    "arguments": {"study_id": "breast_alpelisib_2020", "gene_symbols": ["PIK3CA"], "max_records": 100},
                }
            )
        },
        max_records=100,
        round_number=2,
        max_rounds=8,
        cohort=type("Cohort", (), {"final_row_count": 51})(),
    )

    assert decision.action == "continue"
    assert decision.diagnosis == "missing_clinical_covariates"
    assert decision.actions
    assert decision.actions[0].arguments["study_id"] == "brca_metabric"


def test_independent_clinical_table_stops_without_joining() -> None:
    loop = GoalLoopController()
    companion = ModelingDataset(
        name="METABRIC 临床与分子队列",
        unit_of_analysis="样本",
        columns=[],
        rows=[{"age": 58, "stage": "II", "er_status": "阳性", "pr_status": "阳性"}],
        row_count=1,
        patient_count=1,
        sample_count=1,
        dataset_role="companion",
        study_key="brca_metabric",
    )
    readiness = AnalysisReadinessReport(
        status="可支持治疗响应分析",
        analysis_ready=True,
        row_count=51,
        feature_count=12,
        split_strategy="按患者编号分组",
        target_match=True,
        requested_variable_coverage_rate=1.0,
    )
    decision = loop.decide(
        spec=QUESTION_SPEC,
        dataset=_dataset("Alpelisib", 51, "treatment_response"),
        readiness=readiness,
        gaps=[],
        attempted_calls=set(),
        max_records=100,
        round_number=3,
        max_rounds=8,
        cohort=type("Cohort", (), {"final_row_count": 51})(),
        source_datasets=[companion],
    )

    assert decision.action == "stop_pass"
    assert any(goal.goal_id == "covariate_pack" and goal.met for goal in decision.goals)
