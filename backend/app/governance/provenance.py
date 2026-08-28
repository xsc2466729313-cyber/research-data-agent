from __future__ import annotations

from collections.abc import Mapping
from typing import Any


PROVENANCE_FIELDS = (
    "source_id",
    "raw_field",
    "raw_value",
    "transformation",
    "model_or_rule",
    "version",
)


def missing_provenance_fields(value: Mapping[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in PROVENANCE_FIELDS:
        item = value.get(field)
        if item is None or (isinstance(item, str) and not item.strip()):
            missing.append(field)
    return missing


def has_complete_provenance(value: Mapping[str, Any]) -> bool:
    return not missing_provenance_fields(value)
