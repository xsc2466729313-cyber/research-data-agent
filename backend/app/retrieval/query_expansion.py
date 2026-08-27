from __future__ import annotations

_ALIASES = {
    "pcr": ("pathological complete response", "pathologic complete response"),
    "her2": ("erbb2", "human epidermal growth factor receptor 2"),
    "乳腺癌": ("breast cancer",),
    "新辅助": ("neoadjuvant", "preoperative treatment"),
}


def expand_query(query: str) -> str:
    terms = [query.strip()]
    folded = query.casefold()
    for source, aliases in _ALIASES.items():
        if source.casefold() in folded:
            terms.extend(aliases)
    return " ".join(dict.fromkeys(item for item in terms if item))
