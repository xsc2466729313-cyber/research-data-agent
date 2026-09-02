from __future__ import annotations

import pytest

from backend.app.agent.accession_harvest import seed_geo_accessions
from backend.app.agent.models import AgentTaskRequest
from backend.app.agent.service import ResearchAgentService
from backend.app.literature import LiteratureScanRequest, PaperRecord
from backend.app.oncology import CANCER_PROFILES, canonical_disease_name, resolve_cancer_profile
from backend.app.research_planning import (
    QuestionSelectionRequest,
    ResearchPlanningService,
    TopicCreateRequest,
)
from backend.app.research_planning.formulation_agent import ResearchFormulationAgent
from backend.app.research_planning.intent_agent import ResearchIntentAgent
from backend.app.source_broker.models import SourcePlanRequest
from backend.app.source_broker.source_catalog import SeedSourceCatalog


ADDED_CANCER_CASES = (
    ("肺鳞癌 TP53", "Lung Squamous Cell Carcinoma", "TCGA-LUSC", "TP53"),
    ("前列腺癌 SPOP", "Prostate Adenocarcinoma", "TCGA-PRAD", "SPOP"),
    ("肝细胞癌 CTNNB1", "Liver Hepatocellular Carcinoma", "TCGA-LIHC", "CTNNB1"),
    ("胃癌 ERBB2", "Stomach Adenocarcinoma", "TCGA-STAD", "ERBB2"),
    ("胰腺癌 SMAD4", "Pancreatic Adenocarcinoma", "TCGA-PAAD", "SMAD4"),
    ("卵巢癌 BRCA1", "Ovarian Serous Cystadenocarcinoma", "TCGA-OV", "BRCA1"),
    ("肾透明细胞癌 VHL", "Kidney Renal Clear Cell Carcinoma", "TCGA-KIRC", "VHL"),
    ("膀胱癌 FGFR3", "Bladder Urothelial Carcinoma", "TCGA-BLCA", "FGFR3"),
    ("子宫内膜癌 ARID1A", "Uterine Corpus Endometrial Carcinoma", "TCGA-UCEC", "ARID1A"),
    ("头颈鳞癌 CDKN2A", "Head and Neck Squamous Cell Carcinoma", "TCGA-HNSC", "CDKN2A"),
    ("胶质母细胞瘤 IDH1", "Glioblastoma", "TCGA-GBM", "IDH1"),
    ("甲状腺癌 NRAS", "Thyroid Carcinoma", "TCGA-THCA", "NRAS"),
    ("皮肤黑色素瘤 BRAF", "Skin Cutaneous Melanoma", "TCGA-SKCM", "BRAF"),
    ("宫颈癌 PIK3CA", "Cervical Cancer", "TCGA-CESC", "PIK3CA"),
    ("食管癌 CCND1", "Esophageal Carcinoma", "TCGA-ESCA", "CCND1"),
)


def test_configured_cancer_aliases_resolve_to_separate_profiles() -> None:
    lung = resolve_cancer_profile("肺腺癌 EGFR 突变")
    colorectal = resolve_cancer_profile("colorectal cancer KRAS")

    assert lung is not None
    assert lung.canonical_name == "Lung Adenocarcinoma"
    assert lung.gdc_projects == ("TCGA-LUAD",)
    assert colorectal is not None
    assert colorectal.canonical_name == "Colorectal Cancer"
    assert colorectal.cbioportal_studies == ("coadread_tcga_pan_can_atlas_2018",)


@pytest.mark.parametrize(("question", "disease", "project_id", "gene"), ADDED_CANCER_CASES)
def test_added_cancers_resolve_and_parse_without_breast_fallback(
    question: str,
    disease: str,
    project_id: str,
    gene: str,
) -> None:
    profile = resolve_cancer_profile(question)
    spec = ResearchAgentService._deterministic_spec(
        f"研究{question}突变与生存结局的关系",
        f"task-{project_id.casefold()}",
    )

    assert profile is not None
    assert profile.canonical_name == disease
    assert profile.gdc_projects == (project_id,)
    assert spec.disease == disease
    assert gene in spec.genes

    request = AgentTaskRequest(
        question=spec.research_goal,
        use_qwen=False,
        data_mode="plan_only",
        max_sources=8,
    )
    service = ResearchAgentService()
    calls = service._guard_tool_arguments(
        service._deterministic_tool_calls(spec, request),
        spec,
        request,
    )
    serialized = str(calls).casefold()
    assert profile.cbioportal_studies[0] in serialized
    assert project_id.casefold() in serialized
    assert "brca_" not in serialized
    assert "tcga-brca" not in serialized


def test_every_configured_profile_is_available_in_seed_catalog() -> None:
    catalog = SeedSourceCatalog()
    dataset_ids = {item.dataset_id for item in catalog.datasets()}

    for profile in CANCER_PROFILES:
        assert {f"cbioportal:{study_id}" for study_id in profile.cbioportal_studies} <= dataset_ids
        assert {f"gdc:{project_id}" for project_id in profile.gdc_projects} <= dataset_ids


def test_unconfigured_cancer_keeps_its_name_and_uses_generic_discovery() -> None:
    service = ResearchAgentService()
    question = "研究胆管癌中 IDH1 突变与生存结局的关系"
    spec = service._deterministic_spec(question, "task-cholangiocarcinoma")
    request = AgentTaskRequest(question=question, use_qwen=False, data_mode="plan_only", max_sources=8)
    calls = service._guard_tool_arguments(
        service._deterministic_tool_calls(spec, request),
        spec,
        request,
    )
    serialized = str(calls).casefold()

    assert canonical_disease_name(question) == "胆管癌"
    assert spec.disease == "胆管癌"
    assert resolve_cancer_profile(spec.disease) is None
    assert "search_geo_catalog" in serialized
    assert "search_europe_pmc" in serialized
    assert "brca" not in serialized
    assert "tcga-" not in serialized

    topic = ResearchIntentAgent().understand(TopicCreateRequest(topic=question))
    assert topic.disease == "胆管癌"


def test_non_breast_population_is_not_rendered_as_breast_cancer() -> None:
    assert (
        ResearchFormulationAgent._zh_population("Pancreatic Adenocarcinoma patients")
        == "胰腺腺癌患者"
    )


def test_non_breast_evidence_drafts_use_cancer_neutral_fields() -> None:
    topic = ResearchIntentAgent().understand(
        TopicCreateRequest(topic="研究胰腺癌患者 KRAS 突变与生存结局")
    )
    paper = PaperRecord(
        paper_id="pmid:1",
        source_id="pubmed",
        provider="test",
        title="KRAS molecular status and overall survival in pancreatic cancer",
        source_url="https://pubmed.ncbi.nlm.nih.gov/1/",
        abstract="A pancreatic cancer cohort compared KRAS subgroups and overall survival.",
    )

    drafts = ResearchFormulationAgent()._evidence_drafts(topic, [paper])
    serialized = str(drafts).casefold()

    assert drafts
    assert "胰腺腺癌患者" in str(drafts)
    assert "survival" in drafts[0].field_hints
    assert "乳腺癌" not in serialized
    assert "her2_status" not in serialized
    assert "er_status" not in serialized
    assert "pr_status" not in serialized


def test_deterministic_spec_does_not_fall_back_other_cancers_to_breast() -> None:
    lung = ResearchAgentService._deterministic_spec(
        "研究肺腺癌中 EGFR 突变与生存结局的关系",
        "task-luad",
    )
    colorectal = ResearchAgentService._deterministic_spec(
        "研究结直肠癌 KRAS/BRAF 突变与预后",
        "task-crc",
    )

    assert lung.disease == "Lung Adenocarcinoma"
    assert lung.genes == ["EGFR"]
    assert colorectal.disease == "Colorectal Cancer"
    assert colorectal.genes == ["KRAS", "BRAF"]
    assert seed_geo_accessions(lung) == []


def test_tool_guard_replaces_cross_cancer_projects_with_matching_defaults() -> None:
    service = ResearchAgentService()
    question = "研究肺腺癌中 EGFR 突变与生存结局的关系"
    spec = service._deterministic_spec(question, "task-luad-guard")
    request = AgentTaskRequest(question=question, use_qwen=False, data_mode="plan_only", max_sources=4)

    guarded = service._guard_tool_arguments(
        [
            {
                "id": "wrong-cbio",
                "name": "search_cbioportal",
                "arguments": {"study_id": "brca_metabric", "gene_symbols": ["EGFR"]},
            },
            {
                "id": "wrong-gdc",
                "name": "search_gdc",
                "arguments": {"project_id": "TCGA-BRCA"},
            },
            {
                "id": "civic",
                "name": "search_civic",
                "arguments": {"disease_name": "Breast Cancer"},
            },
        ],
        spec,
        request,
    )
    by_name = {call["name"]: call["arguments"] for call in guarded}

    assert by_name["search_cbioportal"]["study_id"] == "luad_tcga_pan_can_atlas_2018"
    assert by_name["search_gdc"]["project_id"] == "TCGA-LUAD"
    assert by_name["search_civic"]["disease_name"] == "Lung Adenocarcinoma"


def test_non_breast_planner_uses_only_matching_seed_cohorts() -> None:
    service = ResearchAgentService()
    question = "研究结直肠癌中 KRAS 突变与生存结局的关系"
    spec = service._deterministic_spec(question, "task-crc-plan")
    request = AgentTaskRequest(question=question, use_qwen=False, data_mode="plan_only", max_sources=8)

    calls = service._guard_tool_arguments(
        service._deterministic_tool_calls(spec, request),
        spec,
        request,
    )
    serialized = str(calls).casefold()

    assert "coadread_tcga_pan_can_atlas_2018" in serialized
    assert "tcga-coad" in serialized
    assert "brca_" not in serialized
    assert "tcga-brca" not in serialized
    assert "gse25066" not in serialized


def test_planning_workspace_filters_seed_catalog_by_cancer() -> None:
    service = ResearchPlanningService()
    service.literature_agent.providers = []
    topic = service.create_topic(TopicCreateRequest(topic="肺腺癌 EGFR 突变与生存结局"))
    service.scan_literature(topic.topic_id, LiteratureScanRequest(max_records=5))
    candidate = service.question_candidates(topic.topic_id).candidates[0]
    contract = service.select_question(candidate.candidate_id, QuestionSelectionRequest())

    result = service.plan_sources(contract.contract_id, SourcePlanRequest())
    dataset_ids = {item.dataset_id for item in result.dataset_candidates}

    assert dataset_ids == {
        "cbioportal:luad_tcga_pan_can_atlas_2018",
        "gdc:TCGA-LUAD",
    }
