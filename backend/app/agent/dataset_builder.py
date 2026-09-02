from __future__ import annotations

import csv
import gzip
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from backend.app.agent.accession_harvest import (
    asks_pcr,
    asks_survival,
    asks_treatment,
    geo_text_has_clinical_cohort,
    geo_text_is_preclinical,
    is_tnbc_question,
    needs_clinical_outcome,
)
from backend.app.agent.match_scoring import outcome_match_rate, requested_gene_coverage
from backend.app.agent.models import (
    AnalysisReadinessReport,
    DatasetColumn,
    ModelingDataset,
)
from backend.app.models import ResearchSpec
from backend.app.oncology import resolve_cancer_profile
from backend.app.sources.cbioportal.models import CBioPortalAdapterResult
from backend.app.sources.depmap.models import DepMapAdapterResult
from backend.app.sources.geo.models import GEOAdapterResult, GEOResourceType


PROJECT_ROOT = Path(__file__).resolve().parents[3]

CHINESE_LABELS = {
    "study_id": "研究编号",
    "patient_id": "患者编号",
    "sample_id": "样本编号",
    "source_id": "来源编号",
    "sample_title": "样本名称",
    "disease": "疾病",
    "age": "年龄",
    "sex": "性别",
    "stage": "肿瘤分期",
    "grade": "肿瘤分级",
    "er_status": "ER 状态",
    "pr_status": "PR 状态",
    "her2_status": "HER2 状态",
    "subtype": "疾病亚型",
    "treatment": "治疗方案",
    "experimental_group": "实验分组",
    "experimental_response": "实验响应",
    "os_status": "总生存状态",
    "os_months": "总生存时间（月）",
    "dfs_status": "无病生存状态",
    "dfs_months": "无病生存时间（月）",
    "pcr": "病理完全缓解",
    "treatment_response": "术后治疗响应",
    "response_domain": "响应数据域",
    "timepoint": "取样时间点",
    "sample_timepoint": "样本时间点",
    "sample_source": "样本来源",
    "raw_characteristics": "原始样本特征",
    "breast_surgery": "乳腺手术方式",
    "cancer_type": "癌症类型",
    "cancer_type_detailed": "癌症详细类型",
    "cellularity": "肿瘤细胞密度",
    "chemotherapy": "是否接受化疗",
    "claudin_subtype": "Claudin 分子亚型",
    "cohort": "队列批次",
    "er_ihc": "ER 免疫组化结果",
    "her2_snp6": "HER2 拷贝数状态（SNP6）",
    "histological_subtype": "组织学亚型",
    "hormone_therapy": "是否接受内分泌治疗",
    "endocrine_therapy": "内分泌治疗",
    "measurable_disease": "可测量病灶",
    "weeks_on_study": "在研周数",
    "inferred_menopausal_state": "推定绝经状态",
    "intclust": "整合聚类亚型",
    "laterality": "肿瘤侧别",
    "lymph_nodes_examined_positive": "阳性淋巴结数",
    "mutation_count": "突变总数",
    "npi": "诺丁汉预后指数（NPI）",
    "oncotree_code": "OncoTree 肿瘤分类代码",
    "radio_therapy": "是否接受放射治疗",
    "sample_count": "样本数量",
    "sample_type": "样本类型",
    "threegene": "三基因分型",
    "tmb_nonsynonymous": "非同义肿瘤突变负荷",
    "tumor_size": "肿瘤大小",
    "vital_status": "生存状态",
    "derived_ihc_subtype": "免疫组化亚型（同队列派生）",
    "pcr_binary": "病理完全缓解（二值派生）",
    "age_group": "年龄分组（同队列派生）",
    "brca_any_mutation": "BRCA1/2 任一突变（同队列派生）",
}

FIELD_DESCRIPTIONS = {
    "study_id": "公开数据库中的研究或队列编号；用于定位研究，不参与统计分析。",
    "patient_id": "来源研究内的患者标识；用于去重、配对和按患者分组切分。",
    "sample_id": "来源研究内的样本标识；用于连接临床、表达和分子记录。",
    "source_id": "系统登记的可追溯来源编号，可在数据溯源区找到官方地址与校验值。",
    "sample_title": "GEO 提交者给出的样本名称，用于核对基线与治疗后配对样本。",
    "disease": "研究对象的疾病或队列人群。",
    "age": "诊断或入组时年龄；具体时间点以原研究数据字典为准。",
    "sex": "患者生物学性别。",
    "stage": "原研究记录的肿瘤分期；不同版本分期系统不可直接混用。",
    "grade": "病理学肿瘤分级。",
    "er_status": "雌激素受体状态；阳性/阴性来自原研究样本特征。",
    "pr_status": "孕激素受体状态；阳性/阴性来自原研究样本特征。",
    "her2_status": "临床 HER2 状态；IHC 2+ 不会被自动判为阳性。",
    "subtype": "疾病亚型；由同一样本的 HER2/患者状态字段解析，不从其他研究推断。",
    "treatment": "该样本所属研究记录的治疗方案；研究级统一方案会标注来源，不跨患者贴值。",
    "experimental_group": "细胞系或动物实验中的扰动/对照分组；不得解释为患者治疗方案。",
    "experimental_response": "前临床实验记录的响应；不得解释为患者临床疗效。",
    "os_status": "随访截止时总生存结局状态。",
    "os_months": "从原研究定义的起点到死亡或末次随访的月数。",
    "dfs_status": "无病生存事件状态。",
    "dfs_months": "从原研究定义的起点到复发/事件或末次随访的月数。",
    "pcr": "术后病理完全缓解结局；应按原研究对 pCR 的定义解释。",
    "treatment_response": "术后疗效分组；GSE76360 中 pCR=病理完全缓解、OBJR=客观缓解、NOR=未达客观缓解。",
    "response_domain": "区分患者临床响应、临床试验响应和细胞系药敏，防止不同结局混用。",
    "timepoint": "样本采集相对治疗的时间点；本主分析表保留基线样本以避免配对泄漏。",
    "sample_timepoint": "标准化样本采集时间点；优先来自原始样本特征，不对缺失时间点做推断。",
    "sample_source": "样本取材部位或来源；仅保留原始样本字段，不用疾病名称代替样本来源。",
    "raw_characteristics": "GEO Series Matrix 中逐项保留的原始 characteristics 文本，供审计与复核。",
    "breast_surgery": "患者接受的乳腺手术方式。",
    "cancer_type": "上游数据库的癌种大类。",
    "cancer_type_detailed": "更细粒度的组织学或疾病类型。",
    "cellularity": "病理评估的肿瘤细胞含量分级。",
    "chemotherapy": "是否记录为接受过化疗。",
    "claudin_subtype": "基于表达特征得到的 Claudin 分子亚型。",
    "cohort": "原研究中的病例队列或批次。",
    "er_ihc": "ER 免疫组化检测结果。",
    "her2_snp6": "SNP6 推断的 ERBB2/HER2 拷贝数状态，不等同临床 IHC 阳性。",
    "histological_subtype": "乳腺癌组织学亚型。",
    "hormone_therapy": "是否接受过内分泌治疗。",
    "endocrine_therapy": "原研究记录的内分泌治疗药物或方案；不等于 ER 免疫组化状态。",
    "measurable_disease": "原研究记录的可测量病灶状态。",
    "weeks_on_study": "患者在该研究中的随访或用药周数。",
    "inferred_menopausal_state": "原研究推定的绝经状态。",
    "intclust": "METABRIC 整合聚类分子亚型。",
    "laterality": "原发肿瘤位于左侧或右侧乳腺。",
    "lymph_nodes_examined_positive": "检查淋巴结中阳性的数量。",
    "mutation_count": "该样本记录的体细胞突变总数。",
    "npi": "诺丁汉预后指数，由肿瘤大小、分级和淋巴结状态组合。",
    "oncotree_code": "OncoTree 标准癌种编码。",
    "radio_therapy": "是否接受过放射治疗。",
    "sample_count": "患者对应的样本数量。",
    "sample_type": "原发、转移或其他样本类型。",
    "threegene": "原研究提供的三基因分型结果。",
    "tmb_nonsynonymous": "每兆碱基非同义体细胞突变负荷。",
    "tumor_size": "原发肿瘤大小；单位以原研究数据字典为准。",
    "vital_status": "末次随访时患者生存状态。",
    "derived_ihc_subtype": "由同一行 ER/PR/HER2 临床字段组合；HER2 IHC 2+ 不自动判阳，ERBB2 CNA 不参与该字段。",
    "pcr_binary": "由同队列 pCR/治疗响应文本映射的二值标记；不用生存结局冒充 pCR。",
    "age_group": "由同队列年龄切分的分组，未发布年龄时不生成。",
    "brca_any_mutation": "同一行 BRCA1 或 BRCA2 突变为 1 则记为 1；拷贝数不计入该字段。",
}

ATTRIBUTE_ALIASES = {
    "AGE_AT_DIAGNOSIS": "age",
    "AGE": "age",
    "SEX": "sex",
    "GENDER": "sex",
    "TUMOR_STAGE": "stage",
    "AJCC_PATHOLOGIC_TUMOR_STAGE": "stage",
    "STAGE": "stage",
    "TUMOR_GRADE": "grade",
    "GRADE": "grade",
    "ER_STATUS": "er_status",
    "PR_STATUS": "pr_status",
    "ENDOCRINE_THERAPY": "endocrine_therapy",
    "MEASURABLE_DISEASE": "measurable_disease",
    "WEEKS_ON_STUDY": "weeks_on_study",
    "HER2_STATUS": "her2_status",
    "HER2_IHC": "her2_status",
    "IHC_HER2": "her2_status",
    "HER2_IHC_SCORE": "her2_status",
    "HER2_STATUS_IHC": "her2_status",
    "OS_STATUS": "os_status",
    "OS_MONTHS": "os_months",
    "OS": "os_status",
    "OVERALL_SURVIVAL": "os_months",
    "OVERALL_SURVIVAL_MONTHS": "os_months",
    "DFS_STATUS": "dfs_status",
    "DFS_MONTHS": "dfs_months",
    "DFS": "dfs_status",
    "RFS_STATUS": "dfs_status",
    "RFS_MONTHS": "dfs_months",
    "RFS": "dfs_status",
    "DISEASE_FREE_SURVIVAL": "dfs_months",
    "DISEASE_FREE_SURVIVAL_MONTHS": "dfs_months",
    "DSS_STATUS": "dss_status",
    "DSS_MONTHS": "dss_months",
    "DSS": "dss_status",
    "DISEASE_SPECIFIC_SURVIVAL": "dss_months",
    "VITAL_STATUS": "vital_status",
    "PCR": "pcr",
    "PCR_RESPONSE": "pcr",
    "PCR_STATUS": "pcr",
    "PATHOLOGIC_COMPLETE_RESPONSE": "pcr",
    "TREATMENT_RESPONSE": "treatment_response",
    "RESPONSE": "treatment_response",
    "RECIST_RESPONSE": "treatment_response",
    "TREATMENT_BEST_RESPONSE": "treatment_response",
    "BEST_RESPONSE_TO_THERAPY": "treatment_response",
    "CLINICAL_BENEFIT": "treatment_response",
    "BEST_RESPONSE": "treatment_response",
    "TREATMENT_ARM": "treatment",
    "BREAST_CANCER_SUBTYPE": "subtype",
    "SAMPLE_COLLECTION_TIMEPOINT": "sample_timepoint",
    "CANCER_TYPE": "disease",
    "PIK3CA_MUT_PRE_TREATMENT_TUMOR": "pik3ca_mutation",
    "PIK3CA_PRE_TREATMENT_TUMOR": "pik3ca_mutation",
    "PIK3CA_MUTATION": "pik3ca_mutation",
    "PIK3CA_STATUS": "pik3ca_mutation",
    "SAMPLE_TYPE": "sample_type",
    "SAMPLE_TYPE_DETAILED": "sample_type_detailed",
    "TISSUE_TYPE": "tissue_type",
    "SPECIMEN_TYPE": "specimen_type",
    "SAMPLE_SOURCE": "sample_source",
    "TISSUE_SOURCE": "tissue_source",
    "TISSUE_SOURCE_SITE": "tissue_source_site",
    "SPECIMEN_SOURCE": "specimen_source",
    "SAMPLE_ORIGIN": "sample_origin",
    "SAMPLE_TIMEPOINT": "sample_timepoint",
    "COLLECTION_TIMEPOINT": "collection_timepoint",
    "INTCLUST": "intclust",
    "INT_CLUST": "intclust",
    "INTEGRATIVE_CLUSTER": "intclust",
    "CLAUDIN_SUBTYPE": "claudin_subtype",
}

VALUE_NORMALIZATION = {
    "YES": "是",
    "Y": "是",
    "TRUE": "是",
    "NO": "否",
    "N": "否",
    "FALSE": "否",
    "POS": "阳性",
    "POSITIVE": "阳性",
    "POSITVE": "阳性",
    "NEG": "阴性",
    "NEGATIVE": "阴性",
    "MALE": "男性",
    "FEMALE": "女性",
    "MASTECTOMY": "乳房切除术",
    "BREAST CONSERVING": "保乳手术",
    "BREAST CANCER": "乳腺癌",
    "HER2+ BREAST CANCER": "HER2 阳性乳腺癌",
    "BREAST INVASIVE DUCTAL CARCINOMA": "乳腺浸润性导管癌",
    "BREAST INVASIVE LOBULAR CARCINOMA": "乳腺浸润性小叶癌",
    "BREAST MIXED DUCTAL AND LOBULAR CARCINOMA": "乳腺混合性导管-小叶癌",
    "HIGH": "高",
    "MODERATE": "中",
    "LOW": "低",
    "BASELINE": "基线",
    "PRE": "基线",
    "PRE-TREATMENT": "基线",
    "PRETREATMENT": "基线",
    "PRE_TREATMENT": "基线",
    "BEFORE TREATMENT": "基线",
    "T0": "基线",
    "DIAGNOSIS": "基线",
    "POST": "治疗后",
    "POST-TREATMENT": "治疗后",
    "POSTTREATMENT": "治疗后",
    "ON-TREATMENT": "治疗后",
    "AFTER TREATMENT": "治疗后",
    "PCR": "病理完全缓解（pCR）",
    "RD": "未达客观缓解",
    "OBJR": "客观缓解",
    "NOR": "未达客观缓解",
    "0:LIVING": "生存",
    "1:DECEASED": "死亡",
}

DATASET_NAMES = {
    "brca_metabric": "乳腺癌 METABRIC 临床与分子队列",
    "GSE76360": "HER2 阳性乳腺癌术前曲妥珠单抗响应队列",
    "GSE25066": "乳腺癌新辅助化疗响应与生存队列",
    "GSE50948": "HER2 阳性乳腺癌新辅助治疗病理完全缓解队列",
    "breast_alpelisib_2020": "PIK3CA 突变乳腺癌 Alpelisib 治疗响应队列",
    "brca_mskcc_2019": "MSK 乳腺癌突变与治疗响应队列",
}

# Same-study protocol fields. Applied only when the accession is a curated
# uniform-treatment cohort and the patient row still lacks that column.
GEO_COHORT_PROTOCOL: dict[str, dict[str, str]] = {
    "GSE76360": {
        "treatment": "曲妥珠单抗新辅助治疗",
        "sample_type": "原发肿瘤",
        "sample_source": "乳腺肿瘤穿刺活检",
    },
    "GSE50948": {
        "sample_type": "原发肿瘤",
        "sample_source": "乳腺肿瘤组织",
    },
}

# GEO Series Matrix local names → canonical analysis fields.
GEO_FIELD_SYNONYMS: dict[str, tuple[str, ...]] = {
    "treatment_response": (
        "response_at_surgery",
        "treatment_response",
        "response",
        "pcr",
        "pcr_status",
        "pathological_complete_response",
        "pathologic_complete_response",
        "pathologic_response",
        "clinical_response",
        "trastuzumab_response",
        "herceptin_response",
        "neoadjuvant_response",
        "chemo_response",
        "chemotherapy_response",
        "residual_cancer_burden",
        "rcb_class",
        "miller_payne",
        "pathologic_response_pcr_rd",
        "pcr_rd",
        "pcr_vs_rd",
    ),
            "pcr": (
                "pcr",
                "pcr_status",
                "pcr_yes_no",
                "pathological_complete_response",
                "pathologic_complete_response",
                "pathologic_response",
                "pathologic_response_pcr_rd",
                "pcr_rd",
                "pcr_vs_rd",
                "residual_disease_pcr",
            ),
    "disease": ("patient_status", "disease", "diagnosis", "cancer_type", "disease_state"),
    "treatment": (
        "treatment",
        "therapy",
        "neoadjuvant_treatment",
        "neoadjuvant_therapy",
        "drug",
        "regimen",
        "treatment_protocol",
        "her2_therapy",
    ),
    "sample_type": ("sample_type", "sample_type_detailed", "tissue_type", "specimen_type"),
    "sample_source": (
        "sample_source",
        "tissue_source_site",
        "tissue_source",
        "specimen_source",
        "sample_origin",
        "organ",
        "tissue",
        "biopsy_site",
    ),
    "sample_timepoint": (
        "sample_timepoint",
        "timepoint",
        "time_point",
        "collection_timepoint",
        "sampling_timepoint",
        "treatment_timepoint",
    ),
    "her2_status": (
        "her2_status",
        "her2",
        "her2_ihc",
        "erbb2_status",
        "her2_status_ihc",
        "her2_ihc_status",
        "her2_ihc_score",
        "ihc_her2",
    ),
    "er_status": ("er_status", "er", "estrogen_receptor", "er_status_ihc", "er_ihc"),
    "pr_status": ("pr_status", "pr", "progesterone_receptor", "pr_status_ihc", "pr_ihc"),
    "subtype": ("subtype", "molecular_subtype", "breast_cancer_subtype"),
    "stage": ("stage", "tumor_stage", "ajcc_stage"),
    "age": ("age", "age_at_diagnosis", "age_years"),
}

GEO_SAMPLE_METADATA_KEYS = {
    "title": "sample_title",
    "geo_accession": "geo_accession",
    "source_name_ch1": "source_name",
    "source_name_ch2": "source_name",
    "organism_ch1": "organism",
    "description": "sample_description",
}

_CHARACTERISTIC_SPLIT = re.compile(r"\s*;\s*|\s*\|\s*")
_PCR_FIELD_NAMES = {
    "pcr",
    "pcr_status",
    "pathological_complete_response",
    "pathologic_complete_response",
    "pathologic_response_pcr_rd",
    "pcr_rd",
    "pcr_vs_rd",
    "residual_disease_pcr",
}


class ResearchDatasetBuilder:
    """Build audited research tables without changing the frozen canonical schema."""

    def empty(self) -> tuple[ModelingDataset, AnalysisReadinessReport]:
        dataset = ModelingDataset(
            name="尚未形成可用科研数据集",
            unit_of_analysis="患者/样本",
            columns=[],
            rows=[],
            row_count=0,
            patient_count=0,
            sample_count=0,
        )
        report = AnalysisReadinessReport(
            status="数据不足",
            analysis_ready=False,
            row_count=0,
            feature_count=0,
            split_strategy="获得患者级数据后按患者编号分组，避免同一患者跨分析分区。",
            warnings=["当前工具结果不包含可构建患者/样本级宽表的记录。"],
            recommendations=["优先调用含研究结局的患者队列；知识证据和试验目录不能替代患者数据。"],
        )
        return dataset, report

    def build_from_depmap(
        self,
        result: DepMapAdapterResult,
        spec: ResearchSpec,
    ) -> tuple[ModelingDataset, AnalysisReadinessReport]:
        blob = f"{spec.research_goal} {' '.join(spec.outcomes)}".casefold()
        cell_line_question = any(
            token in blob for token in ("细胞系", "auc", "ic50", "depmap", "ccle", "药敏")
        )
        rows = []
        for record in result.records:
            rows.append(
                {
                    "study_id": "DepMap",
                    "sample_id": record.model_id,
                    "cell_line_id": record.model_id,
                    "cell_line_name": record.cell_line_name,
                    "disease": spec.disease,
                    "drug": record.drug,
                    "auc": record.auc,
                    "ic50": record.ic50,
                    "response_domain": "preclinical_cell_line",
                    "source_id": record.source_id,
                    "raw_field": "DepMap.Model",
                    "raw_value": record.cell_line_name,
                }
            )
        columns = [
            DatasetColumn(name="study_id", label_zh="研究编号", data_type="string", role="id", description="DepMap"),
            DatasetColumn(name="cell_line_id", label_zh="细胞系编号", data_type="string", role="id", description="DepMap ModelID"),
            DatasetColumn(name="cell_line_name", label_zh="细胞系名称", data_type="string", role="feature", description="细胞系"),
            DatasetColumn(name="drug", label_zh="药物", data_type="string", role="exposure", description="药敏药物"),
            DatasetColumn(name="auc", label_zh="AUC", data_type="number", role="outcome", description="细胞系药敏 AUC"),
            DatasetColumn(name="ic50", label_zh="IC50", data_type="number", role="outcome", description="细胞系药敏 IC50"),
            DatasetColumn(
                name="response_domain",
                label_zh="响应域",
                data_type="string",
                role="guard",
                description="固定 preclinical_cell_line",
            ),
            DatasetColumn(name="source_id", label_zh="来源编号", data_type="string", role="audit", description="DepMap"),
            DatasetColumn(name="raw_field", label_zh="原始字段", data_type="string", role="audit", description="原始字段"),
            DatasetColumn(name="raw_value", label_zh="原始值", data_type="string", role="audit", description="原始值"),
        ]
        cancer_profile = resolve_cancer_profile(spec.disease)
        disease_label = cancer_profile.label_zh if cancer_profile is not None else spec.disease
        dataset = ModelingDataset(
            name=f"DepMap {disease_label}细胞系药敏",
            unit_of_analysis="细胞系",
            columns=columns,
            rows=rows,
            row_count=len(rows),
            patient_count=0,
            sample_count=len(rows),
            target_column="auc" if cell_line_question else None,
            study_key="DepMap",
        )
        warnings = ["response_domain=preclinical_cell_line；AUC/IC50 不得解释为患者 pCR 或临床疗效。"]
        recommendations = ["细胞系药敏与患者队列必须分表保留，禁止混域合并。"]
        if not cell_line_question:
            warnings.append("本题主目标是患者/样本队列；DepMap 仅作为前临床对照表。")
        report = AnalysisReadinessReport(
            status="可分析" if cell_line_question and len(rows) >= 8 else "领域隔离",
            analysis_ready=bool(cell_line_question and len(rows) >= 8),
            row_count=len(rows),
            feature_count=len(columns),
            target_column=dataset.target_column,
            target_match=cell_line_question,
            target_match_rate=1.0 if cell_line_question and rows else 0.0,
            field_completeness_rate=1.0 if rows else 0.0,
            split_strategy="按细胞系编号划分；不得与患者编号对齐。",
            warnings=warnings,
            recommendations=recommendations,
        )
        return dataset, report

    def build_from_cbioportal(
        self,
        result: CBioPortalAdapterResult,
        spec: ResearchSpec,
    ) -> tuple[ModelingDataset, AnalysisReadinessReport]:
        tables = {table.table_name: table for table in result.tables}
        entity_rows: dict[tuple[str, str], dict[str, Any]] = {}
        patient_values: dict[str, dict[str, Any]] = defaultdict(dict)
        cleaned_values = 0
        orphan_records = 0
        source_id = result.source_items[0].source_id if result.source_items else f"cbioportal:{result.study.study_id}"

        patient_table = tables.get("clinical_patient")
        for raw in patient_table.rows if patient_table else []:
            patient_id = str(raw.get("patientId") or "").strip()
            attribute = self._normalize_attribute(raw.get("clinicalAttributeId"))
            if patient_id and attribute:
                value, changed = self._clean_value(raw.get("value"))
                patient_values[patient_id][attribute] = value
                cleaned_values += int(changed)

        sample_table = tables.get("clinical_sample")
        sample_rows = sample_table.rows if sample_table else []
        for raw in sample_rows:
            patient_id = str(raw.get("patientId") or "").strip()
            # A patient identifier is not a sample identifier. Keep the sample
            # field missing when the upstream sample table does not provide one.
            sample_id = str(raw.get("sampleId") or "").strip()
            if not patient_id and not sample_id:
                continue
            key = (patient_id or sample_id, sample_id)
            row = entity_rows.setdefault(
                key,
                {
                    "study_id": result.study.study_id,
                    "patient_id": patient_id or None,
                    "sample_id": sample_id or None,
                    "source_id": source_id,
                },
            )
            attribute = self._normalize_attribute(raw.get("clinicalAttributeId"))
            if attribute:
                value, changed = self._clean_value(raw.get("value"))
                row[attribute] = value
                cleaned_values += int(changed)

        # Clinical samples are the cohort anchor. Patient-only rows are created only
        # when no sample table exists; this prevents mutation-only samples from
        # inflating the cohort and producing artificial missingness.
        if entity_rows:
            for patient_id, attributes in patient_values.items():
                for key in (key for key in entity_rows if key[0] == patient_id):
                    entity_rows[key].update(attributes)
        else:
            for patient_id, attributes in patient_values.items():
                entity_rows[(patient_id, patient_id)] = {
                    "study_id": result.study.study_id,
                    "patient_id": patient_id,
                    "sample_id": None,
                    "source_id": source_id,
                    **attributes,
                }

        by_sample = {key[1]: key for key in entity_rows}
        by_patient: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for key in entity_rows:
            by_patient[key[0]].append(key)

        mutation_genes: set[str] = set()
        mutation_table = tables.get("mutations")
        for raw in mutation_table.rows if mutation_table else []:
            gene = self._extract_gene(raw)
            key = self._match_entity(raw, by_sample, by_patient)
            if not gene or key is None:
                orphan_records += int(gene is not None)
                continue
            mutation_genes.add(gene)
            row = entity_rows[key]
            row[f"{gene.lower()}_mutation"] = 1
            protein = str(raw.get("proteinChange") or "").strip()
            if protein:
                variants = row.setdefault(f"{gene.lower()}_variants", [])
                if protein not in variants:
                    variants.append(protein)

        cna_table = tables.get("discrete_cna")
        for raw in cna_table.rows if cna_table else []:
            gene = self._extract_gene(raw)
            key = self._match_entity(raw, by_sample, by_patient)
            if not gene or key is None:
                orphan_records += int(gene is not None)
                continue
            entity_rows[key][f"{gene.lower()}_cna"] = raw.get("alteration")

        rows = list(entity_rows.values())
        for row in rows:
            for gene in mutation_genes:
                row.setdefault(f"{gene.lower()}_mutation", 0)
                variants = row.get(f"{gene.lower()}_variants")
                if isinstance(variants, list):
                    row[f"{gene.lower()}_variants"] = ";".join(variants)
        rows, subtype_action = self._filter_rows_for_research_spec(rows, spec)
        rows, alias_actions = self._materialize_canonical_fields(rows, spec, result.study.study_id)
        rows, derive_actions = self._derive_same_cohort_fields(rows, spec)

        cleaning_actions = [
            "以临床样本表作为队列锚点，未把无临床信息的分子记录扩成新患者。",
            "将缺失哨兵统一为空值，并统一常见中英文分类值。",
            "同一患者的临床属性传播到其样本，但不跨患者补值。",
        ]
        if subtype_action:
            cleaning_actions.append(subtype_action)
        cleaning_actions.extend(alias_actions)
        cleaning_actions.extend(derive_actions)
        if orphan_records:
            cleaning_actions.append(f"排除 {orphan_records} 条无法连接到临床队列的分子记录。")
        dataset = self._dataset_from_rows(
            rows,
            name=f"{DATASET_NAMES.get(result.study.study_id, result.study.study_id)}科研数据集",
            unit="样本（同一患者可能包含多个样本）",
            spec=spec,
        )
        report = self._readiness(
            dataset,
            spec,
            tables=tables,
            cleaned_value_count=cleaned_values,
            excluded_orphan_record_count=orphan_records,
            cleaning_actions=cleaning_actions,
        )
        return dataset, report

    def build_from_geo(
        self,
        result: GEOAdapterResult,
        spec: ResearchSpec,
    ) -> tuple[ModelingDataset, AnalysisReadinessReport] | None:
        resource = next(
            (
                item
                for item in result.resources
                if item.resource_type == GEOResourceType.SERIES_MATRIX
                and item.source_item.local_path
            ),
            None,
        )
        if resource is None:
            return None
        path = Path(resource.source_item.local_path or "")
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.is_file():
            return None

        sample_data: dict[str, list[str]] = {}
        series_metadata: list[str] = []
        characteristics: list[list[str]] = []
        try:
            with gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="") as handle:
                for line in handle:
                    if line.startswith("!series_matrix_table_begin"):
                        break
                    if line.startswith("!Series_"):
                        fields = next(csv.reader([line.rstrip("\r\n")], delimiter="\t"))
                        series_metadata.extend(value for value in fields[1:] if value)
                        continue
                    if not line.startswith("!Sample_"):
                        continue
                    fields = next(csv.reader([line.rstrip("\r\n")], delimiter="\t"))
                    if len(fields) < 2:
                        continue
                    key = fields[0].removeprefix("!Sample_").strip()
                    values = fields[1:]
                    if key.startswith("characteristics_ch"):
                        characteristics.append(values)
                    elif key in GEO_SAMPLE_METADATA_KEYS:
                        sample_data[key] = values
        except (OSError, EOFError, csv.Error):
            return None

        accessions = sample_data.get("geo_accession", [])
        titles = sample_data.get("title", [])
        source_names = sample_data.get("source_name_ch1") or sample_data.get("source_name_ch2") or []
        if not accessions:
            return None
        series_context = " ".join(series_metadata)
        series_is_preclinical = geo_text_is_preclinical(series_context)
        rows: list[dict[str, Any]] = []
        cleaned_values = 0
        for index, sample_id in enumerate(accessions):
            raw_items = [values[index] for values in characteristics if index < len(values)]
            parsed, changed = self._parse_geo_characteristics(raw_items)
            cleaned_values += changed
            source_name, source_changed = self._clean_value(
                source_names[index] if index < len(source_names) else None
            )
            cleaned_values += int(source_changed)
            if self._has_filled(source_name) and not self._has_filled(parsed.get("source_name")):
                parsed["source_name"] = source_name
            subject = str(
                parsed.get("subject_id")
                or parsed.get("patid")
                or parsed.get("patient_id")
                or parsed.get("case_id")
                or ""
            ).strip()
            treatment_response = self._geo_mapped_value(parsed, "treatment_response")
            treatment = self._geo_mapped_value(parsed, "treatment")
            row_context = " ".join(
                [
                    series_context,
                    titles[index] if index < len(titles) else "",
                    str(source_name or ""),
                    " ".join(raw_items),
                ]
            )
            preclinical = series_is_preclinical or geo_text_is_preclinical(row_context)
            clinical = not preclinical and bool(subject or geo_text_has_clinical_cohort(row_context))
            response_domain = "preclinical_cell_line" if preclinical else "clinical" if clinical else None
            cell_line = parsed.get("cell_line") or parsed.get("cell_line_name")
            sample_type = self._geo_mapped_value(parsed, "sample_type") or self._infer_sample_type(
                source_name or parsed.get("source_name") or parsed.get("tissue")
            )
            sample_source = self._geo_mapped_value(parsed, "sample_source") or source_name
            if preclinical:
                sample_type = "细胞系" if self._has_filled(cell_line) else "前临床实验样本"
                sample_source = cell_line or sample_source
            row = {
                "study_id": result.accession,
                "patient_id": f"{result.accession}-{subject}" if subject and not preclinical else None,
                "sample_id": sample_id,
                "source_id": resource.source_item.source_id,
                "sample_title": titles[index] if index < len(titles) else None,
                "disease": self._geo_mapped_value(parsed, "disease"),
                "timepoint": self._geo_mapped_value(parsed, "sample_timepoint"),
                "sample_timepoint": self._geo_mapped_value(parsed, "sample_timepoint"),
                "sample_type": sample_type,
                "sample_source": sample_source,
                "treatment_response": None if preclinical else treatment_response,
                "experimental_response": treatment_response if preclinical else None,
                "pcr": None if preclinical else self._geo_mapped_value(parsed, "pcr"),
                "er_status": self._geo_mapped_value(parsed, "er_status"),
                "pr_status": self._geo_mapped_value(parsed, "pr_status"),
                "her2_status": self._geo_mapped_value(parsed, "her2_status"),
                "treatment": None if preclinical else treatment,
                "experimental_group": treatment if preclinical else None,
                "stage": self._geo_mapped_value(parsed, "stage"),
                "age": self._geo_mapped_value(parsed, "age"),
                "subtype": self._geo_mapped_value(parsed, "subtype"),
                "response_domain": response_domain,
                "raw_characteristics": "；".join(item for item in raw_items if item),
            }
            for gene in spec.genes:
                field = f"{gene.lower()}_mutation"
                raw_mut = (
                    parsed.get(field)
                    or parsed.get(f"{gene.lower()}_status")
                    or parsed.get(f"{gene.lower()}_mut")
                    or parsed.get(gene.lower())
                )
                flag = self._as_mutation_flag(raw_mut)
                if flag is not None:
                    row[field] = flag
            self._enrich_geo_row_from_status(row, parsed, result.accession)
            rows.append(row)

        baseline_rows = [
            row
            for row in rows
            if row.get("timepoint") == "基线" and row.get("response_domain") != "preclinical_cell_line"
        ]
        filtered_count = len(rows) - len(baseline_rows)
        if baseline_rows:
            rows = baseline_rows
        rows, duplicate_count = self._deduplicate_rows(rows, "sample_id")
        rows, alias_actions = self._materialize_canonical_fields(rows, spec, result.accession)
        rows, derive_actions = self._derive_same_cohort_fields(rows, spec)
        cleaning_actions = [
            "解析 GEO Series Matrix 的真实样本元数据并保留原始 characteristics。",
            "统一疾病、受体状态、取样时间点和术后响应的分类值。",
            "从同一样本特征解析亚型、HER2 和治疗字段，不从其他研究补患者。",
        ]
        preclinical_count = sum(row.get("response_domain") == "preclinical_cell_line" for row in rows)
        clinical_count = sum(row.get("response_domain") == "clinical" for row in rows)
        if preclinical_count:
            cleaning_actions.append(
                f"识别 {preclinical_count} 个前临床实验样本；将 shRNA/敲低等扰动移入实验分组，不标作患者治疗方案。"
            )
        cleaning_actions.extend(alias_actions)
        cleaning_actions.extend(derive_actions)
        if filtered_count:
            cleaning_actions.append(
                f"主分析表保留 {len(rows)} 个基线样本，分离 {filtered_count} 个治疗后配对样本，避免同一患者跨分析分区。"
            )
        if preclinical_count == len(rows):
            unit = "前临床实验样本（非患者临床队列）"
        elif clinical_count == len(rows):
            unit = "基线患者样本（一名患者一行）"
        else:
            unit = "样本（患者身份或响应域未完全确认）"
        dataset = self._dataset_from_rows(
            rows,
            name=f"{DATASET_NAMES.get(result.accession, result.accession)}科研数据集",
            unit=unit,
            spec=spec,
        )
        report = self._readiness(
            dataset,
            spec,
            cleaned_value_count=cleaned_values,
            duplicate_row_count=duplicate_count,
            cleaning_actions=cleaning_actions,
        )
        if preclinical_count:
            report.warnings.insert(
                0,
                f"该 GEO 队列含 {preclinical_count} 个细胞系/前临床实验样本，不能作为患者临床响应主分析表。",
            )
            report.recommendations.insert(
                0,
                "如题目研究患者疗效或生存，应改用含患者编号和对应临床结局的队列；本表仅作为机制证据独立保留。",
            )
        return dataset, report

    def _dataset_from_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        name: str,
        unit: str,
        spec: ResearchSpec,
    ) -> ModelingDataset:
        rows, _derive_actions = self._derive_same_cohort_fields(rows, spec)
        rows, _map_actions = self._map_outcome_synonyms(rows, spec)
        rows, _her2_actions = self._map_her2_synonyms(rows)
        ordered_names = self._ordered_columns(rows, spec)
        columns = [self._describe_column(name, rows, spec) for name in ordered_names]
        normalized_rows = [{name: row.get(name) for name in ordered_names} for row in rows]
        target = self._select_target(ordered_names, spec, normalized_rows)
        return ModelingDataset(
            name=name,
            unit_of_analysis=unit,
            columns=columns,
            rows=normalized_rows,
            row_count=len(normalized_rows),
            patient_count=len({row.get("patient_id") for row in normalized_rows if row.get("patient_id")}),
            sample_count=len({row.get("sample_id") for row in normalized_rows if row.get("sample_id")}),
            target_column=target,
            class_distribution=self._distribution(normalized_rows, target),
        )

    def _readiness(
        self,
        dataset: ModelingDataset,
        spec: ResearchSpec,
        *,
        tables: dict[str, Any] | None = None,
        cleaned_value_count: int = 0,
        duplicate_row_count: int = 0,
        excluded_orphan_record_count: int = 0,
        cleaning_actions: list[str] | None = None,
    ) -> AnalysisReadinessReport:
        repeated = Counter(row.get("patient_id") for row in dataset.rows if row.get("patient_id"))
        repeated_count = sum(count > 1 for count in repeated.values())
        truncated = sorted(
            name for name, table in (tables or {}).items() if getattr(table, "truncated", False)
        )
        warnings: list[str] = []
        recommendations: list[str] = []
        if dataset.row_count < 30:
            warnings.append("当前患者/样本数少于 30，不足以支持稳健的多变量统计分析。")

        needs_outcome = needs_clinical_outcome(spec)
        target_match_rate = outcome_match_rate(dataset, spec)
        target_match = dataset.target_column is not None
        if needs_outcome and not target_match:
            requested = "、".join(spec.outcomes) or "当前科研问题指定的结局"
            warnings.append(f"当前队列不含与“{requested}”匹配的研究结局；系统未用生存结局冒充治疗响应。")
            recommendations.append("更换为含目标结局的独立队列，不对不同患者来源的数据进行强行补值或横向拼接。")
        elif not needs_outcome:
            target_match = True
            target_match_rate = 1.0
        elif target_match and target_match_rate < 1:
            warnings.append(
                f"研究结局匹配率为 {target_match_rate:.1%}：按字段别名契合与行覆盖连续计分，不是有列即 100%。"
            )
        if truncated:
            warnings.append("以下上游表仍受最大记录数限制：" + "、".join(truncated) + "。")
            recommendations.append("提高最大记录数或改用能够完整下载的队列文件；截断的突变缺失不能解释为野生型。")
        if repeated_count:
            warnings.append(f"发现 {repeated_count} 名患者对应多个样本，随机按行切分会造成数据泄漏。")

        target_missing_rate: float | None = None
        nonmissing_classes: set[str] = set()
        if dataset.target_column and dataset.row_count:
            target_values = [row.get(dataset.target_column) for row in dataset.rows]
            missing = sum(value in {None, ""} for value in target_values)
            target_missing_rate = missing / dataset.row_count
            nonmissing_classes = {str(value) for value in target_values if value not in {None, ""}}
            if needs_outcome and target_missing_rate > 0.2:
                warnings.append(f"研究结局缺失率为 {target_missing_rate:.1%}，需要预先定义纳入/排除规则。")
            if needs_outcome and len(nonmissing_classes) <= 1:
                warnings.append("非缺失研究结局只有一个类别，无法进行可靠的分组比较。")
        elif dataset.target_column:
            warnings.append("当前没有实际数据行，研究结局未评测。")

        field_completeness_rate = self._field_completeness(dataset)
        variable_coverage = self._requested_variable_coverage(dataset, spec)
        if variable_coverage is not None and variable_coverage < 1:
            warnings.append(
                f"请求的基因变量覆盖率为 {variable_coverage:.1%}；按突变、蛋白变异和拷贝数的行覆盖连续计分，拷贝数不得记为完整突变证据。"
            )
            recommendations.append(
                "基因假设需选择同时具有分子检测的同一患者队列；禁止把其他研究的突变补到当前患者。"
                if not needs_outcome
                else "把该队列用于治疗响应/受体分层；基因假设需选择同时具有分子检测和同一患者结局的队列。"
            )

        analysis_ready = bool(
            dataset.row_count >= 30
            and (target_match if needs_outcome else True)
            and not truncated
            and ((target_missing_rate or 0) <= 0.2 if needs_outcome and dataset.target_column else True)
            and (len(nonmissing_classes) > 1 if needs_outcome and dataset.target_column else True)
        )
        if analysis_ready:
            if variable_coverage is not None and variable_coverage < 1:
                status = "可支持当前分析，分子暴露待同队列补充"
            else:
                status = "可支持科研分析"
        elif needs_outcome and dataset.target_column is None:
            status = "研究结局不匹配"
        elif variable_coverage is not None and variable_coverage < 1:
            status = "研究变量待补充"
        else:
            status = "需要补充或清洗"

        recommendations.extend(
            [
                "分析数据应按患者编号分组，同一患者的全部样本必须进入同一分析分区。",
                "正式分析前冻结队列纳入标准、研究结局定义和变量时间窗。",
                "知识证据与临床试验目录仅作解释层，不与患者行直接拼接。",
            ]
        )
        return AnalysisReadinessReport(
            status=status,
            analysis_ready=analysis_ready,
            row_count=dataset.row_count,
            feature_count=max(len(dataset.columns) - 4, 0),
            target_column=dataset.target_column,
            target_missing_rate=target_missing_rate,
            field_completeness_rate=field_completeness_rate,
            target_match=target_match,
            target_match_rate=target_match_rate,
            requested_variable_coverage_rate=variable_coverage,
            repeated_patient_count=repeated_count,
            duplicate_row_count=duplicate_row_count,
            cleaned_value_count=cleaned_value_count,
            excluded_orphan_record_count=excluded_orphan_record_count,
            cleaning_actions=cleaning_actions or [],
            split_strategy="按患者编号分组；同一患者的全部样本必须进入同一分析分区。",
            warnings=warnings,
            recommendations=list(dict.fromkeys(recommendations)),
        )

    @staticmethod
    def _match_entity(
        raw: dict[str, Any],
        by_sample: dict[str, tuple[str, str]],
        by_patient: dict[str, list[tuple[str, str]]],
    ) -> tuple[str, str] | None:
        sample_id = str(raw.get("sampleId") or "").strip()
        patient_id = str(raw.get("patientId") or "").strip()
        if sample_id and sample_id in by_sample:
            return by_sample[sample_id]
        matches = by_patient.get(patient_id, [])
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _normalize_attribute(value: Any) -> str | None:
        raw = str(value or "").strip().upper()
        if not raw:
            return None
        if raw in ATTRIBUTE_ALIASES:
            return ATTRIBUTE_ALIASES[raw]
        normalized = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
        return normalized or None

    @staticmethod
    def _clean_value(value: Any) -> tuple[Any, bool]:
        if value is None:
            return None, False
        text = str(value).strip()
        if not text or text.upper() in {"NA", "N/A", "NULL", "UNKNOWN", "[NOT AVAILABLE]", "NOT AVAILABLE"}:
            return None, bool(text)
        compact = text.casefold().replace(" ", "")
        if compact in {"2+", "ihc2+", "2"}:
            return text, False
        normalized = VALUE_NORMALIZATION.get(text.upper())
        if normalized is not None:
            return normalized, normalized != text
        if re.fullmatch(r"-?\d+", text):
            try:
                return int(text), False
            except ValueError:
                pass
        if re.fullmatch(r"-?(?:\d+\.\d*|\d*\.\d+)", text):
            try:
                return float(text), False
            except ValueError:
                pass
        return text, False

    @staticmethod
    def _has_filled(value: Any) -> bool:
        return value not in (None, "", [], {}, "NA", "N/A", "<缺失>")

    @classmethod
    def _parse_geo_characteristics(cls, raw_items: list[str]) -> tuple[dict[str, Any], int]:
        parsed: dict[str, Any] = {}
        cleaned = 0
        for raw_item in raw_items:
            for piece in cls._characteristic_pieces(raw_item):
                field, value_text = cls._split_characteristic_piece(piece)
                if not field:
                    continue
                normalized_field = cls._normalize_attribute(field) or re.sub(r"[^a-z0-9]+", "_", field.casefold()).strip("_")
                if not normalized_field:
                    continue
                value, changed = cls._clean_value(value_text)
                parsed[normalized_field] = value
                cleaned += int(changed)
        return parsed, cleaned

    @staticmethod
    def _characteristic_pieces(raw_item: str) -> list[str]:
        text = str(raw_item or "").strip().strip('"')
        if not text:
            return []
        parts = [part.strip() for part in _CHARACTERISTIC_SPLIT.split(text) if part.strip()]
        keyed = [part for part in parts if ":" in part or "=" in part]
        if len(parts) > 1 and len(keyed) >= 2:
            return parts
        return [text]

    @staticmethod
    def _split_characteristic_piece(piece: str) -> tuple[str | None, str]:
        for separator in (":", "="):
            if separator in piece:
                field, _, value = piece.partition(separator)
                if field.strip():
                    return field.strip(), value.strip()
        return None, piece.strip()

    @classmethod
    def _geo_mapped_value(cls, parsed: dict[str, Any], canonical: str) -> Any:
        for key in GEO_FIELD_SYNONYMS.get(canonical, (canonical,)):
            value = parsed.get(key)
            if not cls._has_filled(value):
                continue
            if canonical == "treatment_response":
                return cls._as_treatment_response(key, value)
            return value
        return None

    @classmethod
    def _as_treatment_response(cls, source_field: str, value: Any) -> Any:
        text = str(value).strip()
        upper = text.upper()
        if source_field in _PCR_FIELD_NAMES or source_field == "pcr":
            if text in {"是", "1"} or upper in {"YES", "TRUE", "PCR", "POSITIVE"}:
                return "病理完全缓解（pCR）"
            if text in {"否", "0"} or upper in {"NO", "FALSE", "NEGATIVE", "RD", "NON-PCR"}:
                return "未达客观缓解"
        return value

    @staticmethod
    def _as_mutation_flag(value: Any) -> int | None:
        if value in {0, 1}:
            return int(value)
        text = str(value or "").strip()
        if not text:
            return None
        compact = text.casefold().replace(" ", "").replace("_", "").replace("-", "")
        if compact in {"1", "yes", "true", "mutant", "mutated", "mutation", "positive", "pos", "是", "突变"}:
            return 1
        if compact in {"0", "no", "false", "wt", "wildtype", "wild", "negative", "neg", "否", "野生"}:
            return 0
        if re.fullmatch(r"[A-Z]\d+[A-Z*]|[A-Z]\d+fs", text, re.IGNORECASE):
            return 1
        return None

    @staticmethod
    def _infer_sample_type(source_name: Any) -> str | None:
        text = str(source_name or "").casefold()
        if not text:
            return None
        if any(token in text for token in ("cell line", "cell culture", "细胞系")):
            return "细胞系"
        if any(token in text for token in ("metastasis", "metastatic", "转移")):
            return "转移灶"
        if any(token in text for token in ("normal", "healthy", "正常")):
            return "正常组织"
        if any(token in text for token in ("tumor", "tumour", "cancer", "carcinoma", "biopsy", "肿瘤", "癌")):
            return "原发肿瘤"
        return None

    @classmethod
    def _enrich_geo_row_from_status(
        cls,
        row: dict[str, Any],
        parsed: dict[str, Any],
        accession: str,
    ) -> None:
        blob = " ".join(
            str(parsed.get(key) or row.get(key) or "")
            for key in ("patient_status", "disease", "subtype", "her2_status", "raw_characteristics")
        )
        upper = blob.upper()
        if any(token in upper or token in blob for token in ("HER2+", "HER2 阳性", "HER2阳性", "HER-2+")):
            if not cls._has_filled(row.get("her2_status")):
                row["her2_status"] = "阳性"
            if not cls._has_filled(row.get("subtype")):
                row["subtype"] = "HER2-positive"
            if str(row.get("disease") or "").strip() in {"HER2 阳性乳腺癌", "HER2+ Breast Cancer"}:
                row["disease"] = "乳腺癌"
        protocol = GEO_COHORT_PROTOCOL.get(str(accession or "").upper()) or {}
        for field, value in protocol.items():
            if not cls._has_filled(row.get(field)):
                row[field] = value

    @classmethod
    def _materialize_canonical_fields(
        cls,
        rows: list[dict[str, Any]],
        spec: ResearchSpec,
        accession: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        actions: list[str] = []
        subtype_filled = 0
        treatment_filled = 0
        protocol = GEO_COHORT_PROTOCOL.get(str(accession or "").upper()) or {}
        for row in rows:
            for key, value in list(row.items()):
                if str(key).endswith("_mutation"):
                    flag = cls._as_mutation_flag(value)
                    if flag is not None:
                        row[key] = flag
            if not cls._has_filled(row.get("subtype")):
                her2 = str(row.get("her2_status") or "").strip()
                if her2 in {"阳性", "Positive", "positive"}:
                    row["subtype"] = "HER2-positive"
                    subtype_filled += 1
                elif her2 in {"阴性", "Negative", "negative"}:
                    row["subtype"] = "HER2-negative"
                    subtype_filled += 1
            if not cls._has_filled(row.get("treatment")):
                for candidate in (
                    row.get("chemotherapy"),
                    row.get("hormone_therapy"),
                    row.get("radio_therapy"),
                    protocol.get("treatment"),
                ):
                    if cls._has_filled(candidate):
                        text = str(candidate)
                        if text in {"是", "Yes", "YES", "true"}:
                            if candidate is row.get("chemotherapy"):
                                row["treatment"] = "化疗"
                            elif candidate is row.get("hormone_therapy"):
                                row["treatment"] = "内分泌治疗"
                            elif candidate is row.get("radio_therapy"):
                                row["treatment"] = "放射治疗"
                            else:
                                row["treatment"] = text
                        else:
                            row["treatment"] = text
                        treatment_filled += 1
                        break
            if not cls._has_filled(row.get("treatment_response")) and cls._has_filled(row.get("pcr")):
                row["treatment_response"] = row.get("pcr")
            if not cls._has_filled(row.get("sample_type")) and protocol.get("sample_type"):
                row["sample_type"] = protocol["sample_type"]
            if not cls._has_filled(row.get("sample_timepoint")) and cls._has_filled(row.get("timepoint")):
                row["sample_timepoint"] = row.get("timepoint")
        if subtype_filled:
            actions.append(f"由同队列 HER2 状态解析疾病亚型 {subtype_filled} 行。")
        if treatment_filled:
            actions.append(f"由同队列治疗/方案字段补全治疗方案 {treatment_filled} 行。")
        if protocol:
            actions.append(
                f"对 {accession} 均匀治疗队列补全研究级方案字段，并保留样本原始特征备查。"
            )
        return rows, actions

    @classmethod
    def _map_outcome_synonyms(
        cls,
        rows: list[dict[str, Any]],
        spec: ResearchSpec,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        if not rows:
            return rows, []
        actions: list[str] = []
        survival_aliases = {
            "overall_survival": "os_months",
            "overall_survival_months": "os_months",
            "os": "os_status",
            "dss": "dss_status",
            "rfs": "dfs_status",
            "rfs_status": "dfs_status",
            "rfs_months": "dfs_months",
            "disease_free_survival": "dfs_months",
            "disease_free_survival_months": "dfs_months",
            "disease_specific_survival": "dss_months",
        }
        pcr_aliases = {
            "pathological_complete_response": "pcr",
            "pathologic_complete_response": "pcr",
            "pathologic_response_pcr_rd": "pcr",
            "pcr_status": "pcr",
            "pcr_yes_no": "pcr",
            "pcr_rd": "pcr",
            "pathologic_response": "treatment_response",
            "response_at_surgery": "treatment_response",
        }
        survival_n = 0
        pcr_n = 0
        want_pcr = asks_pcr(spec) or needs_clinical_outcome(spec)
        want_survival = asks_survival(spec) or "survival" in (spec.outcomes or [])
        for row in rows:
            if want_survival:
                for raw_name, canonical in survival_aliases.items():
                    if cls._has_filled(row.get(raw_name)) and not cls._has_filled(row.get(canonical)):
                        row[canonical] = row.get(raw_name)
                        row.setdefault("raw_field", raw_name)
                        row.setdefault("raw_value", row.get(raw_name))
                        survival_n += 1
            if want_pcr:
                for forbidden in ("os_status", "os_months", "dfs_status", "dfs_months", "dss_status", "dss_months", "auc", "ic50"):
                    if forbidden in row and not cls._has_filled(row.get("pcr")):
                        continue
                for raw_name, canonical in pcr_aliases.items():
                    if cls._has_filled(row.get(raw_name)) and not cls._has_filled(row.get(canonical)):
                        row[canonical] = row.get(raw_name)
                        row.setdefault("raw_field", raw_name)
                        row.setdefault("raw_value", row.get(raw_name))
                        pcr_n += 1
                if cls._has_filled(row.get("pcr")) and not cls._has_filled(row.get("treatment_response")):
                    row["treatment_response"] = row.get("pcr")
        if survival_n:
            actions.append(f"将 OS/RFS/DSS 同义列映射到 canonical 生存字段 {survival_n} 行，保留原始列。")
        if pcr_n:
            actions.append(f"将病理响应同义列映射到 pCR/treatment_response {pcr_n} 行；未使用生存或 AUC。")
        return rows, actions

    @classmethod
    def _map_her2_synonyms(cls, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        if not rows:
            return rows, []
        aliases = (
            "her2_ihc",
            "her2_status_ihc",
            "her2_ihc_status",
            "her2_ihc_score",
            "ihc_her2",
            "erbb2_status",
        )
        mapped = 0
        for row in rows:
            if cls._has_filled(row.get("her2_status")):
                continue
            for name in aliases:
                raw = row.get(name)
                if not cls._has_filled(raw):
                    continue
                row["her2_status"] = raw
                row.setdefault("raw_field", name)
                row.setdefault("raw_value", raw)
                mapped += 1
                break
        if not mapped:
            return rows, []
        return rows, [f"将 HER2 IHC/临床同义列映射到 her2_status {mapped} 行；IHC 2+ 保持原值，不判为阳性。"]

    @staticmethod
    def _filter_rows_for_research_spec(
        rows: list[dict[str, Any]],
        spec: ResearchSpec,
    ) -> tuple[list[dict[str, Any]], str | None]:
        subtype = (spec.subtype or "").casefold()
        if not rows:
            return rows, None
        if "hr-positive" in subtype and ("her2-negative" in subtype or "her2-" in subtype):
            return ResearchDatasetBuilder._filter_by_receptor_rule(
                rows,
                require_hr_positive=True,
                require_her2_negative=True,
                label="HR+/HER2-",
            )
        if is_tnbc_question(spec):
            return ResearchDatasetBuilder._filter_by_receptor_rule(
                rows,
                require_hr_positive=False,
                require_her2_negative=True,
                require_hr_negative=True,
                label="三阴性（TNBC）",
            )
        return rows, None

    @staticmethod
    def _filter_by_receptor_rule(
        rows: list[dict[str, Any]],
        *,
        require_hr_positive: bool = False,
        require_her2_negative: bool = False,
        require_hr_negative: bool = False,
        label: str,
    ) -> tuple[list[dict[str, Any]], str | None]:
        receptor_columns = {"er_status", "pr_status", "her2_status"} & {
            key for row in rows for key in row
        }
        if not receptor_columns:
            return rows, f"当前问题要求 {label}，但主队列缺少 ER/PR/HER2 受体字段；未强行过滤患者。"

        filtered: list[dict[str, Any]] = []
        for row in rows:
            her2 = ResearchDatasetBuilder._receptor_polarity(row.get("her2_status"))
            er = ResearchDatasetBuilder._receptor_polarity(row.get("er_status"))
            pr = ResearchDatasetBuilder._receptor_polarity(row.get("pr_status"))
            if require_her2_negative and her2 not in {None, "negative"}:
                continue
            hr_present = er is not None or pr is not None
            hr_positive = er == "positive" or pr == "positive"
            if require_hr_positive and hr_present and not hr_positive:
                continue
            if require_hr_negative and hr_positive:
                continue
            if require_hr_negative and her2 == "equivocal":
                continue
            if require_hr_negative and er is not None and pr is not None and not (
                er == "negative" and pr == "negative"
            ):
                continue
            filtered.append(row)
        if not filtered:
            return rows, f"当前问题要求 {label}，但自动过滤后无可用记录；保留原队列并提示人工复核受体定义。"
        removed = len(rows) - len(filtered)
        if removed:
            return filtered, f"按 {label} 约束过滤队列，保留 {len(filtered)} 行，排除 {removed} 行非匹配或受体冲突记录。"
        return filtered, f"当前队列记录满足 {label} 自动过滤条件。"

    @staticmethod
    def _receptor_polarity(value: Any) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        compact = text.casefold().replace(" ", "").replace("_", "")
        if compact in {"2+", "ihc2+", "2", "equivocal", "ambiguous", "indeterminate", "不明", "临界", "可疑"}:
            return "equivocal"
        if compact in {"阳性", "positive", "pos", "是", "yes", "1", "true", "3+", "ihc3+"}:
            return "positive"
        if compact in {"阴性", "negative", "neg", "否", "no", "0", "false", "0+", "1+", "ihc0", "ihc1+", "ihc0+"}:
            return "negative"
        return None

    @staticmethod
    def _typed_value(value: Any) -> Any:
        return ResearchDatasetBuilder._clean_value(value)[0]

    @staticmethod
    def _extract_gene(raw: dict[str, Any]) -> str | None:
        nested = raw.get("gene")
        symbol = nested.get("hugoGeneSymbol") if isinstance(nested, dict) else None
        symbol = symbol or raw.get("hugoGeneSymbol")
        text = str(symbol or "").strip().upper()
        return text if re.fullmatch(r"[A-Z0-9][A-Z0-9._-]*", text) else None

    @staticmethod
    def _research_priority_columns(spec: ResearchSpec | None) -> list[str]:
        if spec is None:
            return []
        names: list[str] = ["disease", "subtype", "derived_ihc_subtype"]
        for gene in spec.genes:
            symbol = gene.lower()
            names.extend([f"{symbol}_mutation", f"{symbol}_variants", f"{symbol}_cna", f"{symbol}_altered"])
        if {item.upper() for item in spec.genes} >= {"BRCA1", "BRCA2"}:
            names.append("brca_any_mutation")
        if asks_pcr(spec):
            names.extend(["pcr", "pcr_binary", "treatment_response", "response_domain"])
        elif asks_survival(spec):
            names.extend(["os_status", "os_months", "dfs_status", "dfs_months"])
        elif needs_clinical_outcome(spec):
            names.extend(["treatment_response", "pcr", "pcr_binary", "response", "response_domain"])
        names.extend(["er_status", "pr_status", "her2_status"])
        goal = (spec.research_goal or "").casefold()
        if any(token in goal for token in ("intclust", "integrative cluster", "整合聚类")):
            names.append("intclust")
        if asks_treatment(spec) or needs_clinical_outcome(spec):
            names.extend(["treatment", "chemotherapy", "hormone_therapy", "radio_therapy", "drug"])
        names.extend(
            [
                "sample_type",
                "sample_timepoint",
                "timepoint",
                "sample_source",
                "age",
                "age_group",
                "stage",
            ]
        )
        return list(dict.fromkeys(names))

    @classmethod
    def _derive_same_cohort_fields(
        cls,
        rows: list[dict[str, Any]],
        spec: ResearchSpec,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        if not rows:
            return rows, []
        actions: list[str] = []
        subtype_n = 0
        pcr_n = 0
        age_n = 0
        altered_n = 0
        brca_n = 0
        genes = [gene.lower() for gene in spec.genes]
        want_brca = {item.upper() for item in spec.genes} >= {"BRCA1", "BRCA2"}
        for row in rows:
            er = cls._receptor_polarity(row.get("er_status"))
            pr = cls._receptor_polarity(row.get("pr_status"))
            her2 = cls._receptor_polarity(row.get("her2_status"))
            derived_subtype = None
            if er == "negative" and pr == "negative" and her2 == "negative":
                derived_subtype = "Triple-negative"
            elif her2 == "positive" and (er == "positive" or pr == "positive"):
                derived_subtype = "HR-positive/HER2-positive"
            elif her2 == "positive":
                derived_subtype = "HER2-positive"
            elif her2 == "negative" and (er == "positive" or pr == "positive"):
                derived_subtype = "HR-positive/HER2-negative"
            if derived_subtype:
                row["derived_ihc_subtype"] = derived_subtype
                subtype_n += 1
                if not cls._has_filled(row.get("subtype")):
                    row["subtype"] = derived_subtype
            pcr_flag = cls._as_pcr_flag(row.get("pcr"))
            if pcr_flag is None:
                pcr_flag = cls._as_pcr_flag(row.get("treatment_response"))
            if pcr_flag is not None:
                row["pcr_binary"] = pcr_flag
                pcr_n += 1
                if not cls._has_filled(row.get("pcr")) and pcr_flag == 1:
                    row["pcr"] = "病理完全缓解（pCR）"
                elif not cls._has_filled(row.get("pcr")) and pcr_flag == 0:
                    row["pcr"] = "未达病理完全缓解"
            age_group = cls._age_group(row.get("age"))
            if age_group is not None:
                row["age_group"] = age_group
                age_n += 1
            for gene in genes:
                mutated = cls._as_mutation_flag(row.get(f"{gene}_mutation"))
                cna_altered = cls._cna_is_altered(row.get(f"{gene}_cna"))
                if mutated is None and cna_altered is None:
                    continue
                row[f"{gene}_altered"] = int(mutated == 1 or cna_altered is True)
                altered_n += 1
            if want_brca:
                brca1 = cls._as_mutation_flag(row.get("brca1_mutation"))
                brca2 = cls._as_mutation_flag(row.get("brca2_mutation"))
                if brca1 is not None or brca2 is not None:
                    row["brca_any_mutation"] = int(brca1 == 1 or brca2 == 1)
                    brca_n += 1
        if subtype_n:
            actions.append(f"由同一行 ER/PR/HER2 组合免疫组化亚型 {subtype_n} 行；HER2 IHC 2+ 未自动判阳，未使用 ERBB2 CNA。")
        if pcr_n:
            actions.append(f"由同队列 pCR/治疗响应文本派生病理完全缓解二值标记 {pcr_n} 行，未使用生存结局。")
        if age_n:
            actions.append(f"由同队列年龄派生年龄分组 {age_n} 行。")
        if altered_n:
            actions.append(
                "由同队列突变和/或离散拷贝数派生基因分子改变标记；拷贝数扩增不得解释为免疫组化阳性。"
            )
        if brca_n:
            actions.append(f"由同一行 BRCA1/BRCA2 突变组合 BRCA 任一突变标记 {brca_n} 行。")
        return rows, actions

    @staticmethod
    def _as_pcr_flag(value: Any) -> int | None:
        if value in {0, 1}:
            return int(value)
        text = str(value or "").strip()
        if not text:
            return None
        compact = text.casefold().replace(" ", "").replace("_", "").replace("-", "")
        if any(token in compact for token in ("nonpcr", "nopcr", "未达", "未获得")):
            return 0
        if compact in {"rd", "nor", "residualdisease", "nonresponse", "noresponse"}:
            return 0
        if compact in {"pcr", "yes", "true", "1", "是"} or "病理完全缓解" in text or compact.endswith("pcr"):
            if "客观缓解" in text and "病理完全缓解" not in text:
                return None
            return 1
        return None

    @staticmethod
    def _age_group(value: Any) -> str | None:
        age: float | None = None
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            age = float(value)
        else:
            text = str(value or "").strip()
            if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
                age = float(text)
        if age is None or age < 0 or age > 120:
            return None
        if age < 40:
            return "<40"
        if age < 50:
            return "40-49"
        if age < 60:
            return "50-59"
        if age < 70:
            return "60-69"
        return ">=70"

    @staticmethod
    def _cna_is_altered(value: Any) -> bool | None:
        if value in {None, ""}:
            return None
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return abs(number) >= 2

    @staticmethod
    def _ordered_columns(rows: list[dict[str, Any]], spec: ResearchSpec | None = None) -> list[str]:
        fixed = ["study_id", "patient_id", "sample_id", "source_id"]
        filled = {
            key
            for row in rows
            for key, value in row.items()
            if key not in fixed and ResearchDatasetBuilder._has_filled(value)
        }
        present_fixed = [name for name in fixed if any(name in row for row in rows)]
        priority = [
            name
            for name in ResearchDatasetBuilder._research_priority_columns(spec)
            if name in filled
        ]
        rest = sorted(name for name in filled if name not in present_fixed and name not in set(priority))
        return present_fixed + priority + rest

    @staticmethod
    def _select_target(columns: list[str], spec: ResearchSpec, rows: list[dict[str, Any]] | None = None) -> str | None:
        if asks_pcr(spec):
            priority = ["pcr", "pcr_binary", "treatment_response", "response"]
        elif asks_survival(spec) or "survival" in spec.outcomes:
            priority = ["os_status", "os_months", "dfs_status", "dfs_months", "dss_status", "dss_months", "vital_status"]
        elif needs_clinical_outcome(spec):
            priority = ["treatment_response", "pcr", "pcr_binary", "response", "pathological_complete_response"]
        else:
            priority = []
            for gene in spec.genes:
                symbol = gene.lower()
                priority.extend([f"{symbol}_mutation", f"{symbol}_variants", f"{symbol}_altered"])
            priority.extend(["er_status", "her2_status", "subtype", "derived_ihc_subtype"])
        for name in priority:
            if name not in columns:
                continue
            if rows is not None and not any(ResearchDatasetBuilder._has_filled(row.get(name)) for row in rows):
                continue
            return name
        return None

    @staticmethod
    def _distribution(rows: list[dict[str, Any]], target: str | None) -> dict[str, int]:
        if not target:
            return {}
        counter = Counter("<缺失>" if row.get(target) in {None, ""} else str(row.get(target)) for row in rows)
        return dict(counter.most_common())

    @staticmethod
    def _field_completeness(dataset: ModelingDataset) -> float | None:
        if not dataset.rows or not dataset.columns:
            return None
        analytical = [column.name for column in dataset.columns if column.role != "审计信息"]
        total = len(dataset.rows) * len(analytical)
        present = sum(row.get(name) not in {None, ""} for row in dataset.rows for name in analytical)
        return present / total if total else None

    @staticmethod
    def _requested_variable_coverage(dataset: ModelingDataset, spec: ResearchSpec) -> float | None:
        return requested_gene_coverage(dataset, spec)

    @staticmethod
    def _deduplicate_rows(rows: list[dict[str, Any]], key_name: str) -> tuple[list[dict[str, Any]], int]:
        unique: dict[str, dict[str, Any]] = {}
        anonymous: list[dict[str, Any]] = []
        duplicates = 0
        for row in rows:
            key = str(row.get(key_name) or "").strip()
            if not key:
                anonymous.append(row)
            elif key in unique:
                duplicates += 1
            else:
                unique[key] = row
        return list(unique.values()) + anonymous, duplicates

    @staticmethod
    def _describe_column(name: str, rows: list[dict[str, Any]], spec: ResearchSpec | None = None) -> DatasetColumn:
        values = [row.get(name) for row in rows if row.get(name) is not None]
        data_type = "number" if values and all(isinstance(value, (int, float)) for value in values) else "string"
        derived_names = {"derived_ihc_subtype", "pcr_binary", "age_group", "brca_any_mutation"}
        priority = set(ResearchDatasetBuilder._research_priority_columns(spec))
        if name in {"study_id", "patient_id", "sample_id"}:
            role = "标识符"
        elif name in {"source_id", "raw_characteristics"}:
            role = "审计信息"
        elif name in {"pcr", "pcr_binary", "treatment_response", "response", "os_status", "dfs_status", "dss_status"}:
            role = "研究结局"
        elif name in derived_names or name.endswith("_altered"):
            role = "同队列派生"
        elif spec is not None and name not in priority and name not in {
            "disease",
            "sample_type",
            "sample_source",
            "response_domain",
        }:
            role = "次要临床字段"
        else:
            role = "研究变量"
        source_field = name
        if name.endswith("_mutation"):
            gene = name.removesuffix("_mutation").upper()
            label = f"{gene} 突变状态"
            description = "1=本次完整返回的突变记录中观察到；0=未观察到。上游截断时不得把 0 解释为确定野生型。"
        elif name.endswith("_variants"):
            gene = name.removesuffix("_variants").upper()
            label = f"{gene} 蛋白变异"
            description = "cBioPortal 返回的蛋白改变，多个值以分号分隔。"
        elif name.endswith("_cna"):
            gene = name.removesuffix("_cna").upper()
            label = f"{gene} 离散拷贝数"
            description = "cBioPortal 离散 CNA 值；不得直接等同于临床 IHC/FISH 状态。"
        elif name.endswith("_altered"):
            gene = name.removesuffix("_altered").upper()
            label = f"{gene} 分子改变（同队列派生）"
            description = "由同队列突变或离散拷贝数组合；CNA amplification 不得解释为 IHC 阳性。"
            source_field = f"{gene.lower()}_mutation,{gene.lower()}_cna"
        else:
            label = CHINESE_LABELS.get(name, name.replace("_", " "))
            description = FIELD_DESCRIPTIONS.get(
                name,
                f"来自上游字段 {name}；用于分析前应在原研究数据字典中确认定义、单位和时间点。",
            )
            if name == "derived_ihc_subtype":
                source_field = "er_status,pr_status,her2_status"
            elif name == "pcr_binary":
                source_field = "pcr,treatment_response"
            elif name == "age_group":
                source_field = "age"
            elif name == "brca_any_mutation":
                source_field = "brca1_mutation,brca2_mutation"
        return DatasetColumn(
            name=name,
            label_zh=label,
            data_type=data_type,
            role=role,
            source_field=source_field,
            description=description,
        )
