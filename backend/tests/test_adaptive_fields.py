from backend.app.agent.accession_harvest import asks_sample_timepoint, asks_treatment, needs_clinical_outcome
from backend.app.agent.collection_agent import CollectionAgent
from backend.app.agent.dataset_builder import ResearchDatasetBuilder
from backend.app.agent.study_design import StudyDesignBuilder
from backend.app.models import ResearchSpec


def _tnbc_pcr_spec() -> ResearchSpec:
    return ResearchSpec(
        task_id="tnbc-pcr",
        research_goal="研究三阴性乳腺癌中 BRCA1/BRCA2 突变与新辅助化疗病理完全缓解（pCR）的关系，并整理患者级科研数据集",
        disease="Breast Cancer",
        subtype="Triple-negative",
        genes=["BRCA1", "BRCA2"],
        outcomes=["pCR"],
        required_data_types=["clinical", "mutation"],
    )


def _molecular_spec() -> ResearchSpec:
    return ResearchSpec(
        task_id="molecular-only",
        research_goal="研究乳腺癌中 TP53 突变的队列分布",
        disease="Breast Cancer",
        genes=["TP53"],
        outcomes=[],
        required_data_types=["clinical", "mutation"],
    )


def test_pcr_question_does_not_require_treatment_plan_or_timepoint() -> None:
    spec = _tnbc_pcr_spec()
    assert asks_treatment(spec) is False
    assert asks_sample_timepoint(spec) is False
    assert needs_clinical_outcome(spec) is True

    rows = [
        {
            "study_id": "GSE25066",
            "patient_id": "P1",
            "sample_id": "S1",
            "source_id": "geo:GSE25066",
            "disease": "乳腺癌",
            "er_status": "阴性",
            "pr_status": "阴性",
            "her2_status": "阴性",
            "brca1_mutation": 1,
            "brca2_mutation": 0,
            "pcr": "病理完全缓解（pCR）",
            "sample_type": "原发肿瘤",
            "claudin_subtype": "Basal",
            "npi": 4.2,
        }
    ]
    dataset = ResearchDatasetBuilder()._dataset_from_rows(rows, name="TNBC pCR", unit="患者", spec=spec)
    readiness = ResearchDatasetBuilder()._readiness(dataset, spec)
    design, _cohort = StudyDesignBuilder().build(spec, dataset, readiness, [], [])
    by_id = {variable.variable_id: variable for variable in design.required_variables}
    _iteration, critical, _recommended = CollectionAgent().inspect(
        spec=spec,
        dataset=dataset,
        readiness=readiness,
        design=design,
        source_names=["NCBI GEO"],
        source_items=[],
        round_number=1,
        attempted_calls=set(),
        actions=[],
    )

    assert by_id["outcome"].required is True
    assert by_id["outcome"].available is True
    assert by_id["treatment"].required is False
    assert by_id["sample_timepoint"].required is False
    assert "treatment" not in {gap.variable_id for gap in critical}
    assert "sample_timepoint" not in {gap.variable_id for gap in critical}
    names = [column.name for column in dataset.columns]
    assert names.index("brca1_mutation") < names.index("claudin_subtype")
    assert names.index("pcr") < names.index("npi")
    roles = {column.name: column.role for column in dataset.columns}
    assert roles["claudin_subtype"] == "次要临床字段"
    assert roles["npi"] == "次要临床字段"
    assert dataset.rows[0]["derived_ihc_subtype"] == "Triple-negative"
    assert dataset.rows[0]["pcr_binary"] == 1
    assert dataset.rows[0]["brca_any_mutation"] == 1
    assert dataset.target_column in {"pcr", "pcr_binary"}


def test_molecular_question_does_not_force_treatment_or_outcome() -> None:
    spec = _molecular_spec()
    dataset = ResearchDatasetBuilder()._dataset_from_rows(
        [
            {
                "patient_id": "P1",
                "sample_id": "S1",
                "disease": "乳腺癌",
                "tp53_mutation": 1,
                "sample_type": "原发肿瘤",
            }
        ],
        name="分子队列",
        unit="患者",
        spec=spec,
    )
    design, _cohort = StudyDesignBuilder().build(
        spec,
        dataset,
        ResearchDatasetBuilder()._readiness(dataset, spec),
        [],
        [],
    )
    by_id = {variable.variable_id: variable for variable in design.required_variables}

    assert "outcome" not in by_id or by_id["outcome"].required is False
    assert "treatment" not in by_id or by_id["treatment"].required is False
    assert by_id["tp53_mutation"].required is True
    assert by_id["tp53_mutation"].available is True


def test_same_row_receptors_derive_tnbc_but_cna_is_not_ihc() -> None:
    spec = _tnbc_pcr_spec()
    dataset = ResearchDatasetBuilder()._dataset_from_rows(
        [
            {
                "patient_id": "P1",
                "sample_id": "S1",
                "disease": "乳腺癌",
                "er_status": "阴性",
                "pr_status": "阴性",
                "her2_status": "2+",
                "erbb2_cna": 2,
                "brca1_mutation": 0,
                "brca2_mutation": 0,
                "pcr": "NOR",
            },
            {
                "patient_id": "P2",
                "sample_id": "S2",
                "disease": "乳腺癌",
                "er_status": "阴性",
                "pr_status": "阴性",
                "her2_status": "阴性",
                "erbb2_cna": 2,
                "brca1_mutation": 1,
                "brca2_mutation": 0,
                "treatment_response": "病理完全缓解（pCR）",
            },
        ],
        name="受体派生",
        unit="患者",
        spec=spec,
    )
    first, second = dataset.rows
    assert "derived_ihc_subtype" not in first or first.get("derived_ihc_subtype") != "Triple-negative"
    assert first.get("subtype") != "Triple-negative"
    assert second["derived_ihc_subtype"] == "Triple-negative"
    assert second["pcr_binary"] == 1
    assert "erbb2_altered" not in {column.name for column in dataset.columns}
    subtype_column = next(item for item in dataset.columns if item.name == "derived_ihc_subtype")
    assert "2+" in subtype_column.description


def test_gene_altered_combines_mutation_and_cna_without_calling_it_ihc() -> None:
    spec = ResearchSpec(
        task_id="cna-combine",
        research_goal="研究乳腺癌中 PIK3CA 突变与拷贝数",
        disease="Breast Cancer",
        genes=["PIK3CA"],
        outcomes=[],
        required_data_types=["mutation"],
    )
    dataset = ResearchDatasetBuilder()._dataset_from_rows(
        [
            {
                "patient_id": "P1",
                "sample_id": "S1",
                "disease": "乳腺癌",
                "pik3ca_mutation": 0,
                "pik3ca_cna": 2,
                "her2_status": None,
            }
        ],
        name="分子改变",
        unit="患者",
        spec=spec,
    )
    row = dataset.rows[0]
    assert row["pik3ca_altered"] == 1
    assert row.get("her2_status") in {None, ""}
    assert row.get("derived_ihc_subtype") is None
    column = next(item for item in dataset.columns if item.name == "pik3ca_altered")
    assert column.role == "同队列派生"
    assert "IHC" in column.description


def test_age_group_is_derived_from_same_row_age() -> None:
    spec = _molecular_spec()
    dataset = ResearchDatasetBuilder()._dataset_from_rows(
        [{"patient_id": "P1", "sample_id": "S1", "disease": "乳腺癌", "tp53_mutation": 0, "age": 62}],
        name="年龄派生",
        unit="患者",
        spec=spec,
    )
    assert dataset.rows[0]["age_group"] == "60-69"


def test_survival_is_not_used_as_pcr() -> None:
    spec = _tnbc_pcr_spec()
    dataset = ResearchDatasetBuilder()._dataset_from_rows(
        [
            {
                "patient_id": "P1",
                "sample_id": "S1",
                "disease": "乳腺癌",
                "brca1_mutation": 0,
                "brca2_mutation": 0,
                "os_status": "DECEASED",
                "os_months": 12,
            }
        ],
        name="生存不是pCR",
        unit="患者",
        spec=spec,
    )
    assert dataset.target_column is None
    assert "pcr_binary" not in {column.name for column in dataset.columns}
    readiness = ResearchDatasetBuilder()._readiness(dataset, spec)
    assert readiness.target_match is False
    assert readiness.status == "研究结局不匹配"
    assert readiness.target_match_rate == 0


def test_outcome_match_rate_is_graded_not_binary() -> None:
    spec = _tnbc_pcr_spec()
    full = ResearchDatasetBuilder()._dataset_from_rows(
        [
            {
                "patient_id": "P1",
                "sample_id": "S1",
                "disease": "乳腺癌",
                "brca1_mutation": 1,
                "brca2_mutation": 0,
                "pcr": "病理完全缓解（pCR）",
            }
        ],
        name="完整pCR",
        unit="患者",
        spec=spec,
    )
    related = ResearchDatasetBuilder()._dataset_from_rows(
        [
            {
                "patient_id": "P1",
                "sample_id": "S1",
                "disease": "乳腺癌",
                "brca1_mutation": 1,
                "brca2_mutation": 0,
                "treatment_response": "客观缓解",
            }
        ],
        name="相关响应",
        unit="患者",
        spec=spec,
    )
    partial = ResearchDatasetBuilder()._dataset_from_rows(
        [
            {
                "patient_id": "P1",
                "sample_id": "S1",
                "disease": "乳腺癌",
                "brca1_mutation": 1,
                "brca2_mutation": 0,
                "pcr": "病理完全缓解（pCR）",
            },
            {
                "patient_id": "P2",
                "sample_id": "S2",
                "disease": "乳腺癌",
                "brca1_mutation": 0,
                "brca2_mutation": 0,
            },
        ],
        name="部分pCR",
        unit="患者",
        spec=spec,
    )
    full_rate = ResearchDatasetBuilder()._readiness(full, spec).target_match_rate
    related_rate = ResearchDatasetBuilder()._readiness(related, spec).target_match_rate
    partial_rate = ResearchDatasetBuilder()._readiness(partial, spec).target_match_rate
    assert full_rate == 1.0
    assert 0.7 <= related_rate < 1.0
    assert 0.4 <= partial_rate <= 0.6


def test_gene_cna_alone_is_partial_not_full_mutation_match() -> None:
    spec = ResearchSpec(
        task_id="cna-only",
        research_goal="研究乳腺癌中 PIK3CA 突变分布",
        disease="Breast Cancer",
        genes=["PIK3CA"],
        outcomes=[],
        required_data_types=["mutation"],
    )
    dataset = ResearchDatasetBuilder()._dataset_from_rows(
        [{"patient_id": "P1", "sample_id": "S1", "disease": "乳腺癌", "pik3ca_cna": 2}],
        name="仅拷贝数",
        unit="患者",
        spec=spec,
    )
    rate = ResearchDatasetBuilder()._readiness(dataset, spec).requested_variable_coverage_rate
    assert rate is not None
    assert 0.45 <= rate < 1.0


def test_required_variable_coverage_uses_row_fill_not_any_value() -> None:
    spec = _tnbc_pcr_spec()
    dataset = ResearchDatasetBuilder()._dataset_from_rows(
        [
            {
                "patient_id": "P1",
                "sample_id": "S1",
                "disease": "乳腺癌",
                "sample_type": "原发肿瘤",
                "brca1_mutation": 1,
                "brca2_mutation": 0,
                "pcr": "病理完全缓解（pCR）",
            },
            {
                "patient_id": "P2",
                "sample_id": "S2",
                "disease": "乳腺癌",
                "brca1_mutation": 0,
                "brca2_mutation": 0,
                "pcr": "未达病理完全缓解",
            },
        ],
        name="半覆盖样本类型",
        unit="患者",
        spec=spec,
    )
    design, _cohort = StudyDesignBuilder().build(
        spec,
        dataset,
        ResearchDatasetBuilder()._readiness(dataset, spec),
        [],
        [],
    )
    by_id = {variable.variable_id: variable for variable in design.required_variables}
    assert by_id["sample_type"].available is True
    assert by_id["sample_type"].coverage_rate == 0.5
    assert 0 < design.variable_coverage_rate < 1

