from __future__ import annotations

import csv
import json
from pathlib import Path

from backend.app.evaluation import GoldSetCsvLoader
from backend.app.evaluation.goldset import compute_gold_set_checksum
from backend.app.evaluation.models import GoldSetManifest, ReviewStatus, RiskLevel


ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "goldset" / "breast_cancer" / "development"


def _frozen_envelope() -> dict:
    return json.loads((DEV / "MANIFEST.json").read_text(encoding="utf-8"))


def test_development_gold_is_frozen_by_xsc_not_copied_to_templates() -> None:
    envelope = _frozen_envelope()
    assert envelope["split"] == "development"
    assert envelope["not_frozen_test"] is True
    assert envelope["copied_to_templates"] is False

    manifest = GoldSetManifest.model_validate(envelope["manifest"])
    assert manifest.frozen is True
    assert manifest.initial_labeler == "development-draft-builder"
    assert manifest.independent_reviewer == "xsc"
    assert manifest.human_reviewer == "xsc"
    assert manifest.deterministic_rules_verified is True
    assert manifest.source_references_verified is True
    assert manifest.high_risk_review_complete is True

    bundle = GoldSetCsvLoader().load(DEV, manifest)
    assert envelope["row_counts"] == {
        "retrieval_gold.csv": len(bundle.retrieval_gold),
        "field_gold.csv": len(bundle.field_gold),
        "error_gold.csv": len(bundle.error_gold),
    }
    assert len(bundle.retrieval_gold) >= 50
    assert len(bundle.field_gold) >= 30
    assert len(bundle.error_gold) >= 20
    rows = [*bundle.retrieval_gold, *bundle.field_gold, *bundle.error_gold]
    assert all(item.review_status is ReviewStatus.APPROVED for item in rows)
    assert compute_gold_set_checksum(bundle) == manifest.gold_set_checksum
    assert any(item.canonical_value == "Equivocal" for item in bundle.field_gold)
    assert any(
        item.error_type == "her2_assay_error"
        and item.auto_repair_allowed is False
        and item.risk_level is RiskLevel.HIGH
        for item in bundle.error_gold
    )

    verification = json.loads((DEV / "SOURCE_VERIFICATION.json").read_text(encoding="utf-8"))
    assert all(item["status"] == "verified" for item in verification["allowlist"])
    assert verification["civic_graphql"]["status"] == "verified"
    assert all(item["status"] == "verified" for item in verification["extra_official_pages"])


def test_templates_hold_official_not_development() -> None:
    inspection = GoldSetCsvLoader().inspect(ROOT / "goldset" / "templates")
    assert inspection.row_counts == {
        "retrieval_gold.csv": 50,
        "field_gold.csv": 26,
        "error_gold.csv": 18,
    }
    assert inspection.status.value == "NOT_EVALUATED"
    with (ROOT / "goldset" / "templates" / "retrieval_gold.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        question_ids = {row["question_id"] for row in csv.DictReader(handle)}
    assert "oc01_chemo_pcr_annotation" in question_ids
    assert "q01_neoadjuvant_pcr" not in question_ids


def test_build_draft_refuses_to_overwrite_frozen_csvs() -> None:
    envelope = _frozen_envelope()
    assert envelope["manifest"]["frozen"] is True


def test_source_broker_ids_align_to_gold_dataset_ids() -> None:
    from importlib.machinery import SourceFileLoader

    module = SourceFileLoader(
        "collect_observations_dev",
        str(DEV / "collect_observations.py"),
    ).load_module()
    assert module.gold_id_matches("GSE76360", "geo:GSE76360")
    assert module.gold_id_matches("brca_metabric", "cbioportal:brca_metabric")
    assert module.gold_id_matches("TCGA-BRCA", "gdc:TCGA-BRCA")
    assert not module.gold_id_matches("DepMap", "geo:GSE76360")
