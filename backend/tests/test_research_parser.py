from backend.app.agent.research_parser import ResearchQuestionParser
from backend.app.agent.study_design import StudyDesignBuilder
from backend.app.agent.dataset_builder import ResearchDatasetBuilder
from backend.app.models import ResearchSpec


QUESTION = "研究 HER2 阳性乳腺癌中 PIK3CA 突变是否影响治疗响应"


def _spec() -> ResearchSpec:
    return ResearchSpec(
        task_id="parser-test",
        research_goal=QUESTION,
        disease="Breast Cancer",
        subtype="HER2-positive",
        genes=["PIK3CA"],
        outcomes=["treatment_response"],
        required_data_types=["clinical", "mutation", "treatment_response"],
    )


def test_parser_emits_pico_fields_from_research_spec() -> None:
    parsed = ResearchQuestionParser().parse(QUESTION, _spec())

    assert parsed.disease == "Breast Cancer"
    assert "HER2-positive" in parsed.population
    assert "PIK3CA" in parsed.exposure
    assert "treatment_response" in parsed.outcome
    assert parsed.required_variables == ["clinical", "mutation", "treatment_response"]


def test_parser_prefers_study_design_required_variables() -> None:
    spec = _spec()
    dataset, readiness = ResearchDatasetBuilder().empty()
    design, _cohort = StudyDesignBuilder().build(spec, dataset, readiness, [], [])
    parsed = ResearchQuestionParser().parse(QUESTION, spec, design)

    assert parsed.population == design.population
    assert parsed.exposure == design.exposure
    assert parsed.outcome == design.outcome
    assert parsed.research_type == design.research_type
    required = [variable.variable_id for variable in design.required_variables if variable.required]
    assert parsed.required_variables == required
    assert "disease" in parsed.required_variables
    assert "pik3ca_mutation" in parsed.required_variables
