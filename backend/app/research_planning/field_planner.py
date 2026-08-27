from __future__ import annotations

from dataclasses import dataclass

from backend.app.literature.models import PaperRecord
from backend.app.research_planning.evidence import evidence_references
from backend.app.research_planning.models import (
    FieldPriority,
    FieldRequirement,
    QuestionCandidate,
    ResearchTopic,
)


@dataclass(frozen=True)
class _FieldDefinition:
    field_id: str
    canonical_name: str
    label: str
    role: str
    priority: FieldPriority
    aliases: tuple[str, ...]
    granularity: str
    data_type: str
    reason: str
    source_hints: tuple[str, ...]
    evidence_terms: tuple[str, ...]
    operational: bool = False


class FieldPlanningAgent:
    """Compile a selected question into Required/Recommended/Optional fields."""

    def plan(
        self,
        candidate: QuestionCandidate,
        papers: list[PaperRecord],
        topic: ResearchTopic | None = None,
    ) -> tuple[list[FieldRequirement], list[FieldRequirement], list[FieldRequirement]]:
        definitions = self._definitions(candidate, topic)
        requirements = [self._requirement(definition, papers) for definition in definitions]
        return (
            [item for item in requirements if item.priority == FieldPriority.REQUIRED],
            [item for item in requirements if item.priority == FieldPriority.RECOMMENDED],
            [item for item in requirements if item.priority == FieldPriority.OPTIONAL],
        )

    @staticmethod
    def _requirement(definition: _FieldDefinition, papers: list[PaperRecord]) -> FieldRequirement:
        evidence = evidence_references(
            papers,
            terms=list(definition.evidence_terms),
            evidence_type=f"field_definition:{definition.field_id}",
            limit=3,
        )
        evidence_status = "operational_rule" if definition.operational else "supported" if evidence else "missing"
        return FieldRequirement(
            field_id=definition.field_id,
            canonical_name=definition.canonical_name,
            label=definition.label,
            role=definition.role,
            priority=definition.priority,
            aliases=list(definition.aliases),
            granularity=definition.granularity,
            data_type=definition.data_type,
            reason=definition.reason,
            source_hints=list(definition.source_hints),
            literature_evidence=evidence,
            evidence_status=evidence_status,
            review_required=(definition.priority == FieldPriority.REQUIRED and evidence_status == "missing"),
        )

    @staticmethod
    def _definitions(
        candidate: QuestionCandidate,
        topic: ResearchTopic | None = None,
    ) -> list[_FieldDefinition]:
        if topic is not None and topic.domain not in {"oncology", "biomedicine"}:
            return FieldPlanningAgent._general_science_definitions(candidate)
        if topic is not None and topic.disease != "breast cancer":
            return FieldPlanningAgent._general_biomedical_definitions(candidate, topic)
        question = candidate.question.casefold()
        definitions = [
            _FieldDefinition(
                "study_id",
                "study_id",
                "研究/队列编号",
                "identity",
                FieldPriority.REQUIRED,
                ("study_id", "dataset_id", "cohort_id"),
                "study",
                "string",
                "不同独立队列只能纵向追加，必须保留研究边界。",
                ("GEO", "cBioPortal", "GDC"),
                (),
                True,
            ),
            _FieldDefinition(
                "patient_id",
                "patient_id",
                "患者编号",
                "identity",
                FieldPriority.REQUIRED,
                ("patient_id", "case_id", "subject_id"),
                "patient",
                "string",
                "用于患者级分析、去重与安全实体关联；低置信度关联进入 review。",
                ("GEO", "cBioPortal", "GDC"),
                (),
                True,
            ),
            _FieldDefinition(
                "sample_id",
                "sample_id",
                "样本编号",
                "identity",
                FieldPriority.REQUIRED,
                ("sample_id", "biospecimen_id", "gsm"),
                "sample",
                "string",
                "用于样本级溯源并防止把不同样本误当同一患者记录。",
                ("GEO", "cBioPortal", "GDC"),
                (),
                True,
            ),
            _FieldDefinition(
                "disease",
                "disease",
                "疾病",
                "population",
                FieldPriority.REQUIRED,
                ("disease", "diagnosis", "cancer_type"),
                "patient",
                "string",
                "确认研究人群疾病边界。",
                ("GEO", "cBioPortal", "GDC"),
                ("breast cancer", "乳腺癌"),
            ),
            _FieldDefinition(
                "source_id",
                "source_id",
                "真实来源编号",
                "provenance",
                FieldPriority.REQUIRED,
                ("source_id", "accession"),
                "record",
                "string",
                "关键非空字段必须可追溯到真实来源。",
                ("official_api", "source_manifest"),
                (),
                True,
            ),
        ]
        if "pik3ca" in question or "pik3ca" in candidate.exposure.casefold():
            definitions.append(
                _FieldDefinition(
                    "pik3ca_mutation",
                    "PIK3CA_mutation",
                    "PIK3CA 突变状态",
                    "primary_exposure",
                    FieldPriority.REQUIRED,
                    ("pik3ca_mutation", "gene", "variant", "mutation_status"),
                    "patient_or_sample",
                    "categorical",
                    "候选问题点名的主要分子暴露，必须来自同一患者/样本队列。",
                    ("cBioPortal", "GDC", "GEO_supplementary"),
                    ("PIK3CA", "mutation"),
                )
            )
        if "gene expression" in question or "基因表达" in question:
            definitions.extend(
                [
                    _FieldDefinition(
                        "gene_expression",
                        "gene_expression",
                        "治疗前基因表达特征",
                        "primary_predictor",
                        FieldPriority.REQUIRED,
                        ("expression", "gene_expression", "normalized_expression"),
                        "sample",
                        "numeric_matrix",
                        "预测任务的主要输入；表达矩阵与临床表必须属于同一研究并有明确样本键。",
                        ("GEO", "GDC"),
                        ("gene expression", "pretreatment", "baseline"),
                    ),
                    _FieldDefinition(
                        "sample_timepoint",
                        "sample_timepoint",
                        "样本采集时间点",
                        "eligibility",
                        FieldPriority.REQUIRED,
                        ("timepoint", "sample_timepoint", "pretreatment"),
                        "sample",
                        "categorical",
                        "必须确认预测特征来自治疗前，避免结局泄漏。",
                        ("GEO", "supplementary_table"),
                        ("pretreatment", "baseline", "before treatment"),
                    ),
                ]
            )
        if any(token in question for token in ("pcr", "response", "治疗响应", "完全缓解")) or "response" in candidate.outcome.casefold():
            definitions.extend(
                [
                    _FieldDefinition(
                        "pcr",
                        "pathological_complete_response",
                        "病理完全缓解 pCR",
                        "primary_outcome",
                        FieldPriority.REQUIRED,
                        ("pcr", "pathological_complete_response", "response", "treatment_response"),
                        "patient",
                        "binary",
                        "候选问题的主要结局；必须来自 clinical response 域，不能由细胞系 AUC/IC50 替代。",
                        ("GEO", "supplementary_table"),
                        ("pCR", "pathological complete response", "pathologic complete response"),
                    ),
                    _FieldDefinition(
                        "response_domain",
                        "response_domain",
                        "响应数据域",
                        "safety",
                        FieldPriority.REQUIRED,
                        ("response_domain",),
                        "record",
                        "categorical",
                        "冻结医学规则要求区分患者临床结局、细胞系药敏、临床试验和知识证据。",
                        ("normalization_rule"),
                        (),
                        True,
                    ),
                    _FieldDefinition(
                        "treatment",
                        "treatment",
                        "新辅助治疗方案",
                        "treatment_context",
                        FieldPriority.RECOMMENDED,
                        ("treatment", "regimen", "therapy", "drug"),
                        "patient",
                        "string",
                        "治疗方案差异可能影响 pCR，需要用于分层或混杂控制。",
                        ("GEO", "supplementary_table", "ClinicalTrials.gov"),
                        ("neoadjuvant", "treatment", "regimen", "therapy"),
                    ),
                ]
            )
        if "her2" in question or "受体亚型" in question:
            priority = FieldPriority.REQUIRED if "her2" in question else FieldPriority.RECOMMENDED
            definitions.append(
                _FieldDefinition(
                    "her2_status",
                    "her2_status",
                    "HER2 状态",
                    "population_or_covariate",
                    priority,
                    ("her2_status", "HER2", "ERBB2"),
                    "patient_or_sample",
                    "categorical",
                    "HER2 IHC 2+ 不得直接判为 Positive，ERBB2 CNA amplification 也不能替代 IHC 状态。",
                    ("GEO", "cBioPortal", "GDC"),
                    ("HER2", "ERBB2"),
                )
            )
        for field_id, label, aliases, terms in (
            ("er_status", "ER 状态", ("er_status", "ER"), ("estrogen receptor", "ER status")),
            ("pr_status", "PR 状态", ("pr_status", "PR", "PgR"), ("progesterone receptor", "PR status")),
            ("age", "年龄", ("age", "age_at_diagnosis"), ("age",)),
            ("stage", "临床分期", ("stage", "clinical_stage"), ("stage",)),
        ):
            definitions.append(
                _FieldDefinition(
                    field_id,
                    field_id,
                    label,
                    "covariate",
                    FieldPriority.RECOMMENDED,
                    aliases,
                    "patient",
                    "categorical" if field_id != "age" else "numeric",
                    "常用临床协变量；缺失不阻断主问题，但会限制混杂控制。",
                    ("GEO", "cBioPortal", "GDC"),
                    terms,
                )
            )
        definitions.append(
            _FieldDefinition(
                "grade",
                "grade",
                "肿瘤分级",
                "covariate",
                FieldPriority.OPTIONAL,
                ("grade", "histological_grade"),
                "patient",
                "categorical",
                "可增强亚组描述，但缺失不影响主问题。",
                ("GEO", "cBioPortal", "GDC"),
                ("grade", "histological grade"),
            )
        )
        deduplicated: list[_FieldDefinition] = []
        seen: set[str] = set()
        for definition in definitions:
            if definition.field_id in seen:
                continue
            seen.add(definition.field_id)
            deduplicated.append(definition)
        return deduplicated

    @staticmethod
    def _general_science_definitions(candidate: QuestionCandidate) -> list[_FieldDefinition]:
        return [
            _FieldDefinition(
                "study_id",
                "study_id",
                "研究/数据集编号",
                "identity",
                FieldPriority.REQUIRED,
                ("study_id", "dataset_id", "catalog_id"),
                "study",
                "string",
                "保留独立研究和数据集边界，避免无依据的跨来源横向合并。",
                ("official_repository", "supplementary_table"),
                (),
                True,
            ),
            _FieldDefinition(
                "observation_id",
                "observation_id",
                "观测编号",
                "identity",
                FieldPriority.REQUIRED,
                ("observation_id", "object_id", "record_id"),
                "observation",
                "string",
                "定义最小分析单位并支持去重与字段级溯源。",
                ("official_repository",),
                (),
                True,
            ),
            _FieldDefinition(
                "primary_exposure",
                "primary_exposure",
                "主要解释变量",
                "primary_exposure",
                FieldPriority.REQUIRED,
                ("primary_exposure", *candidate.field_hints[:1]),
                "observation",
                "numeric_or_categorical",
                f"候选问题中的主要解释变量：{candidate.exposure}",
                ("official_repository", "paper_supplementary"),
                tuple(filter(None, (candidate.exposure,))),
            ),
            _FieldDefinition(
                "primary_outcome",
                "primary_outcome",
                "主要结局/目标量",
                "primary_outcome",
                FieldPriority.REQUIRED,
                ("primary_outcome", *candidate.field_hints[-1:]),
                "observation",
                "numeric_or_categorical",
                f"候选问题中的主要目标量：{candidate.outcome}",
                ("official_repository", "paper_supplementary"),
                tuple(filter(None, (candidate.outcome,))),
            ),
            _FieldDefinition(
                "source_id",
                "source_id",
                "真实来源编号",
                "provenance",
                FieldPriority.REQUIRED,
                ("source_id", "accession", "doi"),
                "record",
                "string",
                "所有外部数据必须保留真实来源。",
                ("source_manifest",),
                (),
                True,
            ),
            _FieldDefinition(
                "measurement_unit",
                "measurement_unit",
                "测量单位",
                "measurement_context",
                FieldPriority.RECOMMENDED,
                ("unit", "measurement_unit"),
                "observation",
                "string",
                "跨来源比较前必须核验单位与量纲。",
                ("methods", "data_dictionary"),
                ("unit", "measurement"),
            ),
            _FieldDefinition(
                "measurement_method",
                "measurement_method",
                "测量方法",
                "measurement_context",
                FieldPriority.OPTIONAL,
                ("method", "instrument", "measurement_method"),
                "observation",
                "string",
                "用于解释跨研究测量差异和潜在系统偏差。",
                ("methods",),
                ("method", "instrument"),
            ),
        ]

    @staticmethod
    def _general_biomedical_definitions(
        candidate: QuestionCandidate,
        topic: ResearchTopic,
    ) -> list[_FieldDefinition]:
        definitions = [
            _FieldDefinition(
                "study_id",
                "study_id",
                "研究/队列编号",
                "identity",
                FieldPriority.REQUIRED,
                ("study_id", "dataset_id", "cohort_id"),
                "study",
                "string",
                "保留研究边界，防止跨队列误合并。",
                ("official_repository",),
                (),
                True,
            ),
            _FieldDefinition(
                "patient_id",
                "patient_id",
                "患者编号",
                "identity",
                FieldPriority.REQUIRED,
                ("patient_id", "case_id", "subject_id"),
                "patient",
                "string",
                "用于患者级去重和安全实体关联；低置信度匹配进入 review。",
                ("official_repository",),
                (),
                True,
            ),
            _FieldDefinition(
                "sample_id",
                "sample_id",
                "样本编号",
                "identity",
                FieldPriority.REQUIRED,
                ("sample_id", "biospecimen_id"),
                "sample",
                "string",
                "保留样本粒度并支持字段级溯源。",
                ("official_repository",),
                (),
                True,
            ),
            _FieldDefinition(
                "disease",
                "disease",
                "疾病",
                "population",
                FieldPriority.REQUIRED,
                ("disease", "diagnosis", "cancer_type"),
                "patient",
                "string",
                "确认研究人群疾病边界。",
                ("official_repository",),
                tuple(filter(None, (topic.disease or "",))),
            ),
            _FieldDefinition(
                "primary_exposure",
                "primary_exposure",
                "主要暴露/干预",
                "primary_exposure",
                FieldPriority.REQUIRED,
                ("primary_exposure", *candidate.field_hints[:1]),
                "patient_or_sample",
                "numeric_or_categorical",
                f"候选问题中的主要暴露：{candidate.exposure}",
                ("official_repository", "supplementary_table"),
                tuple(filter(None, (candidate.exposure,))),
            ),
            _FieldDefinition(
                "primary_outcome",
                "primary_outcome",
                "主要结局",
                "primary_outcome",
                FieldPriority.REQUIRED,
                ("primary_outcome", *candidate.field_hints[-1:]),
                "patient",
                "numeric_or_categorical",
                f"候选问题中的主要结局：{candidate.outcome}",
                ("official_repository", "supplementary_table"),
                tuple(filter(None, (candidate.outcome,))),
            ),
            _FieldDefinition(
                "source_id",
                "source_id",
                "真实来源编号",
                "provenance",
                FieldPriority.REQUIRED,
                ("source_id", "accession"),
                "record",
                "string",
                "所有外部数据必须保留真实来源。",
                ("source_manifest",),
                (),
                True,
            ),
        ]
        for field_id, label in (("age", "年龄"), ("stage", "分期"), ("treatment", "治疗方案")):
            definitions.append(
                _FieldDefinition(
                    field_id,
                    field_id,
                    label,
                    "covariate",
                    FieldPriority.RECOMMENDED,
                    (field_id,),
                    "patient",
                    "numeric" if field_id == "age" else "categorical",
                    "常用临床协变量；缺失不阻断主问题，但会限制混杂控制。",
                    ("official_repository", "supplementary_table"),
                    (field_id,),
                )
            )
        return definitions
