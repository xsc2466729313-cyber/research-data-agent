from __future__ import annotations

from backend.app.agent.closed_loop_models import ClosedLoopRequest
from backend.app.agent.closed_loop import ClosedLoopService
from backend.app.agent.dataset_builder import ResearchDatasetBuilder
from backend.app.agent.models import (
    AgentTaskRequest,
    CollectionSearchAction,
    DatasetColumn,
    ModelingDataset,
)
from backend.app.agent.outcome_repair import diagnose_outcome_gap
from backend.app.agent.service import ResearchAgentService
from backend.app.models import ResearchSpec


QUESTION = "研究 HER2 阳性乳腺癌新辅助治疗病理完全缓解（pCR）与临床特征的关系"


def _spec() -> ResearchSpec:
    return ResearchSpec(
        task_id="outcome-repair-test",
        research_goal=QUESTION,
        disease="Breast Cancer",
        subtype="HER2-positive",
        genes=[],
        outcomes=["pCR"],
        required_data_types=["clinical", "treatment_response"],
    )


def _dataset(name: str, rows: list[dict], target: str | None = None) -> ModelingDataset:
    columns = [
        DatasetColumn(name=key, label_zh=key, data_type="string", role="研究结局" if key in {"pcr", "os_status"} else "协变量", description=key)
        for key in (rows[0] if rows else {})
    ]
    return ModelingDataset(
        name=name,
        unit_of_analysis="患者",
        columns=columns,
        rows=rows,
        row_count=len(rows),
        patient_count=len(rows),
        sample_count=len(rows),
        target_column=target,
    )


def test_wrong_cohort_plans_geo_pcr_switch_not_survival_as_pcr() -> None:
    plan = diagnose_outcome_gap(
        spec=_spec(),
        dataset=_dataset(
            "METABRIC",
            [{"patient_id": "P1", "os_status": "1:DECEASED", "os_months": 40, "source_id": "cbioportal:brca_metabric"}],
            target="os_status",
        ),
        target_match_rate=0.0,
        question=QUESTION,
    )
    assert plan.gap_kind == "wrong_cohort"
    assert "GSE25066" in plan.focus_accessions
    assert "search_geo" in plan.focus_tools
    assert "生存" in plan.rationale or "pCR" in plan.rationale
    assert "冒充" in plan.forbidden_note


def test_maps_survival_synonyms_but_not_os_to_pcr() -> None:
    survival_spec = ResearchSpec(
        task_id="surv",
        research_goal="乳腺癌总体生存 OS 与临床特征",
        disease="Breast Cancer",
        outcomes=["survival"],
        required_data_types=["clinical"],
    )
    rows = [
        {
            "patient_id": "P1",
            "overall_survival": 48.5,
            "dss_status": "0:LIVING",
            "source_id": "cbioportal:brca_metabric",
        }
    ]
    mapped, actions = ResearchDatasetBuilder._map_outcome_synonyms(rows, survival_spec)
    assert mapped[0]["os_months"] == 48.5
    assert mapped[0]["dss_status"] == "0:LIVING"
    assert mapped[0].get("pcr") in {None, ""}
    assert any("生存" in item for item in actions)

    pcr_rows = [{"patient_id": "P1", "os_status": "1:DECEASED", "os_months": 12, "source_id": "cbioportal:brca_metabric"}]
    pcr_mapped, _ = ResearchDatasetBuilder._map_outcome_synonyms(pcr_rows, _spec())
    assert pcr_mapped[0].get("pcr") in {None, ""}
    assert pcr_mapped[0]["os_status"] == "1:DECEASED"


def test_closed_loop_round2_switches_to_pcr_cohort_and_metrics_improve() -> None:
    base = ResearchAgentService().run(
        AgentTaskRequest(question=QUESTION, use_qwen=False, data_mode="plan_only", max_sources=2, max_records=100, iterative_collection=False)
    )
    first_dataset = _dataset(
        "METABRIC",
        [{"patient_id": f"P{i}", "os_status": "0:LIVING", "source_id": "cbioportal:brca_metabric"} for i in range(40)],
        target=None,
    )
    second_dataset = _dataset(
        "GSE25066",
        [{"patient_id": f"S{i}", "pcr": "pCR", "treatment_response": "pCR", "source_id": "geo:GSE25066"} for i in range(50)],
        target="pcr",
    )
    first = base.model_copy(update={
        "research_spec": _spec(),
        "modeling_dataset": first_dataset,
        "readiness": base.readiness.model_copy(update={
            "requested_variable_coverage_rate": 0.69,
            "target_match": False,
            "target_match_rate": 0.0,
            "status": "研究结局不匹配",
        }),
        "collection_agent": base.collection_agent.model_copy(update={
            "next_actions": [
                CollectionSearchAction(
                    action_id="switch-gse25066",
                    tool_name="search_geo",
                    source_name="NCBI GEO",
                    priority=1,
                    rationale="换有 pCR 的队列",
                    status="待执行",
                    arguments={"accession": "GSE25066", "max_files": 5},
                    strategy_id="cohort.geo.gse25066",
                    strategy_label="GSE25066",
                )
            ]
        }) if base.collection_agent else None,
    })
    second = first.model_copy(update={
        "modeling_dataset": second_dataset,
        "readiness": first.readiness.model_copy(update={
            "requested_variable_coverage_rate": 0.82,
            "target_match": True,
            "target_match_rate": 1.0,
            "status": "可支持科研分析",
        }),
        "collection_agent": first.collection_agent.model_copy(update={"next_actions": []}) if first.collection_agent else None,
    })
    calls = []

    def runner(request, **_kwargs):
        calls.append(request)
        return first if len(calls) == 1 else second

    response = ClosedLoopService(object(), runner=runner).run(ClosedLoopRequest(
        initial_request=AgentTaskRequest(question=QUESTION, use_qwen=False, data_mode="plan_only", max_sources=2, max_records=100, iterative_collection=False),
        max_iterations=2,
        min_improvement=0.01,
    ))

    assert len(calls) == 2
    assert "GSE25066" in calls[1].focus_accessions
    assert "search_geo" in calls[1].focus_tools or "search_geo" in calls[1].preferred_sources
    assert response.completed_iterations == 2
    assert response.improved is True
    assert response.presentation == "comparison"
    assert response.iterations[1].metrics.target_match_rate > response.iterations[0].metrics.target_match_rate
    assert response.iterations[1].metrics.required_field_coverage > response.iterations[0].metrics.required_field_coverage
    assert any("GSE25066" in item for item in response.attempted_repairs)


def test_closed_loop_round2_drops_outcome_mismatch_diagnosis_when_pcr_arrives() -> None:
    from backend.app.agent.quality_gate import QualityGateBuilder

    base = ResearchAgentService().run(
        AgentTaskRequest(question=QUESTION, use_qwen=False, data_mode="plan_only", max_sources=2, max_records=100, iterative_collection=False)
    )
    first_dataset = _dataset(
        "METABRIC",
        [{"patient_id": f"P{i}", "os_status": "0:LIVING", "source_id": "cbioportal:brca_metabric"} for i in range(40)],
        target=None,
    )
    second_dataset = _dataset(
        "GSE25066",
        [
            {
                "patient_id": f"S{i}",
                "pcr": "pCR",
                "treatment_response": "pCR",
                "her2_status": "阳性",
                "source_id": "geo:GSE25066",
                "study_id": "GSE25066",
            }
            for i in range(50)
        ],
        target="pcr",
    )
    first = base.model_copy(update={
        "research_spec": _spec(),
        "modeling_dataset": first_dataset,
        "readiness": base.readiness.model_copy(update={
            "requested_variable_coverage_rate": 0.33,
            "target_match": False,
            "target_match_rate": 0.0,
            "status": "研究结局不匹配",
            "analysis_ready": False,
            "target_column": None,
        }),
    })
    second = first.model_copy(update={
        "modeling_dataset": second_dataset,
        "readiness": first.readiness.model_copy(update={
            "requested_variable_coverage_rate": 0.82,
            "target_match": True,
            "target_match_rate": 1.0,
            "status": "可支持科研分析",
            "analysis_ready": True,
            "target_column": "pcr",
            "field_completeness_rate": 0.42,
        }),
        "collection_agent": first.collection_agent.model_copy(update={"critical_gaps": [], "next_actions": []}) if first.collection_agent else None,
    })
    first = first.model_copy(update={"quality_gate_report": QualityGateBuilder().build(first)})
    second = second.model_copy(update={"quality_gate_report": QualityGateBuilder().build(second)})
    calls = []

    def runner(request, **_kwargs):
        calls.append(request)
        return first if len(calls) == 1 else second

    response = ClosedLoopService(object(), runner=runner).run(ClosedLoopRequest(
        initial_request=AgentTaskRequest(question=QUESTION, use_qwen=False, data_mode="plan_only", max_sources=2, max_records=100, iterative_collection=False),
        max_iterations=2,
        min_improvement=0.01,
    ))

    first_labels = {item.label for item in response.iterations[0].diagnoses}
    second_labels = {item.label for item in response.iterations[1].diagnoses}
    assert "结局或目标字段尚未充分匹配" in first_labels
    assert "结局或目标字段尚未充分匹配" not in second_labels
    field_first = next(layer.decision for layer in first.quality_gate_report.layers if layer.gate_id == "field_quality")
    field_second = next(layer.decision for layer in second.quality_gate_report.layers if layer.gate_id == "field_quality")
    assert field_first == "REVIEW"
    assert field_second == "PASS"
    assert response.iterations[1].metrics.target_match_rate > response.iterations[0].metrics.target_match_rate
    assert "GSE25066" in calls[1].focus_accessions


def test_her2_ihc_two_plus_is_not_mapped_positive() -> None:
    rows = [{"patient_id": "P1", "her2_status_ihc": "2+", "source_id": "geo:GSE25066"}]
    mapped, actions = ResearchDatasetBuilder._map_her2_synonyms(rows)
    assert mapped[0]["her2_status"] == "2+"
    assert ResearchDatasetBuilder._receptor_polarity(mapped[0]["her2_status"]) == "equivocal"
    assert actions
