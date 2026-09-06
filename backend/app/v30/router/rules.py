from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_RULES_PATH = Path(__file__).resolve().parents[4] / "configs" / "v30" / "router_rules.yaml"

_FALLBACK: dict[str, Any] = {
    "chat_exact": ["你好", "您好", "嗨", "在吗", "hello", "hi", "hey", "thanks", "谢谢", "谢谢你"],
    "concept_prefixes": ["什么是", "什么叫", "何为", "what is", "what's", "whats", "解释一下", "解释下"],
    "research_tokens": ["研究", "想研究", "打算研究", "耐药", "机制", "疗效预测", "关联", "是否与", "队列", "队列研究", "相关性"],
    "plan_tokens": ["生成方案", "开始规划", "形成方案", "请规划", "进入规划"],
    "domains": {
        "oncology": ["癌", "肿瘤", "cancer", "carcinoma", "her2", "erbb2", "乳腺", "breast", "oncology"],
        "astronomy": ["红移", "redshift", "超新星", "supernova", "星系", "galaxy", "黑洞", "black hole"],
        "biomedicine": ["治疗", "预后", "基因", "蛋白", "免疫", "therapy", "gene", "protein"],
    },
}


@lru_cache(maxsize=1)
def load_router_rules() -> dict[str, Any]:
    if not _RULES_PATH.is_file():
        return _FALLBACK
    loaded = yaml.safe_load(_RULES_PATH.read_text(encoding="utf-8")) or {}
    merged = dict(_FALLBACK)
    merged.update(loaded)
    domains = dict(_FALLBACK["domains"])
    domains.update(loaded.get("domains") or {})
    merged["domains"] = domains
    return merged


def chat_phrases() -> tuple[str, ...]:
    return tuple(str(item) for item in load_router_rules()["chat_exact"])


def concept_prefixes() -> tuple[str, ...]:
    return tuple(str(item) for item in load_router_rules()["concept_prefixes"])


def research_tokens() -> tuple[str, ...]:
    return tuple(str(item) for item in load_router_rules()["research_tokens"])


def plan_tokens() -> tuple[str, ...]:
    return tuple(str(item) for item in load_router_rules()["plan_tokens"])


def domain_tokens() -> dict[str, tuple[str, ...]]:
    raw = load_router_rules()["domains"]
    return {str(name): tuple(str(token) for token in tokens) for name, tokens in raw.items()}
