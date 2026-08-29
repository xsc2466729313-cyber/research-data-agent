"""Write development Gold Set CSVs for human review. Never marks rows approved or frozen."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LABEL = "official_accession_draft_pending_human_review"
STATUS = "pending"

RETRIEVAL_HEADERS = [
    "question_id",
    "research_question",
    "dataset_id",
    "label",
    "label_source",
    "review_status",
    "notes",
]
FIELD_HEADERS = [
    "case_id",
    "source_dataset",
    "raw_field",
    "raw_value",
    "canonical_field",
    "canonical_value",
    "allowed_auto_transform",
    "label_source",
    "review_status",
    "notes",
]
ERROR_HEADERS = [
    "case_id",
    "error_type",
    "original_record",
    "expected_detection",
    "expected_repair",
    "auto_repair_allowed",
    "risk_level",
    "review_status",
    "notes",
]


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
    q_pcr = "哪些因素会影响乳腺癌新辅助治疗后的病理完全缓解（pCR）？需要患者级临床结局。"
    q_her2_resp = "整理 HER2 阳性乳腺癌术前抗 HER2 治疗的患者级治疗响应队列。"
    q_pik3ca_pcr = "研究 HER2 阳性或激素受体阳性乳腺癌中 PIK3CA 突变与治疗响应的关系，要求同一患者同时有突变和临床响应。"
    q_pik3ca_only = "整理乳腺癌患者的 PIK3CA 突变与临床特征，不要求治疗响应结局。"
    q_erbb2 = "整理乳腺癌患者的 ERBB2/HER2 相关临床特征、拷贝数或突变信息。"
    q_civic = "检索乳腺癌中 PIK3CA 变异与药物治疗的文献级证据，并与患者队列区分。"
    q_trial = "查找乳腺癌新辅助治疗相关的登记临床试验（NCT）。"
    q_cell = "整理乳腺癌细胞系对靶向药物的药敏（AUC/IC50），不得当作患者疗效。"
    q_tnbc = "三阴性乳腺癌患者的临床与分子特征整理。"
    q_hr = "HR 阳性 / HER2 阴性乳腺癌的临床特征与分子队列。"
    q_ihc_cna = "区分 HER2 IHC 结果与 ERBB2 拷贝数扩增，二者不得当成同一字段。"
    q_scanb = "SCAN-B 大规模乳腺癌表达队列能否支持临床特征整理？"

    rows: list[dict[str, str]] = []
    pairs = [
        (q_pcr, "q01_neoadjuvant_pcr", [
            ("GSE76360", True, "GEO 官方 GSE76360：HER2 靶向术前治疗，含术后响应注释。https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE76360"),
            ("GSE25066", True, "GEO 官方 GSE25066：新辅助化疗响应独立队列。https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE25066"),
            ("brca_metabric", False, "METABRIC 有分子与生存，缺与本问匹配的新辅助 pCR 同域结局，不得当正例。https://www.cbioportal.org/study/summary?id=brca_metabric"),
            ("TCGA-BRCA", False, "TCGA-BRCA 主为综合基因组与基线临床，不是新辅助 pCR 专用队列。https://portal.gdc.cancer.gov/projects/TCGA-BRCA"),
            ("CIViC", False, "知识证据库，不是患者级 pCR 队列。https://civicdb.org/"),
            ("DepMap", False, "细胞系药敏，response_domain 不同。"),
        ]),
        (q_her2_resp, "q02_her2_targeted_response", [
            ("GSE76360", True, "公开 Series Matrix 可解析 HER2 队列与治疗响应。"),
            ("GSE25066", True, "新辅助化疗响应，可作为独立临床响应来源，但是否抗 HER2 需按样本注释核对。"),
            ("breast_alpelisib_2020", True, "cBioPortal 同患者可含分子与治疗响应。https://www.cbioportal.org/study/summary?id=breast_alpelisib_2020"),
            ("brca_metabric", False, "缺匹配的抗 HER2 治疗响应结局。"),
            ("DepMap", False, "非患者临床响应。"),
        ]),
        (q_pik3ca_pcr, "q03_pik3ca_and_response_same_patient", [
            ("breast_alpelisib_2020", True, "同患者可同时有 PIK3CA 与治疗响应，禁止用别的队列贴突变。"),
            ("brca_mskcc_2019", True, "cBioPortal 同患者临床/分子候选。https://www.cbioportal.org/study/summary?id=brca_mskcc_2019"),
            ("GSE76360", False, "有治疗响应，公开矩阵无 PIK3CA；相关但不足以回答「同患者双变量」。标负例防止跨库贴值。"),
            ("brca_metabric", False, "有 PIK3CA，无匹配治疗响应，不得当正例。"),
            ("CIViC", False, "知识证据不等于患者疗效。"),
        ]),
        (q_pik3ca_only, "q04_pik3ca_clinical_features", [
            ("brca_metabric", True, "METABRIC 含 PIK3CA 等体细胞突变与临床。"),
            ("TCGA-BRCA", True, "GDC/TCGA-BRCA 含突变与临床。"),
            ("brca_mskcc_2019", True, "MSK 乳腺癌队列含突变。"),
            ("GSE76360", False, "公开矩阵无 PIK3CA。"),
            ("DepMap", False, "细胞系，不是患者队列。"),
        ]),
        (q_erbb2, "q05_erbb2_her2_features", [
            ("TCGA-BRCA", True, "含 ERBB2 拷贝数/突变，须与 IHC 分列。"),
            ("brca_metabric", True, "含 HER2 临床状态与分子。"),
            ("GSE76360", True, "样本注释含 HER2 相关临床，不是 CNA 金标准。"),
            ("CIViC", True, "ERBB2 变异的知识证据，response_domain=knowledge_evidence。"),
            ("DepMap", False, "本题要患者/临床特征，不是细胞系药敏。"),
        ]),
        (q_civic, "q06_pik3ca_knowledge_evidence", [
            ("CIViC", True, "Variant–Drug–Disease 证据。https://civicdb.org/"),
            ("brca_metabric", False, "患者队列，不是文献证据库。"),
            ("GSE76360", False, "表达/临床队列，不是 CIViC 证据。"),
            ("TCGA-BRCA", False, "基因组队列，不是知识证据层。"),
        ]),
        (q_trial, "q07_neoadjuvant_trials", [
            ("NCT01042379", True, "I-SPY2 新辅助登记试验。https://clinicaltrials.gov/study/NCT01042379"),
            ("AACT", True, "ClinicalTrials.gov/AACT 聚合层，须落到具体 NCT。"),
            ("GSE76360", False, "单中心 GEO 队列，不是试验登记主库。"),
            ("DepMap", False, "非临床试验。"),
        ]),
        (q_cell, "q08_cell_line_drug_response", [
            ("DepMap", True, "细胞系药敏；response_domain 必须是 preclinical_cell_line。"),
            ("GSE76360", False, "患者治疗响应，不得与 AUC/IC50 混为正例。"),
            ("brca_metabric", False, "患者队列。"),
            ("CIViC", False, "知识证据，不是细胞系筛药表。"),
        ]),
        (q_tnbc, "q09_tnbc", [
            ("TCGA-BRCA", True, "可用受体状态筛选 TNBC 临床/分子。"),
            ("brca_metabric", True, "含 ER/PR/HER2 临床，可筛 TNBC。"),
            ("GSE25066", True, "新辅助队列含受体注释时可用于 TNBC 亚组，以样本注释为准。"),
            ("DepMap", False, "细胞系不是患者 TNBC 队列。"),
        ]),
        (q_hr, "q10_hr_positive_her2_negative", [
            ("brca_metabric", True, "含激素受体与 HER2 临床分层。"),
            ("TCGA-BRCA", True, "含受体临床字段。"),
            ("GSE76360", False, "该测试队列以 HER2 阳性靶向治疗为主，不是 HR+/HER2- 主队列。"),
            ("DepMap", False, "非患者。"),
        ]),
        (q_ihc_cna, "q11_her2_ihc_vs_erbb2_cna", [
            ("TCGA-BRCA", True, "同时可能有 IHC 临床与 ERBB2 CNA，必须分字段。"),
            ("brca_metabric", True, "临床 HER2 与分子分开保存。"),
            ("GSE76360", False, "公开矩阵侧重治疗响应与 IHC 类注释，不是 CNA 对照集。"),
            ("CIViC", False, "知识证据不能替代 IHC/CNA 字段对齐金标准。"),
        ]),
        (q_scanb, "q12_scanb_expression", [
            ("GSE96058", True, "SCAN-B 表达队列。https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE96058"),
            ("GSE76360", False, "不是 SCAN-B。"),
            ("CIViC", False, "非表达队列。"),
        ]),
    ]
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
        row("f01_ihc3_positive", "GSE76360", "her2_ihc", "3+", "her2_status", "Positive", True, "IHC 3+ 可映射 Positive；须同时保留 her2_assay=IHC 与 her2_raw_value=3+。"),
        row("f02_ihc3_assay", "GSE76360", "her2_ihc", "3+", "her2_assay", "IHC", True, "检测方法必须保留为 IHC。"),
        row("f03_ihc3_raw", "GSE76360", "her2_ihc", "3+", "her2_raw_value", "3+", True, "原始值不得丢弃。"),
        row("f04_ihc2_equivocal", "GSE76360", "her2_ihc", "2+", "her2_status", "Equivocal", False, "硬规则：IHC 2+ 不得自动判为 Positive，只能 Equivocal/REVIEW。"),
        row("f05_ihc2_assay", "GSE76360", "her2_ihc", "2+", "her2_assay", "IHC", True, "2+ 仍是 IHC 检测。"),
        row("f06_ihc2_raw", "GSE76360", "her2_ihc", "2+", "her2_raw_value", "2+", True, "必须留下 2+ 原文。"),
        row("f07_ihc1_negative", "brca_metabric", "HER2_IHC", "1+", "her2_status", "Negative", True, "IHC 0/1+ 通常为 Negative；仍保留 assay 与 raw。"),
        row("f08_ihc0_negative", "brca_metabric", "HER2 IHC", "0", "her2_status", "Negative", True, "IHC 0 → Negative。"),
        row("f09_fish_amp", "TCGA-BRCA", "HER2_FISH", "amplified", "her2_status", "Positive", False, "FISH 扩增可支持 Positive，但属高风险，建议人工确认，不得与 IHC 2+ 混用。"),
        row("f10_fish_assay", "TCGA-BRCA", "HER2_FISH", "amplified", "her2_assay", "FISH", True, "assay=FISH。"),
        row("f11_cna_gene", "TCGA-BRCA", "ERBB2_CNA", "amplification", "gene", "ERBB2", True, "CNA 只证明基因是 ERBB2，不是 IHC。"),
        row("f12_cna_not_ihc", "TCGA-BRCA", "ERBB2_CNA", "amplification", "her2_status", "Unknown", False, "禁止把 CNA amplification 写成 HER2 Positive。"),
        row("f13_er_pos", "GSE76360", "er status", "positive", "er_status", "Positive", True, "大小写/同义可自动。"),
        row("f14_er_plus", "GSE25066", "ER", "+", "er_status", "Positive", True, "符号 + → Positive。"),
        row("f15_er_cn", "brca_metabric", "ER", "阳性", "er_status", "Positive", True, "中文阳性。"),
        row("f16_pr_neg", "GSE76360", "pr status", "negative", "pr_status", "Negative", True, "PR 阴性。"),
        row("f17_gene_her2", "CIViC", "gene", "HER2", "gene", "ERBB2", True, "基因别名可自动，medical_rules.auto_fix.gene_alias_exact。"),
        row("f18_gene_pik3ca", "brca_metabric", "Hugo_Symbol", "PIK3CA", "gene", "PIK3CA", True, "已是标准符号。"),
        row("f19_mut_pik3ca", "brca_metabric", "Mutation_Status", "Mutated", "mutation_status", "Mutated", True, "突变状态。"),
        row("f20_drug_herceptin", "NCT01042379", "intervention", "Herceptin", "drug", "trastuzumab", True, "药品别名可自动。"),
        row("f21_pcr_yes", "GSE25066", "pCR", "yes", "response", "pCR", True, "临床病理完全缓解。"),
        row("f22_pcr_domain", "GSE25066", "pCR", "yes", "response_domain", "clinical", True, "患者结局必须是 clinical。"),
        row("f23_rd", "GSE76360", "response at surgery", "RD", "response", "residual_disease", False, "残余病灶写法需核对原始注释，建议审核。"),
        row("f24_auc_domain", "DepMap", "AUC", "0.42", "response_domain", "preclinical_cell_line", True, "细胞系药敏域。"),
        row("f25_auc_not_pcr", "DepMap", "AUC", "0.42", "response", "AUC", False, "不得写成患者 pCR。"),
        row("f26_disease", "TCGA-BRCA", "primary_diagnosis", "Breast Invasive Carcinoma", "disease", "breast cancer", True, "疾病归一。"),
        row("f27_source", "GSE76360", "geo_accession", "GSE76360", "source_id", "geo:GSE76360", True, "必须有真实 source_id。"),
        row("f28_patient", "GSE76360", "subject id", "P1", "patient_id", "P1", False, "身份字段低置信时不得跨库对齐。"),
        row("f29_sample", "GSE76360", "sample", "GSM_baseline_1", "sample_id", "GSM_baseline_1", False, "样本 ID 保留，不与其他研究同号合并。"),
        row("f30_her2_pos_text", "brca_metabric", "HER2_STATUS", "Positive", "her2_status", "Positive", True, "来源已给临床 HER2 Positive，仍建议核对 assay。"),
        row("f31_unknown_er", "TCGA-BRCA", "er_status", "NA", "er_status", "Unknown", True, "缺失记号 → Unknown，不是 Negative。"),
        row("f32_civic_domain", "CIViC", "evidence_type", "Predictive", "response_domain", "knowledge_evidence", True, "知识证据层。"),
        row("f33_stage", "TCGA-BRCA", "ajcc_pathologic_stage", "Stage IIA", "stage", "IIA", True, "分期压缩为 IIA。"),
        row("f34_treatment", "GSE76360", "treatment", "trastuzumab + chemotherapy", "treatment", "trastuzumab + chemotherapy", True, "治疗方案原文可规范化空格，不改药名语义。"),
        row("f35_subtype_her2", "GSE76360", "HER2_cohort", "HER2-positive", "subtype", "HER2-positive", True, "亚型。"),
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
            "e01_ihc2_to_positive",
            "her2_assay_error",
            {"source_id": "geo:GSE76360", "raw_field": "her2_ihc", "raw_value": "2+", "her2_status": "Positive"},
            True,
            "her2_status=Equivocal; her2_assay=IHC; her2_raw_value=2+; 进入 REVIEW",
            False,
            "high",
            "不得把 IHC 2+ 自动改成 Positive。",
        ),
        row(
            "e02_cna_as_ihc",
            "her2_assay_error",
            {"source_id": "gdc:TCGA-BRCA", "raw_field": "ERBB2_CNA", "raw_value": "amplification", "her2_status": "Positive"},
            True,
            "撤销 her2_status=Positive；保留 gene=ERBB2 与 CNA 原始值",
            False,
            "high",
            "CNA 扩增 ≠ IHC 阳性。",
        ),
        row(
            "e03_cross_study_id",
            "patient_sample_conflict",
            {"left": "geo:GSE76360:P1", "right": "cbioportal:brca_metabric:P1", "action": "merge_as_same_patient"},
            True,
            "unresolved；禁止合并",
            False,
            "high",
            "跨研究同号不得当同一患者。",
        ),
        row(
            "e04_auc_as_pcr",
            "schema_mapping_error",
            {"source_id": "depmap:BRCA", "AUC": 0.4, "response": "pCR", "response_domain": "clinical"},
            True,
            "response_domain=preclinical_cell_line；清除患者 pCR 解释",
            False,
            "high",
            "细胞系药敏不得解释为患者 pCR。",
        ),
        row(
            "e05_missing_source",
            "provenance_missing",
            {"her2_status": "Positive", "source_id": "", "raw_field": "", "raw_value": ""},
            True,
            "阻断发布；补 source_id 与 raw_* 或删除该关键字段",
            False,
            "high",
            "无 Evidence 不得正式发布。",
        ),
        row(
            "e06_gene_alias",
            "gene_alias",
            {"gene": "HER2", "source_id": "civic:1"},
            True,
            '{"gene":"ERBB2"}',
            True,
            "low",
            "基因别名可自动。",
        ),
        row(
            "e07_drug_alias",
            "drug_alias",
            {"drug": "Herceptin", "source_id": "nct:NCT01042379"},
            True,
            '{"drug":"trastuzumab"}',
            True,
            "low",
            "药品别名可自动。",
        ),
        row(
            "e08_duplicate",
            "duplicate",
            {"patient_id": "P1", "sample_id": "S1", "source_id": "geo:GSE76360", "rows": 2},
            True,
            "保留一条并记审计；不删原始备份",
            True,
            "low",
            "同研究完全重复可自动去重。",
        ),
        row(
            "e09_missing_pcr",
            "missing",
            {"source_id": "cbioportal:brca_metabric", "required": "response", "response": ""},
            True,
            "不填假 pCR；标记字段缺失并换队列或 REVIEW",
            False,
            "medium",
            "METABRIC 缺治疗响应时不得编造结局。",
        ),
        row(
            "e10_unit",
            "unit",
            {"age": "0.52", "unit_guess": "years", "source_id": "gdc:TCGA-BRCA"},
            True,
            "按来源单位核验；不确定则 REVIEW",
            False,
            "medium",
            "年龄单位不明不得瞎转。",
        ),
        row(
            "e11_low_conf_link",
            "patient_sample_conflict",
            {"patient_id": "A", "sample_id": "B", "match_score": 0.4, "decision": "AUTO_MERGE"},
            True,
            "unresolved",
            False,
            "high",
            "低置信关联不得自动合并。",
        ),
        row(
            "e12_clean_ihc3",
            "her2_assay_error",
            {"source_id": "geo:GSE76360", "raw_field": "her2_ihc", "raw_value": "3+", "her2_status": "Positive", "her2_assay": "IHC"},
            False,
            "",
            False,
            "low",
            "对照：IHC 3+ → Positive 且保留 assay/raw，不应报 her2 错。",
        ),
        row(
            "e13_clean_er",
            "schema_mapping_error",
            {"source_id": "geo:GSE76360", "raw_field": "er status", "raw_value": "positive", "er_status": "Positive"},
            False,
            "",
            False,
            "low",
            "对照：ER 标准化正确。",
        ),
        row(
            "e14_typo_stage",
            "typo",
            {"stage": "Stge IIA", "source_id": "gdc:TCGA-BRCA"},
            True,
            "stage=IIA",
            False,
            "medium",
            "拼写错误可提议，分期属临床字段，建议审核后应用。",
        ),
        row(
            "e15_authority_conflict",
            "schema_mapping_error",
            {"source_a": "IHC 3+", "source_b": "FISH negative", "picked": "Positive", "source_id": "mixed"},
            True,
            "不自动选边；记录冲突并 REVIEW",
            False,
            "high",
            "高权威来源冲突不得自动选边。",
        ),
        row(
            "e16_join_without_crosswalk",
            "patient_sample_conflict",
            {"left": "GSE76360", "right": "brca_metabric", "join": "patient_id"},
            True,
            "FORBIDDEN_PATIENT_JOIN",
            False,
            "high",
            "无 crosswalk 禁止患者级 Join。",
        ),
        row(
            "e17_empty_her2_publish",
            "provenance_missing",
            {"her2_status": "Positive", "source_id": "geo:GSE76360", "raw_value": ""},
            True,
            "缺 raw_value 则关键字段不可发布",
            False,
            "high",
            "有 source 但无原始值仍不算完整 Evidence。",
        ),
        row(
            "e18_pr_pos_alias",
            "gene_alias",
            {"gene": "PgR", "source_id": "cbioportal:brca_metabric"},
            True,
            '{"gene":"PGR"}',
            True,
            "low",
            "PgR → PGR 可自动。",
        ),
        row(
            "e19_response_domain_blank",
            "schema_mapping_error",
            {"response": "pCR", "response_domain": "", "source_id": "geo:GSE25066"},
            True,
            "response_domain=clinical",
            False,
            "medium",
            "有患者结局必须补 clinical 域。",
        ),
        row(
            "e20_clean_alias_done",
            "drug_alias",
            {"drug": "trastuzumab", "source_id": "nct:NCT01042379"},
            False,
            "",
            False,
            "low",
            "对照：已是标准药名，不应再报错。",
        ),
        row(
            "e21_sample_timepoint_leak",
            "duplicate",
            {"patient_id": "P1", "timepoint": ["baseline", "post"], "stacked_as_two_analysis_rows": True, "source_id": "geo:GSE76360"},
            True,
            "分析集只保留基线或按研究设计显式分表，避免治疗后行泄漏",
            False,
            "medium",
            "配对时间点不是重复身份，但不得当两个独立患者。",
        ),
        row(
            "e22_unknown_to_negative",
            "schema_mapping_error",
            {"er_status": "Negative", "raw_value": "NA", "source_id": "gdc:TCGA-BRCA"},
            True,
            "er_status=Unknown",
            False,
            "medium",
            "NA 不得当成 Negative。",
        ),
    ]


def write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    manifest_path = ROOT / "MANIFEST.json"
    if manifest_path.is_file():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if payload.get("manifest", {}).get("frozen") is True:
            raise SystemExit(
                "Development Gold Set is already frozen. Do not regenerate CSVs "
                "from build_draft.py."
            )
    retrieval = retrieval_rows()
    fields = field_rows()
    errors = error_rows()
    write_csv(ROOT / "retrieval_gold.csv", RETRIEVAL_HEADERS, retrieval)
    write_csv(ROOT / "field_gold.csv", FIELD_HEADERS, fields)
    write_csv(ROOT / "error_gold.csv", ERROR_HEADERS, errors)
    print(
        json.dumps(
            {
                "directory": str(ROOT),
                "retrieval_rows": len(retrieval),
                "field_rows": len(fields),
                "error_rows": len(errors),
                "review_status": STATUS,
                "frozen": False,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
