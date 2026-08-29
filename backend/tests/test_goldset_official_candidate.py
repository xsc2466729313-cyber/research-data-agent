from __future__ import annotations

import csv
import json
from pathlib import Path

from backend.app.evaluation import GoldSetCsvLoader
from backend.app.evaluation.goldset import REQUIRED_HEADERS, compute_gold_set_checksum
from backend.app.evaluation.models import GoldSetManifest, ReviewStatus, RiskLevel


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = ROOT / "goldset" / "breast_cancer" / "official_candidate"
DEV = ROOT / "goldset" / "breast_cancer" / "development"
TEMPLATES = ROOT / "goldset" / "templates"


def _envelope(directory: Path) -> dict:
    return json.loads((directory / "MANIFEST.json").read_text(encoding="utf-8"))


def _csv_questions(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["research_question"].strip() for row in csv.DictReader(handle)}


def _csv_ids(path: Path, column: str) -> set[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row[column].strip() for row in csv.DictReader(handle)}


def test_official_candidate_approved_by_xsc_and_copied_to_templates() -> None:
    envelope = _envelope(CANDIDATE)
    assert envelope["split"] == "official_candidate"
    assert envelope["not_frozen_test"] is True
    assert envelope["copied_to_templates"] is True
    assert envelope["frozen"] is False
    dumped = json.dumps(envelope, ensure_ascii=False)
    assert "66.94" not in dumped
    assert envelope["manifest"]["frozen"] is False
    assert envelope["manifest"].get("sdti") is None
    assert envelope["reviewed_by"] == "xsc"

    manifest = GoldSetManifest.model_validate(envelope["manifest"])
    assert manifest.gold_set_id == "breast-cancer-official-candidate-20260829"
    assert manifest.frozen is False
    assert manifest.initial_labeler == "official-candidate-draft-builder"
    assert manifest.independent_reviewer == "xsc"
    assert manifest.human_reviewer == "xsc"
    assert manifest.deterministic_rules_verified is False
    assert manifest.source_references_verified is False
    assert manifest.high_risk_review_complete is True

    bundle = GoldSetCsvLoader().load(CANDIDATE, manifest)
    assert envelope["row_counts"] == {
        "retrieval_gold.csv": len(bundle.retrieval_gold),
        "field_gold.csv": len(bundle.field_gold),
        "error_gold.csv": len(bundle.error_gold),
    }
    assert 30 <= len(bundle.retrieval_gold) < 53
    assert 20 <= len(bundle.field_gold) <= 34
    assert 12 <= len(bundle.error_gold) < 22
    rows = [*bundle.retrieval_gold, *bundle.field_gold, *bundle.error_gold]
    assert all(item.review_status is ReviewStatus.APPROVED for item in rows)
    assert compute_gold_set_checksum(bundle) == manifest.gold_set_checksum

    assert any(
        item.canonical_field == "her2_status" and item.canonical_value == "Equivocal"
        for item in bundle.field_gold
    )
    assert any(
        item.canonical_field == "her2_status" and item.canonical_value == "Unknown"
        and "CNA" in item.raw_field.upper()
        for item in bundle.field_gold
    )
    assert any(
        item.canonical_field == "response_domain"
        and item.canonical_value == "preclinical_cell_line"
        for item in bundle.field_gold
    )
    assert any(item.raw_field and item.raw_value is not None for item in bundle.field_gold)
    assert any(
        item.error_type == "her2_assay_error"
        and item.auto_repair_allowed is False
        and item.risk_level is RiskLevel.HIGH
        for item in bundle.error_gold
    )
    assert any("AUTO_MERGE" in item.original_record for item in bundle.error_gold)
    assert any("pCR" in item.original_record and "depmap" in item.original_record.lower() for item in bundle.error_gold)

    retrieved_ids = {item.dataset_id for item in bundle.retrieval_gold if item.label.value == "relevant"}
    assert {"GSE25066", "GSE50948", "GSE76360", "NCT01104584", "DepMap", "CIViC"} <= retrieved_ids
    assert all(item.dataset_id for item in bundle.retrieval_gold)


def test_templates_hold_official_candidate_rows_not_development() -> None:
    for filename, headers in REQUIRED_HEADERS.items():
        with (CANDIDATE / filename).open("r", encoding="utf-8-sig", newline="") as handle:
            actual = csv.DictReader(handle).fieldnames
        assert actual == headers
        with (TEMPLATES / filename).open("r", encoding="utf-8-sig", newline="") as handle:
            template_headers = csv.DictReader(handle).fieldnames
        assert template_headers == headers

    inspection = GoldSetCsvLoader().inspect(TEMPLATES)
    assert inspection.row_counts == {
        "retrieval_gold.csv": 50,
        "field_gold.csv": 26,
        "error_gold.csv": 18,
    }
    assert inspection.status.value == "NOT_EVALUATED"
    assert "仍需要冻结" in inspection.notice or "系统观察" in inspection.notice

    templates_envelope = _envelope(TEMPLATES)
    candidate_envelope = _envelope(CANDIDATE)
    assert templates_envelope["copied_to_templates"] is True
    assert templates_envelope["manifest"]["gold_set_checksum"] == candidate_envelope["manifest"]["gold_set_checksum"]
    assert templates_envelope["manifest"]["independent_reviewer"] == "xsc"

    manifest = GoldSetManifest.model_validate(templates_envelope["manifest"])
    template_bundle = GoldSetCsvLoader().load(TEMPLATES, manifest)
    candidate_bundle = GoldSetCsvLoader().load(CANDIDATE, manifest)
    assert compute_gold_set_checksum(template_bundle) == compute_gold_set_checksum(candidate_bundle)
    assert {item.question_id for item in template_bundle.retrieval_gold} == {
        item.question_id for item in candidate_bundle.retrieval_gold
    }
    assert _csv_questions(TEMPLATES / "retrieval_gold.csv") == _csv_questions(CANDIDATE / "retrieval_gold.csv")
    assert _csv_questions(TEMPLATES / "retrieval_gold.csv").isdisjoint(_csv_questions(DEV / "retrieval_gold.csv"))
    assert _csv_ids(TEMPLATES / "retrieval_gold.csv", "question_id").isdisjoint(
        _csv_ids(DEV / "retrieval_gold.csv", "question_id")
    )
    assert "q01_neoadjuvant_pcr" not in _csv_ids(TEMPLATES / "retrieval_gold.csv", "question_id")
    for filename in REQUIRED_HEADERS:
        text = (TEMPLATES / filename).read_text(encoding="utf-8-sig")
        assert "66.94" not in text
        assert "SDTI" not in text


def test_official_candidate_does_not_copy_development_items() -> None:
    cand_questions = _csv_questions(CANDIDATE / "retrieval_gold.csv")
    dev_questions = _csv_questions(DEV / "retrieval_gold.csv")
    assert cand_questions
    assert cand_questions.isdisjoint(dev_questions)

    assert _csv_ids(CANDIDATE / "retrieval_gold.csv", "question_id").isdisjoint(
        _csv_ids(DEV / "retrieval_gold.csv", "question_id")
    )
    assert _csv_ids(CANDIDATE / "field_gold.csv", "case_id").isdisjoint(
        _csv_ids(DEV / "field_gold.csv", "case_id")
    )
    assert _csv_ids(CANDIDATE / "error_gold.csv", "case_id").isdisjoint(
        _csv_ids(DEV / "error_gold.csv", "case_id")
    )

    for filename in REQUIRED_HEADERS:
        text = (CANDIDATE / filename).read_text(encoding="utf-8-sig")
        assert "66.94" not in text
        assert "SDTI" not in text
