from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.normalization import (
    BiomarkerNormalizer,
    DrugNormalizer,
    GeneNormalizer,
)
from backend.app.normalization.models import FieldMapping, NormalizationStatus


def test_gene_normalizer_uses_exact_aliases_and_casing() -> None:
    normalizer = GeneNormalizer()

    assert normalizer.normalize("HER-2").values == {"gene": "ERBB2"}
    assert normalizer.normalize("pik3ca").values == {"gene": "PIK3CA"}
    assert normalizer.normalize("PIK3CA").status == NormalizationStatus.IDENTITY


def test_gene_normalizer_routes_non_symbols_to_unresolved() -> None:
    result = GeneNormalizer().normalize("ERBB2 amplification")

    assert result.values == {}
    assert result.status == NormalizationStatus.UNRESOLVED


def test_drug_normalizer_maps_curated_trade_names_only() -> None:
    normalizer = DrugNormalizer()

    assert normalizer.normalize("Herceptin").values == {"drug": "Trastuzumab"}
    assert normalizer.normalize("Piqray").values == {"drug": "Alpelisib"}
    unknown = normalizer.normalize("Investigational Agent X")
    assert unknown.values == {"drug": "Investigational Agent X"}
    assert unknown.status == NormalizationStatus.IDENTITY


def test_drug_combination_is_preserved_for_review() -> None:
    result = DrugNormalizer().normalize("trastuzumab + pertuzumab")

    assert result.values["drug"] == "trastuzumab + pertuzumab"
    assert result.status == NormalizationStatus.REVIEW


def test_her2_ihc_2plus_is_equivocal_and_raw_assay_is_retained() -> None:
    result = BiomarkerNormalizer().normalize(
        raw_field="HER2_IHC",
        raw_value="2+",
        canonical_field="her2_status",
    )

    assert result.values == {
        "her2_assay": "IHC",
        "her2_raw_value": "2+",
        "her2_status": "Equivocal",
    }
    assert result.confidence == 1.0
    assert "never directly" in (result.reason or "")


def test_fish_and_erbb2_cna_remain_separate_dimensions() -> None:
    normalizer = BiomarkerNormalizer()
    fish = normalizer.normalize(
        raw_field="HER2_FISH",
        raw_value="amplified",
        canonical_field="her2_status",
    )
    cna = normalizer.normalize(
        raw_field="ERBB2_CNA",
        raw_value="amplification",
        canonical_field="variant",
    )

    assert fish.values["her2_status"] == "Positive"
    assert fish.values["her2_assay"] == "FISH"
    assert cna.values == {"gene": "ERBB2", "variant": "Amplification"}
    assert "her2_status" not in cna.values
    assert "her2_assay" not in cna.values


def test_numeric_fish_and_receptor_percentage_do_not_infer_thresholds() -> None:
    normalizer = BiomarkerNormalizer()
    fish = normalizer.normalize(
        raw_field="HER2_FISH_RATIO",
        raw_value="1.9",
        canonical_field="her2_status",
    )
    er = normalizer.normalize(
        raw_field="ER_STATUS",
        raw_value="5%",
        canonical_field="er_status",
    )

    assert fish.values["her2_status"] == "Unknown"
    assert fish.status == NormalizationStatus.REVIEW
    assert er.values == {"er_status": "Unknown"}
    assert er.status == NormalizationStatus.REVIEW


def test_high_risk_fields_require_specialized_normalizers() -> None:
    with pytest.raises(ValidationError, match="requires biomarker"):
        FieldMapping(
            mapping_id="unsafe-her2",
            raw_field="HER2_IHC",
            canonical_field="her2_status",
            normalizer="passthrough",
        )
    with pytest.raises(ValidationError, match="requires response_domain"):
        FieldMapping(
            mapping_id="unsafe-domain",
            raw_field="domain",
            canonical_field="response_domain",
            normalizer="passthrough",
        )
