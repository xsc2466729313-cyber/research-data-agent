from __future__ import annotations

import pytest
from pathlib import Path

from backend.app.evaluation.public_cleaning import evaluate_cleaning, load_cleaning_dataset


def test_no_repair_reports_existing_dirty_cells_as_missed() -> None:
    dirty = [{"id": "1", "city": "bejing"}, {"id": "2", "city": "shanghai"}]
    clean = [{"id": "1", "city": "beijing"}, {"id": "2", "city": "shanghai"}]
    result = evaluate_cleaning(dirty, clean, "no_repair")
    assert result.cell_precision == 0
    assert result.cell_recall == 0
    assert result.false_negative == 1
    assert result.dirty_cell_count == 1


def test_column_mode_repair_does_not_change_unique_identifier() -> None:
    dirty = [{"id": "1", "city": "x"}, {"id": "2", "city": "x"}, {"id": "3", "city": "x"}, {"id": "4", "city": "y"}]
    clean = [{"id": "1", "city": "x"}, {"id": "2", "city": "x"}, {"id": "3", "city": "x"}, {"id": "4", "city": "x"}]
    result = evaluate_cleaning(dirty, clean, "column_mode")
    assert result.correct_repairs == 1
    assert result.repair_accuracy == pytest.approx(1.0)


def test_load_cleaning_dataset_accepts_full_clean_table(tmp_path: Path) -> None:
    (tmp_path / "dirty.csv").write_text("id,city\n1,bejing\n2,shanghai\n", encoding="utf-8")
    (tmp_path / "clean.csv").write_text("id,city\n1,beijing\n2,shanghai\n", encoding="utf-8")
    dirty, clean = load_cleaning_dataset(tmp_path)
    assert dirty[0]["city"] == "bejing"
    assert clean[0]["city"] == "beijing"


def test_format_profile_repairs_numeric_units_and_city_state() -> None:
    dirty = [
        {"city": "San Francisco CA", "state": "", "ounces": "12.0 oz", "ibu": "N/A"},
        {"city": "Boston", "state": "MA", "ounces": "16", "ibu": "30"},
    ]
    clean = [
        {"city": "San Francisco", "state": "CA", "ounces": "12", "ibu": ""},
        {"city": "Boston", "state": "MA", "ounces": "16", "ibu": "30"},
    ]
    result = evaluate_cleaning(dirty, clean, "project_format_profile_v2")
    assert result.correct_repairs == 4
    assert result.repair_accuracy == pytest.approx(1.0)


def test_fusion_repair_recovers_repeated_placeholder_typos() -> None:
    dirty = [{"name": "alpha"}] * 10 + [{"name": "alxha"}]
    clean = [{"name": "alpha"}] * 11
    result = evaluate_cleaning(dirty, clean, "project_fusion_repair_v3")
    assert result.cell_f1 == pytest.approx(1.0)


def test_context_consensus_repairs_only_unique_repeated_flight_values() -> None:
    dirty = [
        {"flight": "AA-1", "scheduled": "10:00", "actual": ""},
        {"flight": "AA-1", "scheduled": "10:00", "actual": "10:15"},
        {"flight": "AA-2", "scheduled": "", "actual": "11:20"},
        {"flight": "AA-2", "scheduled": "12:00", "actual": "11:25"},
    ]
    clean = [
        {"flight": "AA-1", "scheduled": "10:00", "actual": "10:15"},
        {"flight": "AA-1", "scheduled": "10:00", "actual": "10:15"},
        {"flight": "AA-2", "scheduled": "12:00", "actual": "11:20"},
        {"flight": "AA-2", "scheduled": "12:00", "actual": "11:25"},
    ]
    result = evaluate_cleaning(dirty, clean, "project_context_consensus_repair_v4")
    assert result.correct_repairs == 2
    assert result.false_positive == 0


def test_date_profile_repairs_only_a_table_wide_rotated_date_profile() -> None:
    dirty = [{"article_jcreated_at": "1/1/14"}] * 20 + [{"article_jcreated_at": ""}]
    clean = [{"article_jcreated_at": "1/14/01"}] * 20 + [{"article_jcreated_at": ""}]
    result = evaluate_cleaning(dirty, clean, "project_date_profile_repair_v5")
    assert result.correct_repairs == 20
    assert result.false_positive == 0


def test_source_anchor_repairs_repeated_flight_copies() -> None:
    dirty = [
        {"tuple_id": "1", "src": "aa", "flight": "AA-1-JFK-SFO", "scheduled": "10:00", "actual": "10:15"},
        {"tuple_id": "2", "src": "weather", "flight": "AA-1-JFK-SFO", "scheduled": "", "actual": "10:22"},
    ]
    clean = [
        {"tuple_id": "1", "src": "aa", "flight": "AA-1-JFK-SFO", "scheduled": "10:00", "actual": "10:15"},
        {"tuple_id": "2", "src": "weather", "flight": "AA-1-JFK-SFO", "scheduled": "10:00", "actual": "10:15"},
    ]
    result = evaluate_cleaning(dirty, clean, "project_source_anchor_repair_v6")
    assert result.correct_repairs == 2
    assert result.false_positive == 0
