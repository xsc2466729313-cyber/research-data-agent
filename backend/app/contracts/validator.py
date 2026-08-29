from __future__ import annotations

from backend.app.contracts.models import FrozenResearchContract


class ContractValidationError(ValueError):
    pass


class ContractValidator:
    """Deterministic gates before a contract may be frozen."""

    def validate(self, contract: FrozenResearchContract) -> list[str]:
        warnings: list[str] = []
        if not contract.research_goal.strip():
            raise ContractValidationError("Research Contract 缺少 research_goal。")
        if not contract.required_fields:
            raise ContractValidationError("Research Contract 必须包含 required_fields。")
        if contract.provenance_required is False:
            warnings.append("关闭 provenance_required 违反生产默认，冻结时仍强制保留来源。")
        if contract.response_domain == "preclinical" and contract.data_granularity == "patient":
            warnings.append("preclinical response 不能作为 patient-level 临床疗效。")
        if contract.generation_source != "EVIDENCE_AGENT":
            warnings.append("当前合同来自 GENERIC_FALLBACK 或模板，冻结后仍须补充论文 Evidence 才能正式取数。")
        if contract.literature_evidence_count == 0:
            warnings.append("没有可核验论文 Evidence；冻结只锁定需求，不证明数据已存在。")
        missing = [item.field_id for item in contract.required_fields if item.evidence_status == "missing"]
        if missing:
            warnings.append("Required 字段缺少论文 Evidence：" + "、".join(missing))
        return warnings

    def can_freeze(self, contract: FrozenResearchContract) -> tuple[bool, str]:
        if contract.status == "FROZEN":
            return True, "合同已经冻结。"
        try:
            self.validate(contract)
        except ContractValidationError as exc:
            return False, str(exc)
        return True, "用户确认后可冻结数据需求。"
