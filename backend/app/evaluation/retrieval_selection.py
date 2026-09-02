from __future__ import annotations

from typing import Any, Iterable


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _call_succeeded(status: str) -> bool:
    value = status.strip().casefold()
    return bool(value) and not any(
        token in value for token in ("失败", "fail", "error", "取消", "cancel")
    )


def final_retrieval_ids(
    tool_calls: Iterable[Any],
    *,
    modeling_dataset: Any | None = None,
    source_datasets: Iterable[Any] = (),
) -> list[str]:
    """Return sources selected or materialized by the research task.

    Discovery hits, provenance records and fallback candidates remain auditable,
    but are not final retrieval decisions and must not become false positives.
    """

    found: list[str] = []

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text and text not in found:
            found.append(text)

    for call in tool_calls:
        if not _call_succeeded(str(_value(call, "status", ""))):
            continue
        name = str(_value(call, "tool_name", _value(call, "name", "")) or "")
        arguments = _value(call, "arguments", {}) or {}
        for key in ("accession", "study_id", "nct_id", "project_id"):
            add(arguments.get(key))
        if name == "search_civic":
            add("CIViC")
        elif name == "search_depmap":
            add("DepMap")
        elif name == "search_trials":
            add("AACT")
        elif name == "search_gdc" and not arguments.get("project_id"):
            add("TCGA-BRCA")

    for dataset in [modeling_dataset, *list(source_datasets)]:
        if dataset is None:
            continue
        add(_value(dataset, "study_key"))
        rows = _value(dataset, "rows", []) or []
        if rows:
            add(_value(rows[0], "study_id"))

    return found


__all__ = ["final_retrieval_ids"]
