from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from backend.app.evaluation.models import RiskLevel
from backend.app.repair.errors import RepairError, RepairErrorCode
from backend.app.repair.models import (
    ErrorFinding,
    PolicyAction,
    RepairErrorType,
    RepairPolicyDecision,
)


ROOT = Path(__file__).resolve().parents[3]


class RepairPolicy:
    """Fail-closed policy derived from the frozen medical safety allowlist."""

    _AUTO_RULES = {
        RepairErrorType.EXACT_DUPLICATE: "exact_duplicate",
        RepairErrorType.GENE_ALIAS: "gene_alias_exact",
        RepairErrorType.DRUG_ALIAS: "drug_alias_exact",
        RepairErrorType.CASING_NORMALIZATION: "casing_normalization",
    }
    _BLOCK_TYPES = {
        RepairErrorType.PROVENANCE_MISSING,
        RepairErrorType.MISSING_REQUIRED_FIELD,
        RepairErrorType.INVALID_SCHEMA_VALUE,
    }

    def __init__(self, *, medical_rules_path: Path | None = None) -> None:
        self.medical_rules_path = (
            medical_rules_path or ROOT / "configs" / "medical_rules.yaml"
        )
        self.rules = self._load_rules(self.medical_rules_path)
        self.auto_fix = set(self.rules["auto_fix"])
        self.version = f"medical-rules-v{self.rules['version']}"

    def decide(self, findings: list[ErrorFinding]) -> list[RepairPolicyDecision]:
        guarded_record_ids = {
            record_id
            for finding in findings
            if finding.risk_level == RiskLevel.HIGH
            or finding.error_type in self._BLOCK_TYPES
            for record_id in finding.record_ids
        }
        return [
            self._decision(finding, guarded_record_ids=guarded_record_ids)
            for finding in findings
        ]

    def _decision(
        self,
        finding: ErrorFinding,
        *,
        guarded_record_ids: set[str],
    ) -> RepairPolicyDecision:
        overlap = sorted(set(finding.record_ids) & guarded_record_ids)
        auto_rule = self._AUTO_RULES.get(finding.error_type)
        if finding.error_type in self._BLOCK_TYPES:
            action = PolicyAction.BLOCK
            policy_rule = "block_invalid_or_missing_evidence"
            rationale = (
                "The record cannot satisfy the frozen publication contract without "
                "inventing or coercing source data."
            )
        elif finding.risk_level == RiskLevel.HIGH:
            action = PolicyAction.REVIEW
            policy_rule = "manual_or_model_review"
            rationale = (
                "High-risk medical semantics or identity conflicts are never decided "
                "automatically."
            )
        elif overlap:
            action = PolicyAction.REVIEW
            policy_rule = "guarded_record_fail_closed"
            rationale = (
                "A deterministic edit was suppressed because the same record has an "
                f"unresolved high-risk or blocking finding: {overlap}."
            )
        elif (
            auto_rule is not None
            and auto_rule in self.auto_fix
            and finding.deterministic
            and finding.candidate_repair is not None
        ):
            action = PolicyAction.AUTO_REPAIR
            policy_rule = auto_rule
            rationale = (
                "The finding has an exact deterministic candidate included in the "
                "medical_rules.yaml auto-fix allowlist."
            )
        else:
            action = PolicyAction.REVIEW
            policy_rule = "manual_or_model_review"
            rationale = (
                "The finding is not an allowlisted deterministic repair and remains "
                "unchanged for review."
            )
        material = {
            "finding_id": finding.finding_id,
            "action": action.value,
            "policy_rule": policy_rule,
            "policy_version": self.version,
        }
        digest = hashlib.sha256(self._json(material).encode("utf-8")).hexdigest()[:24]
        return RepairPolicyDecision(
            decision_id=f"decision:{digest}",
            finding_id=finding.finding_id,
            error_type=finding.error_type,
            action=action,
            policy_rule=policy_rule,
            policy_version=self.version,
            rationale=rationale,
        )

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

    @staticmethod
    def _load_rules(path: Path) -> dict[str, Any]:
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("medical rules must be a mapping")
            if not isinstance(value.get("version"), str):
                raise ValueError("medical rules version is required")
            if not isinstance(value.get("auto_fix"), list):
                raise ValueError("medical rules auto_fix must be a list")
            if not isinstance(value.get("manual_or_model_review"), list):
                raise ValueError("medical rules manual_or_model_review must be a list")
            return value
        except (OSError, ValueError, yaml.YAMLError) as exc:
            raise RepairError(
                RepairErrorCode.INVALID_CONFIGURATION,
                f"Cannot load medical repair policy: {exc}",
                details={"path": str(path)},
            ) from exc
