from __future__ import annotations

from backend.app.contracts.models import PerspectivePrompt


PERSPECTIVES: tuple[tuple[str, str], ...] = (
    ("clinical", "哪些患者亚组、分期或受体状态需要被明确？"),
    ("molecular", "哪些分子变量（突变、表达、拷贝数）可能与结局有关？"),
    ("treatment", "具体治疗方案、时间点和药物组合是什么？"),
    ("outcome", "主要终点是 pCR、ORR、生存还是其他可测结局？"),
    ("data", "哪些公开队列或 accession 可能同时覆盖这些变量？"),
    ("methodology", "更适合关联分析、预测模型还是亚组比较？"),
)


def expand_perspectives(topic: str) -> list[PerspectivePrompt]:
    text = topic.strip() or "当前研究方向"
    return [
        PerspectivePrompt(perspective=name, prompt=f"{text}：{prompt}")
        for name, prompt in PERSPECTIVES
    ]
