from __future__ import annotations

from types import SimpleNamespace

from backend.app.evaluation.public_qwen_matching import (
    _bounded_samples,
    _entity_metrics_from_predictions,
    _schema_predictions,
)


class FakeQwen:
    settings = SimpleNamespace(model="qwen-test")

    def match_schema_batch(self, items):
        assert len(items[0]["source_value_samples"]["short_name"][0]) <= 160
        return {"schema_task": [{
            "source_column": "short_name",
            "target_column": "name",
            "confidence": 0.91,
            "reason": "same meaning",
        }]}


def test_bounded_samples_do_not_send_unbounded_geometry() -> None:
    bounded = _bounded_samples({"shape": ["x" * 1000]})
    assert len(bounded["shape"][0]) == 160


def test_qwen_schema_predictions_keep_valid_one_to_one_pairs() -> None:
    predictions, audit, raw = _schema_predictions(
        ["short_name"], ["name"], {"source": {"short_name": ["x" * 200]}, "target": {"name": ["x"]}}, FakeQwen()
    )
    assert predictions == {("short_name", "name")}
    assert audit.successful_calls == 1
    assert audit.fallback_items == 0
    assert raw[0]["used_qwen"] is not False


def test_entity_metrics_use_local_labels_only() -> None:
    pairs = [
        ({"title": "same"}, {"title": "same"}, 1),
        ({"title": "other"}, {"title": "different"}, 0),
    ]
    result = _entity_metrics_from_predictions(pairs, [True, False])
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0
