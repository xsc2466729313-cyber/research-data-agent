from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .models import AuditStamp


def canonical_hash(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_audit_stamp(
    *,
    input_value: Any,
    output_value: Any,
    code_revision: str = "working-tree",
    model_name: str = "none",
    model_version: str = "not-invoked",
    prompt_version: str = "not-applicable",
    rule_version: str = "0.1",
    schema_version: str = "0.1",
    dataset_manifest: str = "inline-request",
) -> AuditStamp:
    return AuditStamp(
        code_revision=code_revision,
        model_name=model_name,
        model_version=model_version,
        prompt_version=prompt_version,
        rule_version=rule_version,
        schema_version=schema_version,
        dataset_manifest=dataset_manifest,
        timestamp=datetime.now(timezone.utc),
        input_hash=canonical_hash(input_value),
        output_hash=canonical_hash(output_value),
    )
