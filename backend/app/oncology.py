from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CancerProfile:
    key: str
    canonical_name: str
    label_zh: str
    aliases: tuple[str, ...]
    cbioportal_studies: tuple[str, ...]
    cbioportal_prefixes: tuple[str, ...]
    gdc_projects: tuple[str, ...]
    default_genes: tuple[str, ...]
    trial_condition: str


CANCER_PROFILES: tuple[CancerProfile, ...] = (
    CancerProfile(
        key="breast_cancer",
        canonical_name="Breast Cancer",
        label_zh="乳腺癌",
        aliases=(
            "breast carcinoma",
            "breast cancer",
            "brca_metabric",
            "tcga-brca",
            "metabric",
            "乳腺癌",
        ),
        cbioportal_studies=("brca_metabric", "brca_tcga_pan_can_atlas_2018"),
        cbioportal_prefixes=("brca_", "breast_"),
        gdc_projects=("TCGA-BRCA",),
        default_genes=("PIK3CA", "ERBB2"),
        trial_condition="Breast Neoplasms",
    ),
    CancerProfile(
        key="lung_adenocarcinoma",
        canonical_name="Lung Adenocarcinoma",
        label_zh="肺腺癌",
        aliases=("lung adenocarcinoma", "lung adeno", "肺腺癌"),
        cbioportal_studies=("luad_tcga_pan_can_atlas_2018",),
        cbioportal_prefixes=("luad_",),
        gdc_projects=("TCGA-LUAD",),
        default_genes=("EGFR", "KRAS", "TP53"),
        trial_condition="Lung Adenocarcinoma",
    ),
    CancerProfile(
        key="lung_squamous_cell_carcinoma",
        canonical_name="Lung Squamous Cell Carcinoma",
        label_zh="肺鳞癌",
        aliases=("lung squamous cell carcinoma", "lung squamous carcinoma", "lusc", "肺鳞癌"),
        cbioportal_studies=("lusc_tcga_pan_can_atlas_2018",),
        cbioportal_prefixes=("lusc_",),
        gdc_projects=("TCGA-LUSC",),
        default_genes=("TP53", "PIK3CA", "SOX2"),
        trial_condition="Lung Squamous Cell Carcinoma",
    ),
    CancerProfile(
        key="colorectal_cancer",
        canonical_name="Colorectal Cancer",
        label_zh="结直肠癌",
        aliases=(
            "colorectal adenocarcinoma",
            "colorectal cancer",
            "colon cancer",
            "rectal cancer",
            "结直肠癌",
            "结肠癌",
            "直肠癌",
        ),
        cbioportal_studies=("coadread_tcga_pan_can_atlas_2018",),
        cbioportal_prefixes=("coadread_", "coad_", "read_", "colorectal_"),
        gdc_projects=("TCGA-COAD", "TCGA-READ"),
        default_genes=("APC", "KRAS", "BRAF", "TP53"),
        trial_condition="Colorectal Neoplasms",
    ),
    CancerProfile(
        key="prostate_adenocarcinoma",
        canonical_name="Prostate Adenocarcinoma",
        label_zh="前列腺腺癌",
        aliases=("prostate adenocarcinoma", "prostate cancer", "prad", "前列腺腺癌", "前列腺癌"),
        cbioportal_studies=("prad_tcga_pan_can_atlas_2018",),
        cbioportal_prefixes=("prad_",),
        gdc_projects=("TCGA-PRAD",),
        default_genes=("AR", "TP53", "SPOP", "PTEN"),
        trial_condition="Prostatic Neoplasms",
    ),
    CancerProfile(
        key="liver_hepatocellular_carcinoma",
        canonical_name="Liver Hepatocellular Carcinoma",
        label_zh="肝细胞癌",
        aliases=("liver hepatocellular carcinoma", "hepatocellular carcinoma", "lihc", "hcc", "肝细胞肝癌", "肝细胞癌"),
        cbioportal_studies=("lihc_tcga_pan_can_atlas_2018",),
        cbioportal_prefixes=("lihc_",),
        gdc_projects=("TCGA-LIHC",),
        default_genes=("TP53", "CTNNB1", "TERT"),
        trial_condition="Carcinoma, Hepatocellular",
    ),
    CancerProfile(
        key="stomach_adenocarcinoma",
        canonical_name="Stomach Adenocarcinoma",
        label_zh="胃腺癌",
        aliases=("stomach adenocarcinoma", "gastric adenocarcinoma", "stomach cancer", "gastric cancer", "stad", "胃腺癌", "胃癌"),
        cbioportal_studies=("stad_tcga_pan_can_atlas_2018",),
        cbioportal_prefixes=("stad_",),
        gdc_projects=("TCGA-STAD",),
        default_genes=("TP53", "ERBB2", "CDH1"),
        trial_condition="Stomach Neoplasms",
    ),
    CancerProfile(
        key="pancreatic_adenocarcinoma",
        canonical_name="Pancreatic Adenocarcinoma",
        label_zh="胰腺腺癌",
        aliases=("pancreatic ductal adenocarcinoma", "pancreatic adenocarcinoma", "pancreatic cancer", "paad", "pdac", "胰腺导管腺癌", "胰腺腺癌", "胰腺癌"),
        cbioportal_studies=("paad_tcga_pan_can_atlas_2018",),
        cbioportal_prefixes=("paad_",),
        gdc_projects=("TCGA-PAAD",),
        default_genes=("KRAS", "TP53", "CDKN2A", "SMAD4"),
        trial_condition="Pancreatic Neoplasms",
    ),
    CancerProfile(
        key="ovarian_serous_cystadenocarcinoma",
        canonical_name="Ovarian Serous Cystadenocarcinoma",
        label_zh="卵巢浆液性癌",
        aliases=("ovarian serous cystadenocarcinoma", "high-grade serous ovarian cancer", "ovarian cancer", "hgsoc", "卵巢浆液性癌", "高级别浆液性卵巢癌", "卵巢癌"),
        cbioportal_studies=("ov_tcga_pan_can_atlas_2018",),
        cbioportal_prefixes=("ov_",),
        gdc_projects=("TCGA-OV",),
        default_genes=("TP53", "BRCA1", "BRCA2"),
        trial_condition="Ovarian Neoplasms",
    ),
    CancerProfile(
        key="kidney_renal_clear_cell_carcinoma",
        canonical_name="Kidney Renal Clear Cell Carcinoma",
        label_zh="肾透明细胞癌",
        aliases=("kidney renal clear cell carcinoma", "clear cell renal cell carcinoma", "kirc", "ccrcc", "肾透明细胞癌", "透明细胞肾细胞癌"),
        cbioportal_studies=("kirc_tcga_pan_can_atlas_2018",),
        cbioportal_prefixes=("kirc_",),
        gdc_projects=("TCGA-KIRC",),
        default_genes=("VHL", "PBRM1", "SETD2", "BAP1"),
        trial_condition="Carcinoma, Renal Cell",
    ),
    CancerProfile(
        key="bladder_urothelial_carcinoma",
        canonical_name="Bladder Urothelial Carcinoma",
        label_zh="膀胱尿路上皮癌",
        aliases=("bladder urothelial carcinoma", "urothelial bladder cancer", "bladder cancer", "blca", "膀胱尿路上皮癌", "膀胱癌"),
        cbioportal_studies=("blca_tcga_pan_can_atlas_2018",),
        cbioportal_prefixes=("blca_",),
        gdc_projects=("TCGA-BLCA",),
        default_genes=("TP53", "FGFR3", "RB1"),
        trial_condition="Urinary Bladder Neoplasms",
    ),
    CancerProfile(
        key="uterine_corpus_endometrial_carcinoma",
        canonical_name="Uterine Corpus Endometrial Carcinoma",
        label_zh="子宫内膜癌",
        aliases=("uterine corpus endometrial carcinoma", "endometrial cancer", "endometrial carcinoma", "ucec", "子宫内膜癌"),
        cbioportal_studies=("ucec_tcga_pan_can_atlas_2018",),
        cbioportal_prefixes=("ucec_",),
        gdc_projects=("TCGA-UCEC",),
        default_genes=("PTEN", "PIK3CA", "TP53", "ARID1A"),
        trial_condition="Endometrial Neoplasms",
    ),
    CancerProfile(
        key="head_and_neck_squamous_cell_carcinoma",
        canonical_name="Head and Neck Squamous Cell Carcinoma",
        label_zh="头颈鳞癌",
        aliases=("head and neck squamous cell carcinoma", "head and neck squamous carcinoma", "hnscc", "hnsc", "头颈鳞癌", "头颈部鳞状细胞癌"),
        cbioportal_studies=("hnsc_tcga_pan_can_atlas_2018",),
        cbioportal_prefixes=("hnsc_",),
        gdc_projects=("TCGA-HNSC",),
        default_genes=("TP53", "PIK3CA", "CDKN2A"),
        trial_condition="Head and Neck Neoplasms",
    ),
    CancerProfile(
        key="glioblastoma",
        canonical_name="Glioblastoma",
        label_zh="胶质母细胞瘤",
        aliases=("glioblastoma multiforme", "glioblastoma", "gbm", "胶质母细胞瘤"),
        cbioportal_studies=("gbm_tcga_pan_can_atlas_2018",),
        cbioportal_prefixes=("gbm_",),
        gdc_projects=("TCGA-GBM",),
        default_genes=("EGFR", "PTEN", "TP53", "IDH1"),
        trial_condition="Glioblastoma",
    ),
    CancerProfile(
        key="thyroid_carcinoma",
        canonical_name="Thyroid Carcinoma",
        label_zh="甲状腺癌",
        aliases=("thyroid carcinoma", "thyroid cancer", "thca", "甲状腺癌"),
        cbioportal_studies=("thca_tcga_pan_can_atlas_2018",),
        cbioportal_prefixes=("thca_",),
        gdc_projects=("TCGA-THCA",),
        default_genes=("BRAF", "NRAS", "RET"),
        trial_condition="Thyroid Neoplasms",
    ),
    CancerProfile(
        key="skin_cutaneous_melanoma",
        canonical_name="Skin Cutaneous Melanoma",
        label_zh="皮肤黑色素瘤",
        aliases=("skin cutaneous melanoma", "cutaneous melanoma", "skin melanoma", "skcm", "皮肤黑色素瘤", "黑色素瘤"),
        cbioportal_studies=("skcm_tcga_pan_can_atlas_2018",),
        cbioportal_prefixes=("skcm_",),
        gdc_projects=("TCGA-SKCM",),
        default_genes=("BRAF", "NRAS", "NF1"),
        trial_condition="Melanoma",
    ),
    CancerProfile(
        key="cervical_cancer",
        canonical_name="Cervical Cancer",
        label_zh="宫颈癌",
        aliases=("cervical squamous cell carcinoma", "cervical cancer", "cervical carcinoma", "cesc", "宫颈鳞癌", "宫颈癌"),
        cbioportal_studies=("cesc_tcga_pan_can_atlas_2018",),
        cbioportal_prefixes=("cesc_",),
        gdc_projects=("TCGA-CESC",),
        default_genes=("PIK3CA", "TP53", "PTEN"),
        trial_condition="Uterine Cervical Neoplasms",
    ),
    CancerProfile(
        key="esophageal_carcinoma",
        canonical_name="Esophageal Carcinoma",
        label_zh="食管癌",
        aliases=("esophageal carcinoma", "esophageal cancer", "esca", "食管癌", "食道癌"),
        cbioportal_studies=("esca_tcga_pan_can_atlas_2018",),
        cbioportal_prefixes=("esca_",),
        gdc_projects=("TCGA-ESCA",),
        default_genes=("TP53", "ERBB2", "CCND1"),
        trial_condition="Esophageal Neoplasms",
    ),
)


def resolve_cancer_profile(text: str | None) -> CancerProfile | None:
    folded = str(text or "").casefold()
    for profile in CANCER_PROFILES:
        terms = (
            profile.canonical_name,
            profile.label_zh,
            *profile.aliases,
            *profile.cbioportal_studies,
            *profile.gdc_projects,
        )
        if any(_contains_term(folded, term) for term in terms):
            return profile
    return None


def _contains_term(folded_text: str, term: str) -> bool:
    folded_term = term.casefold()
    if any("\u4e00" <= char <= "\u9fff" for char in folded_term):
        return folded_term in folded_text
    return re.search(
        rf"(?<![a-z0-9]){re.escape(folded_term)}(?![a-z0-9])",
        folded_text,
    ) is not None


def canonical_disease_name(text: str, *, title_case: bool = True) -> str:
    profile = resolve_cancer_profile(text)
    if profile is not None:
        return profile.canonical_name if title_case else profile.canonical_name.casefold()
    chinese = re.search(r"([\u4e00-\u9fff]{1,12}(?:癌|肿瘤))", text)
    if chinese:
        value = re.sub(r"^(?:研究|分析|探索|评估|比较|调查|关于|针对)+", "", chinese.group(1))
        return value or chinese.group(1)
    english = re.search(
        r"\b([A-Za-z][A-Za-z -]{1,40}?(?:cancer|carcinoma|sarcoma|neoplasm))\b",
        text,
        re.IGNORECASE,
    )
    if english:
        value = " ".join(english.group(1).split())
        return value.title() if title_case else value.casefold()
    return "Cancer" if title_case else "cancer"


def is_breast_cancer(text: str | None) -> bool:
    profile = resolve_cancer_profile(text)
    return profile is not None and profile.key == "breast_cancer"


def default_genes(text: str | None) -> list[str]:
    profile = resolve_cancer_profile(text)
    return list(profile.default_genes) if profile is not None else ["TP53"]


def default_cbioportal_study(text: str | None) -> str | None:
    profile = resolve_cancer_profile(text)
    return profile.cbioportal_studies[0] if profile and profile.cbioportal_studies else None


def default_gdc_project(text: str | None) -> str | None:
    profile = resolve_cancer_profile(text)
    return profile.gdc_projects[0] if profile and profile.gdc_projects else None


def trial_condition(text: str | None) -> str:
    profile = resolve_cancer_profile(text)
    return profile.trial_condition if profile is not None else str(text or "Cancer")


def is_cbioportal_study_for_disease(study_id: str, disease: str | None) -> bool:
    profile = resolve_cancer_profile(disease)
    normalized = study_id.strip().casefold()
    if profile is None or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,127}", normalized):
        return False
    return normalized in profile.cbioportal_studies or normalized.startswith(profile.cbioportal_prefixes)


def is_gdc_project_for_disease(project_id: str, disease: str | None) -> bool:
    profile = resolve_cancer_profile(disease)
    normalized = project_id.strip().upper()
    if profile is None or not re.fullmatch(r"[A-Z0-9][A-Z0-9_.-]{1,63}", normalized):
        return False
    return normalized in profile.gdc_projects


def disease_match_terms(text: str | None) -> tuple[str, ...]:
    profile = resolve_cancer_profile(text)
    if profile is None:
        value = str(text or "").strip()
        return (value,) if value else ()
    return tuple(dict.fromkeys((profile.canonical_name, profile.label_zh, *profile.aliases)))
