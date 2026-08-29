from __future__ import annotations

from pathlib import Path

import yaml

from backend.app.contracts.models import FrozenResearchContract


ROOT = Path(__file__).resolve().parents[2]


class RulePackEngine:
    """Load additive YAML rule packs. Does not replace frozen medical_rules.yaml."""

    def __init__(self, rules_dir: Path | None = None) -> None:
        self.rules_dir = rules_dir or ROOT / "configs" / "rules"

    def publication_gates(self) -> list[str]:
        payload = yaml.safe_load((self.rules_dir / "publication.yaml").read_text(encoding="utf-8")) or {}
        return list(payload.get("gates") or [])

    def her2_ihc_2plus_action(self, assay: str, raw_value: str) -> str:
        value = raw_value.strip().casefold().replace(" ", "")
        if assay.casefold() == "ihc" and value in {"2+", "ihc2+", "her2ihc2+"}:
            return "REVIEW"
        return "ALLOW"

    def block_publish_without_provenance(self, source_id: str | None, raw_field: str | None, raw_value: object) -> bool:
        return not source_id or not raw_field or raw_value in {None, ""}

    def contract_publication_ready(self, contract: FrozenResearchContract, *, provenance_complete: bool, forbidden_join: bool, identity_passed: bool) -> tuple[bool, list[str]]:
        failures: list[str] = []
        if not contract.required_fields:
            failures.append("required_fields_present")
        if contract.provenance_required and not provenance_complete:
            failures.append("provenance_complete")
        if forbidden_join:
            failures.append("no_forbidden_join")
        if not identity_passed:
            failures.append("identity_gate_passed")
        if contract.response_domain not in {"clinical", "preclinical", "none"}:
            failures.append("response_domain_valid")
        return not failures, failures
