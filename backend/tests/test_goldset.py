from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.app.evaluation import EvaluationError, GoldSetCsvLoader
from backend.app.evaluation.goldset import REQUIRED_HEADERS, compute_gold_set_checksum
from backend.app.evaluation.models import GoldSetManifest


ROOT = Path(__file__).resolve().parents[2]


def manifest() -> GoldSetManifest:
    return GoldSetManifest(
        gold_set_id="fixture-csv",
        version="fixture-v1",
        frozen=True,
        frozen_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        initial_labeler="fixture-a",
        independent_reviewer="fixture-b",
        deterministic_rules_verified=True,
        source_references_verified=True,
        high_risk_review_complete=True,
        gold_set_checksum="0" * 64,
    )


def test_bundled_goldset_templates_have_exact_headers_and_no_fake_scores() -> None:
    inspection = GoldSetCsvLoader().inspect(ROOT / "goldset" / "templates")

    assert inspection.status.value == "NOT_EVALUATED"
    assert inspection.required_headers == REQUIRED_HEADERS
    assert inspection.row_counts == {
        "retrieval_gold.csv": 50,
        "field_gold.csv": 26,
        "error_gold.csv": 18,
    }
    templates = ROOT / "goldset" / "templates"
    for filename in REQUIRED_HEADERS:
        text = (templates / filename).read_text(encoding="utf-8-sig")
        assert "66.94" not in text
        assert "SDTI" not in text


def test_goldset_loader_parses_template_compatible_csv_rows(tmp_path: Path) -> None:
    (tmp_path / "retrieval_gold.csv").write_text(
        ",".join(REQUIRED_HEADERS["retrieval_gold.csv"])
        + "\nq1,fixture question,fixture-dataset,1,dual review,approved,\n",
        encoding="utf-8",
    )
    (tmp_path / "field_gold.csv").write_text(
        ",".join(REQUIRED_HEADERS["field_gold.csv"])
        + "\nf1,fixture-dataset,HER2_IHC,2+,her2_status,Equivocal,true,rules,approved,\n",
        encoding="utf-8",
    )
    (tmp_path / "error_gold.csv").write_text(
        ",".join(REQUIRED_HEADERS["error_gold.csv"])
        + '\ne1,gene_alias,"{""gene"":""HER2""}",true,"{""gene"":""ERBB2""}",true,low,approved,\n',
        encoding="utf-8",
    )

    bundle = GoldSetCsvLoader().load(tmp_path, manifest())

    assert bundle.retrieval_gold[0].label.value == "relevant"
    assert bundle.field_gold[0].canonical_value == "Equivocal"
    assert bundle.error_gold[0].expected_detection is True
    assert len(compute_gold_set_checksum(bundle)) == 64


def test_goldset_loader_rejects_header_drift(tmp_path: Path) -> None:
    for filename, headers in REQUIRED_HEADERS.items():
        actual = headers[:-1] if filename == "retrieval_gold.csv" else headers
        (tmp_path / filename).write_text(
            ",".join(actual) + "\n",
            encoding="utf-8",
        )

    with pytest.raises(EvaluationError) as exc_info:
        GoldSetCsvLoader().inspect(tmp_path)

    assert exc_info.value.code.value == "invalid_gold_set"
