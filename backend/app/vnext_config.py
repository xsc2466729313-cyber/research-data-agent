from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field

from backend.app.models import ApiModel


class GovernanceConfig(ApiModel):
    decision_protocol: str
    auto_confidence_threshold: float = Field(ge=0, le=1)
    review_confidence_threshold: float = Field(ge=0, le=1)
    rule_version: str
    schema_version: str


class RetrievalConfig(ApiModel):
    service_version: str
    default_method: str
    bm25_weight: float = Field(ge=0, le=1)
    dense_weight: float = Field(ge=0, le=1)
    candidate_pool_multiplier: int = Field(ge=1)
    dense_backend: str
    reranker_backend: str
    offline_dense_fallback: str
    query_instruction: str
    max_seq_length: int = Field(ge=16, le=512)
    production_backends_require_benchmark: bool
    record_latency_and_invocation: bool


class SelectiveInvocationConfig(ApiModel):
    enabled: bool
    target_rate_min: float = Field(ge=0, le=1)
    target_rate_max: float = Field(ge=0, le=1)
    current_qwen_judges_enabled: bool
    notice: str


class VNextConfig(ApiModel):
    version: str
    governance: GovernanceConfig
    retrieval: RetrievalConfig
    selective_agent_invocation: SelectiveInvocationConfig


@lru_cache(maxsize=1)
def load_vnext_config() -> VNextConfig:
    path = Path(__file__).resolve().parents[2] / "configs" / "vnext.yaml"
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    return VNextConfig.model_validate(payload)
