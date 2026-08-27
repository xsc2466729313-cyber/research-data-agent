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
