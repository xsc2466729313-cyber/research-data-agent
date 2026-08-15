from __future__ import annotations

import csv
import gzip
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from backend.app.agent.models import (
    AnalysisReadinessReport,
    DatasetColumn,
    ModelingDataset,
)
from backend.app.models import ResearchSpec
from backend.app.sources.cbioportal.models import CBioPortalAdapterResult
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
    "os_status": "总生存状态",
    "os_months": "总生存时间（月）",
    "dfs_status": "无病生存状态",
    "dfs_months": "无病生存时间（月）",
    "pcr": "病理完全缓解",
    "treatment_response": "术后治疗响应",
    "response_domain": "响应数据域",
    "timepoint": "取样时间点",
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
    "os_status": "随访截止时总生存结局状态。",
    "os_months": "从原研究定义的起点到死亡或末次随访的月数。",
    "dfs_status": "无病生存事件状态。",
    "dfs_months": "从原研究定义的起点到复发/事件或末次随访的月数。",
    "pcr": "术后病理完全缓解结局；应按原研究对 pCR 的定义解释。",
    "treatment_response": "术后疗效分组；GSE76360 中 pCR=病理完全缓解、OBJR=客观缓解、NOR=未达客观缓解。",
    "response_domain": "区分患者临床响应、临床试验响应和细胞系药敏，防止不同结局混用。",
    "timepoint": "样本采集相对治疗的时间点；本主分析表保留基线样本以避免配对泄漏。",
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
    "HER2_STATUS": "her2_status",
    "OS_STATUS": "os_status",
    "OS_MONTHS": "os_months",
    "DFS_STATUS": "dfs_status",
    "DFS_MONTHS": "dfs_months",
    "RFS_STATUS": "dfs_status",
    "RFS_MONTHS": "dfs_months",
    "PCR": "pcr",
    "PATHOLOGIC_COMPLETE_RESPONSE": "pcr",
    "TREATMENT_RESPONSE": "treatment_response",
    "RESPONSE": "treatment_response",
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
    "POST": "治疗后",
    "PCR": "病理完全缓解（pCR）",
    "OBJR": "客观缓解",
    "NOR": "未达客观缓解",
    "0:LIVING": "生存",
    "1:DECEASED": "死亡",
}

DATASET_NAMES = {
    "brca_metabric": "乳腺癌 METABRIC 临床与分子队列",
    "GSE76360": "HER2 阳性乳腺癌术前曲妥珠单抗响应队列",
    "GSE25066": "乳腺癌新辅助化疗响应与生存队列",
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
            sample_id = str(raw.get("sampleId") or patient_id).strip()
            if not patient_id and not sample_id:
                continue
            key = (patient_id or sample_id, sample_id or patient_id)
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
                    "sample_id": patient_id,
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

        cleaning_actions = [
            "以临床样本表作为队列锚点，未把无临床信息的分子记录扩成新患者。",
            "将缺失哨兵统一为空值，并统一常见中英文分类值。",
            "同一患者的临床属性传播到其样本，但不跨患者补值。",
        ]
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
        characteristics: list[list[str]] = []
        try:
            with gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="") as handle:
                for line in handle:
                    if line.startswith("!series_matrix_table_begin"):
                        break
                    if not line.startswith("!Sample_"):
                        continue
                    fields = next(csv.reader([line.rstrip("\r\n")], delimiter="\t"))
                    if len(fields) < 2:
                        continue
                    key = fields[0].removeprefix("!Sample_")
                    values = fields[1:]
                    if key == "characteristics_ch1":
                        characteristics.append(values)
                    elif key in {"title", "geo_accession"}:
                        sample_data[key] = values
        except (OSError, EOFError, csv.Error):
            return None

        accessions = sample_data.get("geo_accession", [])
        titles = sample_data.get("title", [])
        if not accessions:
            return None
        rows: list[dict[str, Any]] = []
        cleaned_values = 0
        for index, sample_id in enumerate(accessions):
            raw_items = [values[index] for values in characteristics if index < len(values)]
            parsed: dict[str, Any] = {}
            for raw_item in raw_items:
                field, separator, raw_value = raw_item.partition(":")
                if not separator:
                    continue
                normalized_field = re.sub(r"[^a-z0-9]+", "_", field.casefold()).strip("_")
                value, changed = self._clean_value(raw_value)
                parsed[normalized_field] = value
                cleaned_values += int(changed)
            subject = str(parsed.get("subject_id") or "").strip()
            row = {
                "study_id": result.accession,
                "patient_id": f"{result.accession}-{subject}" if subject else None,
                "sample_id": sample_id,
                "source_id": resource.source_item.source_id,
                "sample_title": titles[index] if index < len(titles) else None,
                "disease": parsed.get("patient_status"),
                "timepoint": parsed.get("timepoint"),
                "treatment_response": parsed.get("response_at_surgery"),
                "er_status": parsed.get("er_status"),
                "pr_status": parsed.get("pr_status"),
                "response_domain": "患者临床响应",
                "raw_characteristics": "；".join(raw_items),
            }
            rows.append(row)

        baseline_rows = [row for row in rows if row.get("timepoint") == "基线"]
        filtered_count = len(rows) - len(baseline_rows)
        if baseline_rows:
            rows = baseline_rows
        rows, duplicate_count = self._deduplicate_rows(rows, "sample_id")
        cleaning_actions = [
            "解析 GEO Series Matrix 的真实样本元数据并保留原始 characteristics。",
            "统一疾病、受体状态、取样时间点和术后响应的分类值。",
        ]
        if filtered_count:
            cleaning_actions.append(
                f"主分析表保留 {len(rows)} 个基线样本，分离 {filtered_count} 个治疗后配对样本，避免同一患者跨分析分区。"
            )
        dataset = self._dataset_from_rows(
            rows,
            name=f"{DATASET_NAMES.get(result.accession, result.accession)}科研数据集",
            unit="基线患者样本（一名患者一行）",
            spec=spec,
        )
        report = self._readiness(
            dataset,
            spec,
            cleaned_value_count=cleaned_values,
            duplicate_row_count=duplicate_count,
            cleaning_actions=cleaning_actions,
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
        ordered_names = self._ordered_columns(rows)
        columns = [self._describe_column(name, rows) for name in ordered_names]
        normalized_rows = [{name: row.get(name) for name in ordered_names} for row in rows]
        target = self._select_target(ordered_names, spec)
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

        target_match = dataset.target_column is not None
        if not target_match:
            requested = "、".join(spec.outcomes) or "当前科研问题指定的结局"
            warnings.append(f"当前队列不含与“{requested}”匹配的研究结局；系统未用生存结局冒充治疗响应。")
            recommendations.append("更换为含目标结局的独立队列，不对不同患者来源的数据进行强行补值或横向拼接。")
        if truncated:
            warnings.append("以下上游表仍受最大记录数限制：" + "、".join(truncated) + "。")
            recommendations.append("提高最大记录数或改用能够完整下载的队列文件；截断的突变缺失不能解释为野生型。")
        if repeated_count:
            warnings.append(f"发现 {repeated_count} 名患者对应多个样本，随机按行切分会造成数据泄漏。")

        target_missing_rate: float | None = None
        nonmissing_classes: set[str] = set()
        if dataset.target_column:
            target_values = [row.get(dataset.target_column) for row in dataset.rows]
            missing = sum(value in {None, ""} for value in target_values)
            target_missing_rate = missing / dataset.row_count if dataset.row_count else 1.0
            nonmissing_classes = {str(value) for value in target_values if value not in {None, ""}}
            if target_missing_rate > 0.2:
                warnings.append(f"研究结局缺失率为 {target_missing_rate:.1%}，需要预先定义纳入/排除规则。")
            if len(nonmissing_classes) <= 1:
                warnings.append("非缺失研究结局只有一个类别，无法进行可靠的分组比较。")

        field_completeness_rate = self._field_completeness(dataset)
        variable_coverage = self._requested_variable_coverage(dataset, spec)
        if variable_coverage is not None and variable_coverage < 1:
            covered = round(variable_coverage * len(spec.genes))
            warnings.append(f"请求的基因变量仅覆盖 {covered}/{len(spec.genes)}；当前队列不能单独回答完整基因假设。")
            recommendations.append("把该队列用于治疗响应/受体分层；基因假设需选择同时具有分子检测和同一患者结局的队列。")

        analysis_ready = bool(
            dataset.row_count >= 30
            and target_match
            and not truncated
            and (target_missing_rate or 0) <= 0.2
            and len(nonmissing_classes) > 1
            and (variable_coverage is None or variable_coverage == 1)
        )
        if analysis_ready:
            status = "可支持科研分析"
        elif not target_match:
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
    def _ordered_columns(rows: list[dict[str, Any]]) -> list[str]:
        fixed = ["study_id", "patient_id", "sample_id", "source_id"]
        dynamic = sorted({key for row in rows for key in row} - set(fixed))
        return [name for name in fixed if any(name in row for row in rows)] + dynamic

    @staticmethod
    def _select_target(columns: list[str], spec: ResearchSpec) -> str | None:
        outcome_text = " ".join(spec.outcomes).lower()
        if any(term in outcome_text for term in ("pcr", "pathological", "response", "响应", "疗效", "缓解")):
            priority = ["pcr", "treatment_response"]
        elif any(term in outcome_text for term in ("survival", " os ", "dfs", "生存")):
            priority = ["os_status", "os_months", "dfs_status", "dfs_months"]
        else:
            priority = []
        return next((name for name in priority if name in columns), None)

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
        if not spec.genes:
            return None
        names = {column.name.casefold() for column in dataset.columns}
        covered = sum(any(name.startswith(gene.casefold() + "_") for name in names) for gene in spec.genes)
        return covered / len(spec.genes)

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
    def _describe_column(name: str, rows: list[dict[str, Any]]) -> DatasetColumn:
        values = [row.get(name) for row in rows if row.get(name) is not None]
        data_type = "number" if values and all(isinstance(value, (int, float)) for value in values) else "string"
        if name in {"study_id", "patient_id", "sample_id"}:
            role = "标识符"
        elif name in {"source_id", "raw_characteristics"}:
            role = "审计信息"
        elif name in {"pcr", "treatment_response", "os_status", "dfs_status"}:
            role = "研究结局"
        else:
            role = "研究变量"
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
        else:
            label = CHINESE_LABELS.get(name, name.replace("_", " "))
            description = FIELD_DESCRIPTIONS.get(
                name,
                f"来自上游字段 {name}；用于分析前应在原研究数据字典中确认定义、单位和时间点。",
            )
        return DatasetColumn(
            name=name,
            label_zh=label,
            data_type=data_type,
            role=role,
            source_field=name,
            description=description,
        )
