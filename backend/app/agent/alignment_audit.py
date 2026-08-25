from __future__ import annotations

from collections import Counter
from typing import Any

from backend.app.agent.models import (
    DataAlignmentReport,
    DataAlignmentSource,
)


class DataAlignmentAuditor:
    """Describe identity and provenance boundaries without inventing cross-source matches."""

    def build(self, dataset: Any, source_items: list[Any]) -> DataAlignmentReport:
        rows = list(getattr(dataset, "rows", []) or [])
        row_count = len(rows)
        patient_ids = {
            str(row.get("patient_id")).strip()
            for row in rows
            if row.get("patient_id") not in (None, "")
        }
        sample_ids = {
            str(row.get("sample_id")).strip()
            for row in rows
            if row.get("sample_id") not in (None, "")
        }
        study_ids = {
            str(row.get("study_id")).strip()
            for row in rows
            if row.get("study_id") not in (None, "")
        }
        row_source_ids = {
            str(row.get("source_id")).strip()
            for row in rows
            if row.get("source_id") not in (None, "")
        }
        unresolved_rows = sum(
            row.get("patient_id") in (None, "")
            and row.get("sample_id") in (None, "")
            for row in rows
        )
        patient_rate = len(
            [row for row in rows if row.get("patient_id") not in (None, "")]
        ) / row_count if row_count else None
        sample_rate = len(
            [row for row in rows if row.get("sample_id") not in (None, "")]
        ) / row_count if row_count else None

        identity_keys = [
            (
                str(row.get("study_id") or ""),
                str(row.get("patient_id") or ""),
                str(row.get("sample_id") or ""),
            )
            for row in rows
        ]
        duplicate_identity_count = sum(
            count - 1 for count in Counter(identity_keys).values() if count > 1
        )

        same_study = len(study_ids) == 1 if row_count else None
        same_source = len(row_source_ids) == 1 if row_count else None
        if not rows:
            status = "无法判定"
            entity_match_status = "UNMATCH"
            note = "当前没有患者/样本级主表，不能判断编号对齐或来源一致性。"
            entity_match_note = "无主表行，实体匹配为 UNMATCH；禁止无证据合并患者。"
        elif same_study and same_source and patient_rate == 1 and sample_rate == 1:
            status = "同一研究内可对齐"
            entity_match_status = "MATCH"
            note = (
                "主表每行都有研究编号、患者编号、样本编号和行级 source_id；"
                "当前可在这一研究空间内对齐，不能据此推断其他数据库中的同名编号是同一患者。"
            )
            entity_match_note = "MATCH：同一研究、同一来源内患者/样本编号完整，仅在该命名空间内关联。"
        elif same_study and same_source:
            status = "同一研究内部分可对齐"
            entity_match_status = "REVIEW"
            note = (
                "主表来源和研究编号一致，但仍有患者编号或样本编号缺失；"
                "缺失行不能自动补成同一患者。"
            )
            entity_match_note = "REVIEW：同一研究内仍有身份缺失，低置信度关联不得自动合并。"
        else:
            status = "混合边界，不能直接合并"
            entity_match_status = "UNMATCH"
            note = (
                "主表包含多个研究或多个来源标识；这些编号属于不同命名空间，"
                "没有经过可审计的身份映射前不能视为同一患者队列。"
            )
            entity_match_note = "UNMATCH：跨研究或跨来源编号不能直接合并，系统未执行跨患者拼接。"

        source_by_id = {
            str(getattr(item, "source_id", "")): item
            for item in source_items
            if getattr(item, "source_id", None)
        }
        sources: list[DataAlignmentSource] = []
        all_source_ids = list(dict.fromkeys([*row_source_ids, *source_by_id.keys()]))
        for source_id in all_source_ids:
            item = source_by_id.get(source_id)
            source_rows = [row for row in rows if str(row.get("source_id") or "") == source_id]
            source_patient_ids = {
                str(row.get("patient_id")).strip()
                for row in source_rows
                if row.get("patient_id") not in (None, "")
            }
            source_sample_ids = {
                str(row.get("sample_id")).strip()
                for row in source_rows
                if row.get("sample_id") not in (None, "")
            }
            sources.append(
                DataAlignmentSource(
                    source_id=source_id,
                    source_name=str(getattr(item, "source_name", None) or "主表行级来源"),
                    source_type=str(getattr(item, "source_type", None) or "未说明"),
                    accession=getattr(item, "accession", None),
                    url=getattr(item, "url", None),
                    role="主数据集来源" if source_rows else "已检索但未进入主表",
                    row_count=len(source_rows),
                    patient_count=len(source_patient_ids),
                    sample_count=len(source_sample_ids),
                    study_ids=sorted(
                        {
                            str(row.get("study_id")).strip()
                            for row in source_rows
                            if row.get("study_id") not in (None, "")
                        }
                    ),
                    note=(
                        "该 source_id 出现在主表行中，可回溯到官方来源。"
                        if source_rows
                        else "本次已登记但未被选为主数据集，不能用于补填患者字段。"
                    ),
                )
            )

        source_names = sorted(
            {
                source.source_name
                for source in sources
                if source.role == "主数据集来源"
            }
        )
        return DataAlignmentReport(
            status=status,
            scope="当前主科研数据集",
            identity_namespace="study_id + 来源内原始 patient_id / sample_id",
            alignment_basis=[
                "同一 study_id 内按原始 patient_id 进行患者级分组。",
                "同一 study_id 内按原始 sample_id 连接样本级临床和分子记录。",
                "缺失或低置信度身份不跨患者、不跨研究自动补值。",
            ],
            row_count=row_count,
            patient_count=len(patient_ids),
            sample_count=len(sample_ids),
            study_count=len(study_ids),
            source_count=len(row_source_ids),
            patient_id_coverage_rate=patient_rate,
            sample_id_coverage_rate=sample_rate,
            same_study=same_study,
            same_source=same_source,
            unresolved_identity_row_count=unresolved_rows,
            duplicate_identity_count=duplicate_identity_count,
            cross_source_join_performed=False,
            cross_source_join_status="未执行跨来源患者合并",
            primary_source_names=source_names,
            sources=sources,
            limitations=[
                "不同数据库的患者编号通常只在各自研究内部有意义，不能仅凭字符串相同认定为同一患者。",
                "source_id 标识文件、接口资源或证据项，不等于患者身份标识。",
                "GEO 等公开队列可能没有真实患者编号，系统使用研究前缀加原始 subject 标识构造隔离命名空间，并保留原始样本特征。",
            ],
            note=note,
            entity_match_status=entity_match_status,
            entity_match_note=entity_match_note,
        )
