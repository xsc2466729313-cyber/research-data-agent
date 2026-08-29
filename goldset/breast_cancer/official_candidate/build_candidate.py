"""Write held-out official-candidate Gold Set CSVs for human review.

Never copies development question text or gold rows.
Never writes goldset/templates/.
Never marks rows approved or frozen.
If MANIFEST already records copied_to_templates, refuse to regenerate.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.app.evaluation.goldset import (  # noqa: E402
    REQUIRED_HEADERS,
    GoldSetCsvLoader,
    compute_gold_set_checksum,
)
from backend.app.evaluation.models import GoldSetManifest  # noqa: E402

LABEL = "official_candidate_draft_pending_xsc_review"
STATUS = "pending"
INITIAL_LABELER = "official-candidate-draft-builder"
INDEPENDENT_REVIEWER = "待 xsc 审核"
GOLD_SET_ID = "breast-cancer-official-candidate-20260829"
VERSION = "official-candidate-v0"
DRAFTED_AT = datetime(2026, 8, 29, 11, 53, tzinfo=timezone.utc)

RETRIEVAL_HEADERS = REQUIRED_HEADERS["retrieval_gold.csv"]
FIELD_HEADERS = REQUIRED_HEADERS["field_gold.csv"]
ERROR_HEADERS = REQUIRED_HEADERS["error_gold.csv"]


def _ret(qid: str, question: str, dataset_id: str, relevant: bool, notes: str) -> dict[str, str]:
    return {
        "question_id": qid,
        "research_question": question,
        "dataset_id": dataset_id,
        "label": "relevant" if relevant else "not_relevant",
        "label_source": LABEL,
        "review_status": STATUS,
        "notes": notes,
    }


def retrieval_rows() -> list[dict[str, str]]:
    q_chemo_pcr = (
        "只要新辅助化疗队列里按样本注释给出的患者级 pCR 或残余病灶标签"
        "（以化疗响应系列为主），不要把抗 HER2 靶向队列、细胞系筛药或知识库当成正例。"
    )
    q_her2_baseline = (
        "公开 GEO 系列中，HER2 阳性术前靶向治疗队列需要同时保留基线受体注释与术后病理响应；"
        "治疗后时间点不得当成另一名患者。"
    )
    q_pi3k = (
        "激素受体阳性乳腺癌接受 PI3K 抑制剂时，能否在同一患者记录上同时看到 PIK3CA 状态与临床响应？"
        "禁止把只有突变或只有表达响应的队列横向贴值。"
    )
    q_esr1 = (
        "需要患者级 ESR1/ER 状态与体细胞突变共存表，不要求治疗响应结局；"
        "细胞系与 CIViC 不得当患者表。"
    )
    q_ihc_cna = (
        "哪些公开队列可以同时提供 HER2 免疫组化类注释和 ERBB2 拷贝数，"
        "以便对照而不是合并成一个 her2_status？"
    )
    q_civic = (
        "查找 ERBB2 变异的文献级预测性证据，并明确这不是患者疗效表，也不是细胞系 AUC。"
    )
    q_nct = (
        "检索 ClinicalTrials.gov 上带公开结局测量的乳腺癌试验，必须落到具体 NCT；"
        "GEO 与 DepMap 不是试验登记主库。"
    )
    q_cell = (
        "乳腺癌细胞系对靶向药的 IC50 或 AUC 应来自 DepMap，且 response_domain 必须是 "
        "preclinical_cell_line；不得用患者 pCR 队列当正例。"
    )
    q_tnbc = (
        "用受体字段筛选三阴性乳腺癌的患者分子队列；"
        "HER2 靶向 GEO 系列和 DepMap 细胞系不是本题正例。"
    )
    q_scanb = (
        "SCAN-B 表达系列能否用于大规模转录组与临床特征关联？"
        "不要把它当成新辅助 pCR 专用试验或知识证据库。"
    )
    q_hr = (
        "激素受体阳性且 HER2 阴性的患者临床分层应使用含 ER/PR/HER2 临床字段的队列；"
        "以 HER2 阳性靶向治疗为主的 GEO 系列不得当本题主队列。"
    )

    pairs: list[tuple[str, str, list[tuple[str, bool, str]]]] = [
        (
            q_chemo_pcr,
            "oc01_chemo_pcr_annotation",
            [
                (
                    "GSE25066",
                    True,
                    "GEO 官方 GSE25066：新辅助化疗响应独立队列，样本注释含 pCR。"
                    "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE25066",
                ),
                (
                    "GSE76360",
                    False,
                    "该系列以 HER2 靶向术前治疗为主，不是本题要求的化疗响应主队列。",
                ),
                (
                    "brca_metabric",
                    False,
                    "有分子与生存，缺与本问匹配的新辅助化疗 pCR 同域结局。"
                    "https://www.cbioportal.org/study/summary?id=brca_metabric",
                ),
                ("DepMap", False, "细胞系药敏，response_domain 不同。"),
                ("CIViC", False, "知识证据库，不是患者级 pCR 注释。https://civicdb.org/"),
            ],
        ),
        (
            q_her2_baseline,
            "oc02_her2_neoadjuvant_baseline",
            [
                (
                    "GSE50948",
                    True,
                    "GEO 官方 GSE50948：HER2 阳性新辅助治疗与病理完全缓解公开系列。"
                    "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE50948",
                ),
                (
                    "GSE76360",
                    True,
                    "GEO 官方 GSE76360：HER2 靶向术前治疗，公开矩阵含基线/术后响应注释。"
                    "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE76360",
                ),
                (
                    "GSE25066",
                    False,
                    "新辅助化疗响应队列，不是抗 HER2 靶向术前治疗主系列。",
                ),
                ("DepMap", False, "非患者临床响应。"),
                ("brca_metabric", False, "缺匹配的抗 HER2 治疗响应结局。"),
            ],
        ),
        (
            q_pi3k,
            "oc03_pi3k_inhibitor_same_patient",
            [
                (
                    "breast_alpelisib_2020",
                    True,
                    "cBioPortal 同患者可含 PIK3CA 与治疗响应。"
                    "https://www.cbioportal.org/study/summary?id=breast_alpelisib_2020",
                ),
                (
                    "brca_mskcc_2019",
                    True,
                    "cBioPortal 同患者临床/分子候选。"
                    "https://www.cbioportal.org/study/summary?id=brca_mskcc_2019",
                ),
                (
                    "GSE76360",
                    False,
                    "有治疗响应，公开矩阵无 PIK3CA；不得跨库贴突变当正例。",
                ),
                ("brca_metabric", False, "有 PIK3CA，无匹配 PI3K 抑制剂治疗响应。"),
                ("CIViC", False, "知识证据不等于患者疗效。"),
            ],
        ),
        (
            q_esr1,
            "oc04_esr1_mutation_clinical_table",
            [
                (
                    "brca_metabric",
                    True,
                    "METABRIC 含 ER 临床状态与体细胞突变。"
                    "https://www.cbioportal.org/study/summary?id=brca_metabric",
                ),
                (
                    "TCGA-BRCA",
                    True,
                    "GDC/TCGA-BRCA 含突变与受体临床。"
                    "https://portal.gdc.cancer.gov/projects/TCGA-BRCA",
                ),
                ("GSE76360", False, "公开矩阵无体细胞突变表。"),
                ("DepMap", False, "细胞系，不是患者队列。"),
                ("CIViC", False, "知识证据层，不是患者共存表。"),
            ],
        ),
        (
            q_ihc_cna,
            "oc05_ihc_and_erbb2_cna_cohorts",
            [
                (
                    "TCGA-BRCA",
                    True,
                    "同时可能有 IHC 类临床与 ERBB2 CNA，必须分字段。"
                    "https://portal.gdc.cancer.gov/projects/TCGA-BRCA",
                ),
                ("brca_metabric", True, "临床 HER2 与分子拷贝数分开保存。"),
                (
                    "GSE76360",
                    False,
                    "公开矩阵侧重治疗响应与 IHC 类注释，不是 CNA 对照集。",
                ),
                ("CIViC", False, "知识证据不能替代 IHC/CNA 字段对照。"),
                ("DepMap", False, "细胞系拷贝数不是患者 IHC 对照金标准。"),
            ],
        ),
        (
            q_civic,
            "oc06_erbb2_knowledge_evidence",
            [
                (
                    "CIViC",
                    True,
                    "Variant–Drug–Disease 文献级证据。https://civicdb.org/",
                ),
                ("brca_metabric", False, "患者队列，不是文献证据库。"),
                ("GSE76360", False, "表达/临床队列，不是 CIViC 证据。"),
                ("DepMap", False, "细胞系筛药不是知识证据。"),
            ],
        ),
        (
            q_nct,
            "oc07_trial_outcome_measurements",
            [
                (
                    "NCT01104584",
                    True,
                    "ClinicalTrials.gov 官方 NCT01104584，项目 AACT 适配器用该编号验证公开结局测量。"
                    "https://clinicaltrials.gov/study/NCT01104584",
                ),
                (
                    "AACT",
                    True,
                    "ClinicalTrials.gov/AACT 聚合层，须落到具体 NCT。"
                    "https://aact.ctti-clinicaltrials.org/",
                ),
                ("GSE76360", False, "单中心 GEO 队列，不是试验登记主库。"),
                ("GSE25066", False, "GEO 表达/响应系列，不是 NCT 主库。"),
                ("DepMap", False, "非临床试验。"),
            ],
        ),
        (
            q_cell,
            "oc08_cell_line_ic50_auc",
            [
                (
                    "DepMap",
                    True,
                    "细胞系药敏；response_domain 必须是 preclinical_cell_line。"
                    "https://depmap.org/portal/",
                ),
                ("GSE76360", False, "患者治疗响应，不得与 IC50/AUC 混为正例。"),
                ("GSE25066", False, "患者 pCR 注释，不是细胞系筛药。"),
                ("CIViC", False, "知识证据，不是细胞系筛药表。"),
            ],
        ),
        (
            q_tnbc,
            "oc09_tnbc_receptor_screen",
            [
                (
                    "TCGA-BRCA",
                    True,
                    "可用受体状态筛选 TNBC 患者分子。"
                    "https://portal.gdc.cancer.gov/projects/TCGA-BRCA",
                ),
                ("brca_metabric", True, "含 ER/PR/HER2 临床，可筛 TNBC。"),
                (
                    "GSE76360",
                    False,
                    "该系列以 HER2 阳性靶向治疗为主，不是 TNBC 患者分子主队列。",
                ),
                ("DepMap", False, "细胞系不是患者 TNBC 队列。"),
            ],
        ),
        (
            q_scanb,
            "oc10_scanb_expression_clinical",
            [
                (
                    "GSE96058",
                    True,
                    "SCAN-B 大规模表达队列。"
                    "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE96058",
                ),
                ("GSE25066", False, "不是 SCAN-B。"),
                ("NCT01104584", False, "临床试验登记，不是表达队列。"),
                ("CIViC", False, "非表达队列。"),
            ],
        ),
        (
            q_hr,
            "oc11_hr_positive_her2_negative_strata",
            [
                ("brca_metabric", True, "含激素受体与 HER2 临床分层。"),
                ("TCGA-BRCA", True, "含受体临床字段。"),
                (
                    "GSE76360",
                    False,
                    "该测试队列以 HER2 阳性靶向治疗为主，不是 HR+/HER2- 主队列。",
                ),
                ("DepMap", False, "非患者。"),
            ],
        ),
    ]
    rows: list[dict[str, str]] = []
    for question, qid, items in pairs:
        for dataset_id, relevant, notes in items:
            rows.append(_ret(qid, question, dataset_id, relevant, notes))
    return rows


def field_rows() -> list[dict[str, str]]:
    def row(
        case_id: str,
        source: str,
        raw_field: str,
        raw_value: str,
        canonical_field: str,
        canonical_value: str,
        auto: bool,
        notes: str,
    ) -> dict[str, str]:
        return {
            "case_id": case_id,
            "source_dataset": source,
            "raw_field": raw_field,
            "raw_value": raw_value,
            "canonical_field": canonical_field,
            "canonical_value": canonical_value,
            "allowed_auto_transform": "true" if auto else "false",
            "label_source": LABEL,
            "review_status": STATUS,
            "notes": notes,
        }

    return [
        row(
            "oc_f01_ihc3_status",
            "GSE50948",
            "HER2 IHC",
            "3+",
            "her2_status",
            "Positive",
            True,
            "IHC 3+ 可映射 Positive；须同时保留 her2_assay=IHC 与 her2_raw_value=3+。",
        ),
        row(
            "oc_f02_ihc3_assay",
            "GSE50948",
            "HER2 IHC",
            "3+",
            "her2_assay",
            "IHC",
            True,
            "检测方法必须保留为 IHC。",
        ),
        row(
            "oc_f03_ihc3_raw",
            "GSE50948",
            "HER2 IHC",
            "3+",
            "her2_raw_value",
            "3+",
            True,
            "原始值不得丢弃。",
        ),
        row(
            "oc_f04_ihc2_equivocal",
            "brca_metabric",
            "HER2 IHC score",
            "2+",
            "her2_status",
            "Equivocal",
            False,
            "硬规则：IHC 2+ 不得自动判为 Positive，只能 Equivocal/REVIEW。",
        ),
        row(
            "oc_f05_ihc2_assay",
            "brca_metabric",
            "HER2 IHC score",
            "2+",
            "her2_assay",
            "IHC",
            True,
            "2+ 仍是 IHC 检测。",
        ),
        row(
            "oc_f06_ihc2_raw",
            "brca_metabric",
            "HER2 IHC score",
            "2+",
            "her2_raw_value",
            "2+",
            True,
            "必须留下 2+ 原文。",
        ),
        row(
            "oc_f07_ihc0_negative",
            "GSE25066",
            "her2",
            "0",
            "her2_status",
            "Negative",
            True,
            "IHC 0 → Negative；仍保留 assay 与 raw。",
        ),
        row(
            "oc_f08_fish_assay",
            "TCGA-BRCA",
            "her2_fish_result",
            "AMP",
            "her2_assay",
            "FISH",
            True,
            "assay=FISH，不得写成 IHC。",
        ),
        row(
            "oc_f09_fish_status",
            "TCGA-BRCA",
            "her2_fish_result",
            "AMP",
            "her2_status",
            "Positive",
            False,
            "FISH 扩增可支持 Positive，但属高风险，建议人工确认，不得与 IHC 2+ 混用。",
        ),
        row(
            "oc_f10_cna_gene",
            "brca_metabric",
            "ERBB2_CNA",
            "Amp",
            "gene",
            "ERBB2",
            True,
            "CNA 只证明基因是 ERBB2，不是 IHC。",
        ),
        row(
            "oc_f11_cna_not_ihc",
            "brca_metabric",
            "ERBB2_CNA",
            "Amp",
            "her2_status",
            "Unknown",
            False,
            "禁止把 CNA Amp 写成 HER2 Positive。",
        ),
        row(
            "oc_f12_er_pos",
            "GSE25066",
            "ER_status",
            "POS",
            "er_status",
            "Positive",
            True,
            "符号/缩写 POS → Positive。",
        ),
        row(
            "oc_f13_pr_neg",
            "TCGA-BRCA",
            "progesterone_receptor_status",
            "negative",
            "pr_status",
            "Negative",
            True,
            "PR 阴性大小写可自动。",
        ),
        row(
            "oc_f14_gene_alias",
            "CIViC",
            "gene_symbol",
            "HER-2",
            "gene",
            "ERBB2",
            True,
            "基因别名可自动（gene_alias_exact）。",
        ),
        row(
            "oc_f15_drug_perjeta",
            "NCT01104584",
            "intervention_name",
            "Perjeta",
            "drug",
            "pertuzumab",
            True,
            "药品别名可自动；须与该 NCT 公开干预字段核对。"
            "https://clinicaltrials.gov/study/NCT01104584",
        ),
        row(
            "oc_f16_pcr_value",
            "GSE25066",
            "pathologic_response",
            "pCR",
            "response",
            "pCR",
            True,
            "临床病理完全缓解。",
        ),
        row(
            "oc_f17_pcr_domain",
            "GSE25066",
            "pathologic_response",
            "pCR",
            "response_domain",
            "clinical",
            True,
            "患者结局必须是 clinical。",
        ),
        row(
            "oc_f18_ic50_domain",
            "DepMap",
            "IC50",
            "0.15",
            "response_domain",
            "preclinical_cell_line",
            True,
            "细胞系药敏域；IC50 数值仅为字段映射示例。",
        ),
        row(
            "oc_f19_ic50_not_pcr",
            "DepMap",
            "IC50",
            "0.15",
            "response",
            "IC50",
            False,
            "不得写成患者 pCR。",
        ),
        row(
            "oc_f20_scanb_source",
            "GSE96058",
            "geo_accession",
            "GSE96058",
            "source_id",
            "geo:GSE96058",
            True,
            "必须有真实 source_id。"
            "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE96058",
        ),
        row(
            "oc_f21_patient_id",
            "GSE25066",
            "subject",
            "PT001",
            "patient_id",
            "PT001",
            False,
            "示例身份字段，非声称真实患者编号；低置信时不得跨库对齐。",
        ),
        row(
            "oc_f22_sample_id",
            "GSE50948",
            "sample_name",
            "GSM_pre_A",
            "sample_id",
            "GSM_pre_A",
            False,
            "示例样本 ID，不与其他研究同号合并。",
        ),
        row(
            "oc_f23_civic_domain",
            "CIViC",
            "evidence_direction",
            "Predictive",
            "response_domain",
            "knowledge_evidence",
            True,
            "知识证据层。",
        ),
        row(
            "oc_f24_er_unknown",
            "TCGA-BRCA",
            "er_ihc",
            "unknown",
            "er_status",
            "Unknown",
            True,
            "unknown 不得当成 Negative。",
        ),
        row(
            "oc_f25_residual",
            "GSE50948",
            "surgery_response",
            "residual disease",
            "response",
            "residual_disease",
            False,
            "残余病灶写法需核对原始注释，建议审核。",
        ),
        row(
            "oc_f26_nct_source",
            "NCT01104584",
            "nct_id",
            "NCT01104584",
            "source_id",
            "nct:NCT01104584",
            True,
            "试验必须落到真实 NCT。"
            "https://clinicaltrials.gov/study/NCT01104584",
        ),
    ]


def error_rows() -> list[dict[str, str]]:
    def row(
        case_id: str,
        error_type: str,
        record: dict[str, object],
        detect: bool,
        repair: str,
        auto: bool,
        risk: str,
        notes: str,
    ) -> dict[str, str]:
        return {
            "case_id": case_id,
            "error_type": error_type,
            "original_record": json.dumps(record, ensure_ascii=False, separators=(",", ":")),
            "expected_detection": "true" if detect else "false",
            "expected_repair": repair,
            "auto_repair_allowed": "true" if auto else "false",
            "risk_level": risk,
            "review_status": STATUS,
            "notes": notes,
        }

    return [
        row(
            "oc_e01_ihc2_to_positive",
            "her2_assay_error",
            {
                "source_id": "cbioportal:brca_metabric",
                "raw_field": "HER2 IHC score",
                "raw_value": "2+",
                "her2_status": "Positive",
            },
            True,
            "her2_status=Equivocal; her2_assay=IHC; her2_raw_value=2+; 进入 REVIEW",
            False,
            "high",
            "不得把 IHC 2+ 自动改成 Positive。",
        ),
        row(
            "oc_e02_cna_as_ihc",
            "her2_assay_error",
            {
                "source_id": "cbioportal:brca_metabric",
                "raw_field": "ERBB2_CNA",
                "raw_value": "Amp",
                "her2_status": "Positive",
            },
            True,
            "撤销 her2_status=Positive；保留 gene=ERBB2 与 CNA 原始值",
            False,
            "high",
            "ERBB2 CNA ≠ HER2 IHC 阳性。",
        ),
        row(
            "oc_e03_ic50_as_pcr",
            "schema_mapping_error",
            {
                "source_id": "depmap:BRCA",
                "IC50": 0.15,
                "response": "pCR",
                "response_domain": "clinical",
            },
            True,
            "response_domain=preclinical_cell_line；清除患者 pCR 解释",
            False,
            "high",
            "细胞系 IC50/AUC 不得解释为患者 pCR。",
        ),
        row(
            "oc_e04_low_conf_merge",
            "patient_sample_conflict",
            {
                "patient_id": "PT001",
                "sample_id": "GSM_pre_A",
                "match_score": 0.35,
                "decision": "AUTO_MERGE",
            },
            True,
            "unresolved",
            False,
            "high",
            "低置信关联不得自动合并。",
        ),
        row(
            "oc_e05_cross_study_id",
            "patient_sample_conflict",
            {
                "left": "geo:GSE25066:PT001",
                "right": "cbioportal:brca_metabric:PT001",
                "action": "merge_as_same_patient",
            },
            True,
            "unresolved；禁止合并",
            False,
            "high",
            "跨研究同号不得当同一患者。",
        ),
        row(
            "oc_e06_gene_alias",
            "gene_alias",
            {"gene": "HER-2", "source_id": "civic:evidence-7316"},
            True,
            '{"gene":"ERBB2"}',
            True,
            "low",
            "基因别名可自动。",
        ),
        row(
            "oc_e07_drug_alias",
            "drug_alias",
            {"drug": "Perjeta", "source_id": "nct:NCT01104584"},
            True,
            '{"drug":"pertuzumab"}',
            True,
            "low",
            "药品别名可自动。",
        ),
        row(
            "oc_e08_duplicate",
            "duplicate",
            {
                "patient_id": "PT001",
                "sample_id": "S-chemo-1",
                "source_id": "geo:GSE25066",
                "rows": 2,
            },
            True,
            "保留一条并记审计；不删原始备份",
            True,
            "low",
            "同研究完全重复可自动去重。",
        ),
        row(
            "oc_e09_missing_source",
            "provenance_missing",
            {
                "her2_status": "Positive",
                "source_id": "",
                "raw_field": "",
                "raw_value": "",
            },
            True,
            "阻断发布；补 source_id 与 raw_* 或删除该关键字段",
            False,
            "high",
            "无 Evidence 不得正式发布。",
        ),
        row(
            "oc_e10_join_without_crosswalk",
            "patient_sample_conflict",
            {
                "left": "GSE25066",
                "right": "TCGA-BRCA",
                "join": "patient_id",
            },
            True,
            "FORBIDDEN_PATIENT_JOIN",
            False,
            "high",
            "无 crosswalk 禁止患者级 Join。",
        ),
        row(
            "oc_e11_clean_ihc3",
            "her2_assay_error",
            {
                "source_id": "geo:GSE50948",
                "raw_field": "HER2 IHC",
                "raw_value": "3+",
                "her2_status": "Positive",
                "her2_assay": "IHC",
            },
            False,
            "",
            False,
            "low",
            "对照：IHC 3+ → Positive 且保留 assay，不应报 her2 错。",
        ),
        row(
            "oc_e12_clean_er",
            "schema_mapping_error",
            {
                "source_id": "geo:GSE25066",
                "raw_field": "ER_status",
                "raw_value": "POS",
                "er_status": "Positive",
            },
            False,
            "",
            False,
            "low",
            "对照：ER 标准化正确。",
        ),
        row(
            "oc_e13_missing_response",
            "missing",
            {
                "source_id": "cbioportal:brca_metabric",
                "required": "response",
                "response": "",
            },
            True,
            "不填假 pCR；标记字段缺失并换队列或 REVIEW",
            False,
            "medium",
            "METABRIC 缺治疗响应时不得编造结局。",
        ),
        row(
            "oc_e14_unknown_to_negative",
            "schema_mapping_error",
            {
                "er_status": "Negative",
                "raw_value": "unknown",
                "source_id": "gdc:TCGA-BRCA",
            },
            True,
            "er_status=Unknown",
            False,
            "medium",
            "unknown/NA 不得当成 Negative。",
        ),
        row(
            "oc_e15_authority_conflict",
            "schema_mapping_error",
            {
                "source_a": "IHC 3+",
                "source_b": "FISH negative",
                "picked": "Positive",
                "source_id": "mixed:TCGA-BRCA",
            },
            True,
            "不自动选边；记录冲突并 REVIEW",
            False,
            "high",
            "高权威来源冲突不得自动选边。",
        ),
        row(
            "oc_e16_empty_raw",
            "provenance_missing",
            {
                "her2_status": "Positive",
                "source_id": "geo:GSE50948",
                "raw_value": "",
            },
            True,
            "缺 raw_value 则关键字段不可发布",
            False,
            "high",
            "有 source 但无原始值仍不算完整 Evidence。",
        ),
        row(
            "oc_e17_clean_drug",
            "drug_alias",
            {"drug": "pertuzumab", "source_id": "nct:NCT01104584"},
            False,
            "",
            False,
            "low",
            "对照：已是标准药名，不应再报错。",
        ),
        row(
            "oc_e18_domain_blank",
            "schema_mapping_error",
            {
                "response": "IC50",
                "response_domain": "",
                "source_id": "depmap:BRCA",
            },
            True,
            "response_domain=preclinical_cell_line",
            False,
            "medium",
            "细胞系药敏必须补 preclinical_cell_line 域。",
        ),
    ]


def write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def draft_manifest(checksum: str, row_counts: dict[str, int]) -> dict[str, object]:
    return {
        "split": "official_candidate",
        "not_frozen_test": True,
        "copied_to_templates": False,
        "frozen": False,
        "official_sdti_entrypoint": (
            "goldset/templates remains empty; dashboard official SDTI stays NOT_EVALUATED"
        ),
        "notice": (
            "Held-out official-candidate draft for xsc review. "
            "Not frozen_test. Not copied to templates. "
            "Do not copy development-split observations into the official dashboard column."
        ),
        "row_counts": row_counts,
        "manifest": {
            "gold_set_id": GOLD_SET_ID,
            "version": VERSION,
            "frozen": False,
            "frozen_at": DRAFTED_AT.isoformat().replace("+00:00", "Z"),
            "initial_labeler": INITIAL_LABELER,
            "independent_reviewer": INDEPENDENT_REVIEWER,
            "deterministic_rules_verified": False,
            "source_references_verified": False,
            "high_risk_review_complete": False,
            "human_reviewer": None,
            "gold_set_checksum": checksum,
        },
    }


def main() -> None:
    manifest_path = ROOT / "MANIFEST.json"
    if manifest_path.is_file():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if payload.get("copied_to_templates") is True:
            raise SystemExit(
                "Official candidate has already been written to goldset/templates. "
                "Do not regenerate CSVs from build_candidate.py."
            )
    retrieval = retrieval_rows()
    fields = field_rows()
    errors = error_rows()
    write_csv(ROOT / "retrieval_gold.csv", RETRIEVAL_HEADERS, retrieval)
    write_csv(ROOT / "field_gold.csv", FIELD_HEADERS, fields)
    write_csv(ROOT / "error_gold.csv", ERROR_HEADERS, errors)

    placeholder = GoldSetManifest(
        gold_set_id=GOLD_SET_ID,
        version=VERSION,
        frozen=False,
        frozen_at=DRAFTED_AT,
        initial_labeler=INITIAL_LABELER,
        independent_reviewer=INDEPENDENT_REVIEWER,
        deterministic_rules_verified=False,
        source_references_verified=False,
        high_risk_review_complete=False,
        gold_set_checksum="0" * 64,
    )
    bundle = GoldSetCsvLoader().load(ROOT, placeholder)
    checksum = compute_gold_set_checksum(bundle)
    row_counts = {
        "retrieval_gold.csv": len(bundle.retrieval_gold),
        "field_gold.csv": len(bundle.field_gold),
        "error_gold.csv": len(bundle.error_gold),
    }
    payload = draft_manifest(checksum, row_counts)
    (ROOT / "MANIFEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"directory": str(ROOT), **row_counts, "checksum": checksum, "frozen": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
