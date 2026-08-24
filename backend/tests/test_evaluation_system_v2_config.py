from __future__ import annotations

import csv
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_unified_evaluation_v2_config_preserves_frozen_core_and_comparisons() -> None:
    config = yaml.safe_load(
        (ROOT / "configs" / "evaluation_system_v2.yaml").read_text(encoding="utf-8")
    )

    assert config["frozen_core"]["sdti_formula_source"] == (
        "docs/06_评测指标与SDTI.md"
    )
    assert config["frozen_core"]["do_not_modify_formula"] is True
    assert config["frozen_core"]["canonical_schema_source"] == (
        "configs/canonical_schema.yaml"
    )
    assert config["frozen_core"]["medical_rule_source"] == (
        "configs/medical_rules.yaml"
    )

    variants = {
        variant["id"] for variant in config["model_comparison"]["compare_variants"]
    }
    assert {
        "rule_keyword",
        "qwen_only",
        "single_source_agent",
        "multi_source_no_gate",
        "full_agent",
    }.issubset(variants)

    assert "sdti_goldset_by_variant" in config["horizontal_comparison"][
        "required_tables"
    ]
    assert "task_fitness_by_variant" in config["horizontal_comparison"][
        "required_tables"
    ]
    assert "response_domain" in config["stratified_comparison"]["required_strata"]
    assert "patient_sample_link_confidence" in config["stratified_comparison"][
        "required_strata"
    ]


def test_unified_results_template_has_lineage_columns_and_no_fake_scores() -> None:
    config = yaml.safe_load(
        (ROOT / "configs" / "evaluation_system_v2.yaml").read_text(encoding="utf-8")
    )
    template_path = ROOT / config["result_schema"]["template"]

    with template_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert reader.fieldnames is not None
    assert set(config["result_schema"]["required_columns"]).issubset(
        set(reader.fieldnames)
    )
    assert rows

    method_ids = {row["method_id"] for row in rows}
    assert {"rule_keyword", "qwen_only", "multi_source_no_gate", "full_agent"}.issubset(
        method_ids
    )
    stratum_names = {row["stratum_name"] for row in rows}
    assert {"benchmark_dataset", "disease_subtype", "method_variant"}.issubset(
        stratum_names
    )

    for row in rows:
        assert row["value"] == ""
        assert row["source_id"]
        assert row["source_url"] == "TBD" or row["source_url"].startswith("https://")
        assert row["raw_field"]
