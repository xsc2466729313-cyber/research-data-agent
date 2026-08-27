from __future__ import annotations

import re


_BILINGUAL_RESEARCH_TERMS = {
    "乳腺癌": ("breast", "cancer"),
    "新辅助": ("neoadjuvant",),
    "病理完全缓解": ("pathological", "complete", "response", "pcr"),
    "主要结局": ("primary", "outcome", "endpoint"),
    "结局": ("outcome", "endpoint"),
    "受体亚型": ("receptor", "subtype"),
    "基因表达": ("gene", "expression", "transcriptomic"),
    "数据可用性": ("data", "availability"),
    "方法": ("method", "methods"),
    "统计": ("statistical", "statistics"),
}


def retrieval_tokens(text: str) -> list[str]:
    """Return deterministic bilingual lexical features for the offline fallback."""

    folded = text.casefold()
    words = re.findall(r"[a-z0-9][a-z0-9_+.-]*", folded)
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", folded))
    bigrams = [chinese[index:index + 2] for index in range(max(0, len(chinese) - 1))]
    translated = [
        token
        for phrase, tokens in _BILINGUAL_RESEARCH_TERMS.items()
        if phrase in folded
        for token in tokens
    ]
    return [*words, *bigrams, *translated]
