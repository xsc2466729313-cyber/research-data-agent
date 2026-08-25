from backend.app.agent.dataset_builder import ResearchDatasetBuilder
from backend.app.agent.study_design import StudyDesignBuilder
from backend.app.models import ResearchSpec


def test_study_design_and_cohort_report_use_observed_rows() -> None:
    dataset = ResearchDatasetBuilder().empty()[0]
    dataset = dataset.model_copy(
        update={
            "unit_of_analysis": "患者一行",
            "columns": [
                {"name": "patient_id", "label_zh": "患者编号", "data_type": "string", "role": "分析单位", "description": "患者"},
                {"name": "disease", "label_zh": "疾病", "data_type": "string", "role": "研究变量", "description": "疾病"},
                {"name": "subtype", "label_zh": "亚型", "data_type": "string", "role": "研究变量", "description": "亚型"},
                {"name": "pik3ca_mutation", "label_zh": "PIK3CA", "data_type": "number", "role": "研究变量", "description": "突变"},
                {"name": "treatment_response", "label_zh": "治疗响应", "data_type": "string", "role": "研究结局", "description": "结局"},
            ],
            "rows": [
                {"patient_id": "P1", "disease": "Breast Cancer", "subtype": "HER2-positive", "pik3ca_mutation": 1, "treatment_response": "pCR"},
                {"patient_id": "P2", "disease": "Breast Cancer", "subtype": "HER2-positive", "pik3ca_mutation": 0, "treatment_response": None},
            ],
            "row_count": 2,
            "patient_count": 2,
            "sample_count": 2,
            "target_column": "treatment_response",
        }
    )
    readiness = ResearchDatasetBuilder().empty()[1].model_copy(
        update={
            "row_count": 2,
            "target_column": "treatment_response",
            "target_match": True,
            "target_missing_rate": 0.5,
            "analysis_ready": False,
        }
    )
    spec = ResearchSpec(
        task_id="study-test",
        research_goal="研究 HER2 阳性乳腺癌中 PIK3CA 突变与治疗响应",
        disease="Breast Cancer",
        subtype="HER2-positive",
        genes=["PIK3CA"],
        outcomes=["treatment_response"],
        required_data_types=["clinical", "mutation", "treatment_response"],
    )

    design, cohort = StudyDesignBuilder().build(spec, dataset, readiness, [], [])

    assert design.research_type_id == "response_analysis"
    assert design.model_expression.startswith("Y = f(")
    assert design.variable_coverage_rate is not None
    assert any(variable.variable_id == "pik3ca_mutation" and variable.available for variable in design.required_variables)
    outcome_step = next(step for step in cohort.filter_steps if step.step_id == "include_outcome")
    assert outcome_step.before_count == 2
    assert outcome_step.after_count == 1
    assert outcome_step.excluded_count == 1
    assert cohort.patient_linkage_f1 is None
    gtex = next(item for item in design.data_source_recommendations if item.database == "GTEx")
    oncokb = next(item for item in design.data_source_recommendations if item.database == "OncoKB")
    assert gtex.availability == "待接入"
    assert oncokb.availability == "待接入"
    assert gtex.selected is False
    assert oncokb.selected is False


def test_cohort_keeps_rows_when_required_variable_is_matched_alias() -> None:
    dataset = ResearchDatasetBuilder().empty()[0]
    dataset = dataset.model_copy(
        update={
            "unit_of_analysis": "患者一行",
            "columns": [
                {"name": "patient_id", "label_zh": "患者编号", "data_type": "string", "role": "分析单位", "description": "患者"},
                {"name": "disease", "label_zh": "疾病", "data_type": "string", "role": "研究变量", "description": "疾病"},
                {"name": "pik3ca_mutation", "label_zh": "PIK3CA", "data_type": "number", "role": "研究变量", "description": "突变"},
                {"name": "chemotherapy", "label_zh": "化疗", "data_type": "string", "role": "研究变量", "description": "治疗"},
                {"name": "treatment_response", "label_zh": "治疗响应", "data_type": "string", "role": "研究结局", "description": "结局"},
            ],
            "rows": [
                {
                    "patient_id": "P1",
                    "disease": "乳腺癌",
                    "pik3ca_mutation": 1,
                    "chemotherapy": "是",
                    "treatment_response": "pCR",
                }
            ],
            "row_count": 1,
            "patient_count": 1,
            "sample_count": 1,
            "target_column": "treatment_response",
        }
    )
    readiness = ResearchDatasetBuilder().empty()[1].model_copy(
        update={"target_column": "treatment_response", "target_match": True}
    )
    spec = ResearchSpec(
        task_id="alias-test",
        research_goal="研究 HER2 阳性乳腺癌治疗响应",
        disease="Breast Cancer",
        genes=["PIK3CA"],
        outcomes=["treatment_response"],
        required_data_types=["clinical", "mutation", "treatment_response"],
    )

    _design, cohort = StudyDesignBuilder().build(spec, dataset, readiness, [], [])
    missing_step = next(step for step in cohort.filter_steps if step.step_id == "exclude_missing_key_variables")

    assert missing_step.status == "已执行"
    assert missing_step.after_count == 1
    assert cohort.final_row_count == 1


def test_plan_only_returns_design_rules_without_claiming_a_built_cohort() -> None:
    dataset, readiness = ResearchDatasetBuilder().empty()
    spec = ResearchSpec(
        task_id="plan-only-test",
        research_goal="规划 HER2 阳性乳腺癌治疗响应研究",
        disease="Breast Cancer",
        subtype="HER2-positive",
        genes=["PIK3CA"],
        outcomes=["treatment_response"],
        required_data_types=["clinical", "mutation", "treatment_response"],
    )

    design, cohort = StudyDesignBuilder().build(
        spec,
        dataset,
        readiness,
        [],
        [],
        "plan_only",
    )

    assert design.status == "已生成"
    assert "仅规划模式" in design.generation_note
    assert cohort.status == "已生成规则"
    assert cohort.execution_mode == "plan_only"
    assert cohort.has_observed_rows is False
    assert cohort.not_run_reason
    assert cohort.filter_steps
    assert all(step.status == "待复核" for step in cohort.filter_steps)


def test_her2_positive_question_uses_her2_status_not_erbb2_mutation() -> None:
    dataset = ResearchDatasetBuilder().empty()[0]
    dataset = dataset.model_copy(
        update={
            "columns": [
                {"name": "patient_id", "label_zh": "患者编号", "data_type": "string", "role": "分析单位", "description": "患者"},
                {"name": "disease", "label_zh": "疾病", "data_type": "string", "role": "研究变量", "description": "疾病"},
                {"name": "her2_status", "label_zh": "HER2", "data_type": "string", "role": "研究变量", "description": "HER2"},
                {"name": "treatment", "label_zh": "治疗", "data_type": "string", "role": "研究变量", "description": "治疗"},
                {"name": "treatment_response", "label_zh": "治疗响应", "data_type": "string", "role": "研究结局", "description": "结局"},
                {"name": "sample_id", "label_zh": "样本编号", "data_type": "string", "role": "分析单位", "description": "样本"},
            ],
            "rows": [
                {
                    "patient_id": "P1",
                    "disease": "乳腺癌",
                    "her2_status": "阳性",
                    "treatment": "曲妥珠单抗新辅助治疗",
                    "treatment_response": "pCR",
                    "sample_id": "S1",
                }
            ],
            "row_count": 1,
            "patient_count": 1,
            "sample_count": 1,
            "target_column": "treatment_response",
        }
    )
    spec = ResearchSpec(
        task_id="her2-fields",
        research_goal="研究 HER2 阳性乳腺癌中 PIK3CA 突变是否影响治疗响应",
        disease="Breast Cancer",
        subtype="HER2-positive",
        genes=["ERBB2", "PIK3CA", "TP53"],
        outcomes=["treatment_response"],
        required_data_types=["clinical", "mutation", "treatment_response"],
    )

    design, _cohort = StudyDesignBuilder().build(spec, dataset, ResearchDatasetBuilder().empty()[1], [], [])
    by_id = {variable.variable_id: variable for variable in design.required_variables}

    assert "erbb2_mutation" not in by_id
    assert by_id["subtype"].available is True
    assert by_id["treatment"].available is True
    assert by_id["pik3ca_mutation"].required is True
    assert by_id["pik3ca_mutation"].available is False
    assert by_id["tp53_mutation"].required is False

