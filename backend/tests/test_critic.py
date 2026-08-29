from __future__ import annotations

from backend.app.contracts.models import FrozenResearchContract, PopulationSpec, VariableSpec
from backend.app.critic import CriticAgent
from backend.app.rules import RulePackEngine


def _contract() -> FrozenResearchContract:
    return FrozenResearchContract(
        contract_id="contract-test",
        research_goal="PIK3CA vs pCR",
        population=PopulationSpec(disease="breast cancer", subtype="HER2-positive"),
        exposure=VariableSpec(name="PIK3CA"),
        outcome=VariableSpec(name="pCR"),
        required_fields=[],
        literature_evidence_count=1,
        generation_source="EVIDENCE_AGENT",
        status="FROZEN",
    )


def test_round1_missing_outcome_then_not_all_met() -> None:
    report = CriticAgent().diagnose(contract=_contract(), required_coverage={"pCR": 0.0, "PIK3CA_mutation": 1.0}, row_count=40, target_match=False)
    types = {item.diagnosis_type for item in report.diagnoses}
    assert "OUTCOME_MISMATCH" in types or "MISSING_OUTCOME" in types
    assert report.answers_contract is False


def test_all_met_when_coverage_complete() -> None:
    report = CriticAgent().diagnose(contract=_contract(), required_coverage={"pCR": 1.0}, row_count=50, target_match=True)
    assert report.diagnoses[0].diagnosis_type == "ALL_MET"
    assert report.answers_contract is True


def test_her2_ihc_2plus_not_auto_positive() -> None:
    engine = RulePackEngine()
    assert engine.her2_ihc_2plus_action("IHC", "2+") == "REVIEW"
    assert engine.her2_ihc_2plus_action("IHC", "3+") == "ALLOW"


def test_missing_provenance_blocks_publish() -> None:
    engine = RulePackEngine()
    assert engine.block_publish_without_provenance(None, "her2_status", "Positive") is True
    assert engine.block_publish_without_provenance("geo:1", "her2_status", "Positive") is False
