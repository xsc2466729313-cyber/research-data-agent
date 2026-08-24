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
