from __future__ import annotations

from backend.app.contracts.models import FrozenResearchContract
from backend.app.critic.models import CriticReport, GapDiagnosis


class CriticAgent:
    """Judge whether current data can answer the frozen Research Contract."""

    def diagnose(
        self,
        *,
        contract: FrozenResearchContract | None = None,
        required_coverage: dict[str, float] | None = None,
        target_match: bool | None = None,
        row_count: int = 0,
        forbidden_join: bool = False,
        unresolved_identity: bool = False,
        provenance_complete: bool = True,
        parsing_failed: bool = False,
        semantic_conflict: bool = False,
    ) -> CriticReport:
        coverage = required_coverage or {}
        diagnoses: list[GapDiagnosis] = []
        if row_count <= 0:
            diagnoses.append(
                GapDiagnosis(
                    diagnosis_type="NO_PATIENT_TABLE",
                    severity="blocker",
                    evidence=["尚无患者/样本主表。"],
                    recommended_actions=["search_dataset_catalog", "fetch_dataset"],
                )
            )
        missing = [field_id for field_id, value in coverage.items() if value <= 0]
        required_ids = [item.field_id for item in contract.required_fields] if contract else list(coverage)
        outcome_fields = [item.field_id for item in (contract.required_fields if contract else []) if item.role in {"outcome", "primary_outcome"}]
        exposure_fields = [item.field_id for item in (contract.required_fields if contract else []) if item.role in {"exposure", "primary_exposure"}]
        if any(field in missing for field in outcome_fields) or target_match is False:
            diagnoses.append(
                GapDiagnosis(
                    diagnosis_type="MISSING_OUTCOME" if target_match is not False else "OUTCOME_MISMATCH",
                    severity="blocker",
                    affected_fields=outcome_fields or missing,
                    evidence=[
                        "结局字段覆盖不足或与 Research Contract 的 response_domain 不一致。",
                        "若当前是生存队列而合同要 pCR，应换 GSE25066/GSE76360/NCT，禁止用 OS 冒充 pCR。",
                    ],
                    recommended_actions=["search_geo", "search_trials", "inspect_dataset_schema"],
                )
            )
        if any(field in missing for field in exposure_fields):
            diagnoses.append(
                GapDiagnosis(
                    diagnosis_type="MISSING_EXPOSURE",
                    severity="blocker",
                    affected_fields=exposure_fields,
                    evidence=["暴露/分子变量未在同一可审计队列中出现。"],
                    recommended_actions=["search_dataset_catalog"],
                )
            )
        leftover = [field for field in missing if field not in outcome_fields and field not in exposure_fields]
        if leftover:
            diagnoses.append(
                GapDiagnosis(
                    diagnosis_type="MISSING_COVARIATES",
                    severity="warning",
                    affected_fields=leftover,
                    evidence=["部分 Required 协变量仍未覆盖。"],
                    recommended_actions=["inspect_dataset_schema"],
                )
            )
        if unresolved_identity:
            diagnoses.append(
                GapDiagnosis(
                    diagnosis_type="IDENTITY_UNRESOLVED",
                    severity="blocker",
                    evidence=["存在低置信度患者/样本关联。"],
                    recommended_actions=["submit_review"],
                )
            )
        if forbidden_join:
            diagnoses.append(
                GapDiagnosis(
                    diagnosis_type="FORBIDDEN_JOIN",
                    severity="blocker",
                    evidence=["无 crosswalk 的跨队列患者级 Join 已被禁止。"],
                    recommended_actions=["keep_independent_cohorts"],
                )
            )
        if contract is not None and contract.literature_evidence_count == 0:
            diagnoses.append(
                GapDiagnosis(
                    diagnosis_type="MISSING_EVIDENCE",
                    severity="warning",
                    evidence=["合同缺少论文 Evidence。"],
                    recommended_actions=["search_literature"],
                )
            )
        if not provenance_complete:
            diagnoses.append(
                GapDiagnosis(
                    diagnosis_type="MISSING_EVIDENCE",
                    severity="blocker",
                    evidence=["关键字段缺少 source_id/raw_field/raw_value。"],
                    recommended_actions=["check_provenance"],
                )
            )
        if parsing_failed:
            diagnoses.append(
                GapDiagnosis(
                    diagnosis_type="PARSING_FAILURE",
                    severity="warning",
                    evidence=["解析失败，已标记 REVIEW，未让模型猜值。"],
                    recommended_actions=["parse_table"],
                )
            )
        if semantic_conflict:
            diagnoses.append(
                GapDiagnosis(
                    diagnosis_type="SEMANTIC_CONFLICT",
                    severity="blocker",
                    evidence=["存在不可自动选边的医学语义冲突。"],
                    recommended_actions=["submit_review"],
                )
            )
        if not diagnoses:
            diagnoses.append(
                GapDiagnosis(
                    diagnosis_type="ALL_MET",
                    severity="info",
                    evidence=["当前数据按合同检查未发现阻断性缺口。"],
                    recommended_actions=[],
                )
            )
        elif leftover and not any(item.severity == "blocker" for item in diagnoses):
            diagnoses.append(
                GapDiagnosis(
                    diagnosis_type="RESIDUAL_GAPS",
                    severity="warning",
                    affected_fields=leftover,
                    evidence=["仍有非阻断缺口。"],
                    recommended_actions=["run_quality"],
                )
            )
        answers = all(item.diagnosis_type == "ALL_MET" for item in diagnoses)
        unused_required = [field_id for field_id in required_ids if coverage.get(field_id, 1.0) <= 0]
        notice = (
            "当前数据可以对照 Research Contract 继续导出。"
            if answers
            else "当前数据还不能完整回答冻结需求；Critic 只诊断，不直接改写数据。"
        )
        if unused_required and answers:
            notice = "覆盖检查与合同字段不完全一致，请复核。"
        return CriticReport(
            contract_id=contract.contract_id if contract else None,
            answers_contract=answers,
            diagnoses=diagnoses,
            notice=notice,
        )
