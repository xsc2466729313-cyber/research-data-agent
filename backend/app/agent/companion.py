from __future__ import annotations

import json
from typing import Any, Mapping

from backend.app.agent.models import CompanionMessage
from backend.app.agent.qwen_client import QwenClient, QwenClientError

_CONTEXT_KEYS = (
    "question",
    "status",
    "stage",
    "dataset_title",
    "dataset_size",
    "dictionary_count",
    "source_count",
    "summary",
    "dataset_note",
    # The research guide sends both rendered panels and a compact result
    # snapshot.  Keeping these keys explicit prevents unrelated request data
    # from entering the model prompt while still allowing the companion to
    # explain the main entry in detail.
    "planner_title",
    "planner_subtitle",
    "flow_summary",
    "planner_chat",
    "planner_results",
    "evidence_panel",
    "contract_panel",
    "sources_panel",
    "coverage_panel",
    "quality_gate",
    "quality_report",
    "lineage_panel",
    "result",
)

_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
}


def _clip(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _safe_value(value: Any, *, depth: int = 0, budget: int = 24000) -> Any:
    """Bound page context before it is copied into a model prompt.

    The main entry result is nested and can contain many rows or source
    objects.  A bounded, recursively sanitized representation lets the
    companion answer from the visible result without accidentally forwarding
    credentials or an unbounded payload.
    """
    if budget <= 0:
        return "…"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value.strip()[: min(2400, budget)]
    if depth >= 4:
        return _clip(value, min(800, budget))
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        remaining = budget
        for key, item in list(value.items())[:80]:
            name = str(key)
            if name.casefold().replace("-", "_") in _SENSITIVE_KEYS:
                continue
            safe = _safe_value(item, depth=depth + 1, budget=min(2400, remaining))
            output[name] = safe
            remaining -= max(1, len(str(safe)))
            if remaining <= 0:
                break
        return output
    if isinstance(value, (list, tuple, set)):
        output = []
        remaining = budget
        for item in list(value)[:40]:
            safe = _safe_value(item, depth=depth + 1, budget=min(1800, remaining))
            output.append(safe)
            remaining -= max(1, len(str(safe)))
            if remaining <= 0:
                break
        return output
    return _clip(value, min(800, budget))


def _safe_context(context: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in _CONTEXT_KEYS:
        if key not in context:
            continue
        safe = _safe_value(context.get(key))
        if safe not in (None, "", [], {}):
            result[key] = safe
    return result


def build_companion_messages(
    *,
    message: str,
    history: list[CompanionMessage],
    context: Mapping[str, Any],
    purpose: str = "chat",
) -> list[dict[str, str]]:
    safe_context = _safe_context(context)
    purpose_instruction = (
        "当前请求是普通对话：直接回答用户的问题；如果涉及页面结果，明确引用上下文里的字段和来源。"
        if purpose == "chat"
        else "当前请求是研究问题整理：把用户对话和页面上下文整理成一段可直接送入研究向导的研究问题。"
    )
    system = (
        "你是‘科研兔’，科研数据工作台里的科研解析助手。你要像高质量 ChatGPT 一样自然对话，"
        "可以回答闲聊、概念问题、研究问题、研究课题设计和数据集理解问题。不要反复要求用户完成表单；"
        "问题足够清楚时直接给出结构化而有解释的回答，并在必要时给出下一步建议。\n\n"
        f"{purpose_instruction}\n"
        "科研可信性规则：\n"
        "1. 页面上下文只是当前界面已经显示的信息；没有显示的事实不能假装已经检索或验证。\n"
        "2. 候选来源不等于已下载数据，预览不等于观测结果；不确定时明确说待核验。\n"
        "3. 解释数据集时优先说明分析单位、字段含义、缺失、来源、原始字段/原始值和血缘，"
        "不要替用户编造行数、样本或统计结论。\n"
        "4. 医学问题只做科研信息解释，不做诊断或治疗决定；HER2 检测维度、患者/样本关联和临床/细胞系响应不能混同。\n"
        "5. 如果用户要启动正式检索或生成数据资产，说明研究向导会负责真实获取、质量检查和来源登记；不要声称你已经完成。\n\n"
        "6. 页面上下文中的 result、来源和血缘对象是当前主入口传入的事实摘要；可以解释其内容，但不能补造缺失字段。\n\n"
        "当前主入口页面与结果上下文（可能为空，仅供解释当前界面）：\n"
        f"{json.dumps(safe_context, ensure_ascii=False)}"
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    messages.extend(
        {"role": item.role, "content": _clip(item.content, 2400)}
        for item in history[-16:]
    )
    messages.append({"role": "user", "content": _clip(message, 2000)})
    return messages


def answer_companion(
    *,
    client: QwenClient,
    message: str,
    history: list[CompanionMessage],
    context: Mapping[str, Any],
) -> str:
    try:
        response = client.chat(messages=build_companion_messages(message=message, history=history, context=context))
    except QwenClientError:
        raise
    answer = _clip(response.get("content"), 12000)
    if not answer:
        raise QwenClientError("科研模型未返回可显示的对话内容。")
    return answer


def format_companion_research_question(
    *,
    client: QwenClient,
    message: str,
    history: list[CompanionMessage],
    context: Mapping[str, Any],
) -> str:
    """Turn an open companion conversation into a planner-ready question.

    The model is asked for a compact, human-readable block rather than a
    guessed database record.  This keeps the handoff useful for the main
    planner while preserving uncertainty and the distinction between page
    context and verified source facts.
    """
    messages = build_companion_messages(
        message=message,
        history=history,
        context=context,
        purpose="research_question",
    )
    messages[0]["content"] += (
        "\n\n请只输出以下四行（每行一项，内容不足时写‘待确认’，不要编造具体数值或患者事实）：\n"
        "研究对象：……\n"
        "研究问题：……\n"
        "数据需求：……\n"
        "分析边界：……"
    )
    try:
        response = client.chat(messages=messages)
    except QwenClientError:
        raise
    answer = _clip(response.get("content"), 12000)
    if not answer:
        raise QwenClientError("科研模型未返回可用的研究问题。")
    # Some compatible endpoints still wrap a requested text answer in JSON;
    # accept that shape without requiring a second model call.
    if answer.startswith("{"):
        try:
            payload = json.loads(answer)
        except (TypeError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict):
            candidate = _clip(payload.get("research_question") or payload.get("question"), 12000)
            if candidate:
                return candidate
    return answer


def deterministic_research_question(
    *,
    message: str,
    history: list[CompanionMessage],
    context: Mapping[str, Any],
) -> str:
    """Create a transparent handoff when no model is connected.

    This formatter only reuses the user's words and visible page state. It
    does not infer a disease, sample size, result, or source that is absent
    from the conversation and the main-entry snapshot.
    """
    safe = _safe_context(context)
    latest_user = next(
        (item.content.strip() for item in reversed(history) if item.role == "user" and item.content.strip()),
        "",
    )
    subject = str(safe.get("question") or latest_user or message).strip()[:1200]
    dataset = str(safe.get("dataset_title") or "待确认").strip()[:400]
    status = str(safe.get("status") or "尚未运行").strip()[:300]
    return (
        f"研究对象：{subject}\n"
        f"研究问题：围绕“{subject}”，明确需要通过真实来源和可复用数据验证的核心关系、现象或方法。\n"
        f"数据需求：检索并解析与该问题相关的公开数据集、论文或原始记录；当前主入口数据资产：{dataset}。\n"
        f"分析边界：先核验分析单位、字段定义、来源血缘、缺失和证据强度；当前页面状态：{status}。"
    )
