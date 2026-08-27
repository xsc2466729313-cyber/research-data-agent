from __future__ import annotations

import pytest

from backend.app.evaluation.public_cleaning import evaluate_cleaning


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
