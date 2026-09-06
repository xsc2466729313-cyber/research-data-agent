from __future__ import annotations

import re

from backend.app.v30.models import (
    ClarificationRecord,
    ClarifyingQuestion,
    DataNeedSuggestion,
    MemorySnapshot,
    ResearchGoal,
    RouteDecision,
    RouteKind,
)
from backend.app.v30.planner.ready import is_ready_for_planner

FOCUS_QUESTION_ID = "research_focus"
FOCUS_QUESTION = "你的研究重点是机制探索还是疗效预测？"
FOCUS_OPTIONS = ("机制探索", "疗效预测")

_ONCOLOGY_DATA_NEEDS = (
    DataNeedSuggestion(
        category="clinical_outcomes",
        description="临床治疗与结局数据（建议，尚未检索）",
        retrieval_status="not_retrieved",
    ),
    DataNeedSuggestion(
        category="gene_expression",
        description="基因表达谱（建议，尚未检索）",
        retrieval_status="not_retrieved",
    ),
    DataNeedSuggestion(
        category="mutations",
        description="突变与拷贝数信息（建议，尚未检索）",
        retrieval_status="not_retrieved",
    ),
    DataNeedSuggestion(
        category="drug_response",
        description="药物敏感性或治疗响应数据（建议，尚未检索）",
        retrieval_status="not_retrieved",
    ),
)

_CONCEPT_CARDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("her2", "erbb2"),
        "HER2（ERBB2）是人表皮生长因子受体2，常作为乳腺癌分型与靶向治疗相关的生物标志物。"
        "这是概念解释，不是取数或诊断结论。",
    ),
    (
        ("红移", "redshift"),
        "红移指天体光谱向较长波长方向移动，常用来描述天体退行或宇宙膨胀相关观测。"
        "这是概念解释，不是取数任务。",
    ),
)


class CopilotDraft:
    def __init__(
        self,
        *,
        understood_goal: ResearchGoal | None,
        suggested_data_needs: list[DataNeedSuggestion],
        clarifying_questions: list[ClarifyingQuestion],
        ready_for_planner: bool,
        user_visible_reply: str,
        blocked_reason: str | None,
        goal_to_store: ResearchGoal | None,
        clarifications_to_store: list[ClarificationRecord] | None,
        constraints_to_add: list[str],
        write_goal: bool,
    ) -> None:
        self.understood_goal = understood_goal
        self.suggested_data_needs = suggested_data_needs
        self.clarifying_questions = clarifying_questions
        self.ready_for_planner = ready_for_planner
        self.user_visible_reply = user_visible_reply
        self.blocked_reason = blocked_reason
        self.goal_to_store = goal_to_store
        self.clarifications_to_store = clarifications_to_store
        self.constraints_to_add = constraints_to_add
        self.write_goal = write_goal


class ResearchCopilot:
    """Understand a research ask and ask clarifying questions. Never fetch or generate data."""

    def draft(self, message: str, route: RouteDecision, memory: MemorySnapshot) -> CopilotDraft:
        text = (message or "").strip()
        if route.route is RouteKind.CHAT:
            return self._chat(text, route)
        if route.route is RouteKind.CONCEPT_QA:
            return self._concept(text, route)
        return self._research(text, route, memory)

    def _chat(self, text: str, route: RouteDecision) -> CopilotDraft:
        if not text:
            reply = "请先用一句话说明研究对象和想回答的问题。我还不会取数，也不会生成研究方案。"
            blocked = "empty_message"
        else:
            reply = "你好。我是科研助手入口，可以帮你澄清研究目标。请直接说你想研究什么；我这一步不取数、不生成数据。"
            blocked = "not_a_research_request"
        return CopilotDraft(
            understood_goal=None,
            suggested_data_needs=[],
            clarifying_questions=[],
            ready_for_planner=False,
            user_visible_reply=reply,
            blocked_reason=blocked,
            goal_to_store=None,
            clarifications_to_store=None,
            constraints_to_add=[],
            write_goal=False,
        )

    def _concept(self, text: str, route: RouteDecision) -> CopilotDraft:
        reply = self._concept_reply(text)
        return CopilotDraft(
            understood_goal=None,
            suggested_data_needs=[],
            clarifying_questions=[],
            ready_for_planner=False,
            user_visible_reply=reply,
            blocked_reason="concept_question_not_a_research_task",
            goal_to_store=None,
            clarifications_to_store=None,
            constraints_to_add=[],
            write_goal=False,
        )

    def _research(self, text: str, route: RouteDecision, memory: MemorySnapshot) -> CopilotDraft:
        goal = self._merge_goal(text, route, memory)
        constraints = self._extract_constraints(text)
        clarifications = [item.model_copy(deep=True) for item in memory.clarifications]
        answered = self._apply_focus_answer(text, clarifications)
        if not clarifications and self._needs_focus_question(text, goal):
            clarifications.append(
                ClarificationRecord(
                    question_id=FOCUS_QUESTION_ID,
                    question=FOCUS_QUESTION,
                    answer=None,
                )
            )
        pending = [item for item in clarifications if not item.answer]
        preview = MemorySnapshot(
            session_id=memory.session_id,
            goal=goal,
            clarifications=clarifications,
            constraints=memory.constraints,
        )
        ready = is_ready_for_planner(preview)
        questions = [
            ClarifyingQuestion(question_id=item.question_id, question=item.question, options=list(FOCUS_OPTIONS))
            for item in pending
            if item.question_id == FOCUS_QUESTION_ID
        ] + [
            ClarifyingQuestion(question_id=item.question_id, question=item.question, options=[])
            for item in pending
            if item.question_id != FOCUS_QUESTION_ID
        ]
        needs = list(_ONCOLOGY_DATA_NEEDS) if (goal.domain or route.domain) == "oncology" else [
            DataNeedSuggestion(
                category="domain_evidence",
                description="与该研究对象匹配的公开观测或实验记录（建议，尚未检索）",
                retrieval_status="not_retrieved",
            )
        ]
        reply = self._research_reply(goal, questions, ready, answered, route)
        return CopilotDraft(
            understood_goal=goal,
            suggested_data_needs=needs,
            clarifying_questions=questions,
            ready_for_planner=ready,
            user_visible_reply=reply,
            blocked_reason=None if ready else "awaiting_clarification",
            goal_to_store=goal,
            clarifications_to_store=clarifications,
            constraints_to_add=constraints,
            write_goal=True,
        )

    def _merge_goal(self, text: str, route: RouteDecision, memory: MemorySnapshot) -> ResearchGoal:
        previous = memory.goal
        extracted = self._extract_goal(text, route.domain)
        if previous is None:
            return extracted
        return ResearchGoal(
            object=extracted.object or previous.object,
            target=extracted.target or previous.target,
            domain=extracted.domain or previous.domain,
            raw_text=previous.raw_text or extracted.raw_text,
        )

    def _extract_goal(self, text: str, domain: str) -> ResearchGoal:
        folded = text.casefold()
        compact = re.sub(r"\s+", "", folded)
        obj = None
        target = None
        her2_positive = "her2" in compact and ("阳性" in text or "positive" in folded)
        breast = "乳腺" in text or "breast" in folded
        if her2_positive and breast:
            obj = "HER2阳性乳腺癌"
        elif her2_positive:
            obj = "HER2阳性肿瘤"
        elif breast and ("癌" in text or "cancer" in folded):
            obj = "乳腺癌"
        elif "红移" in text or "redshift" in folded:
            obj = "红移相关天体观测"
        if "耐药" in text or "resistance" in folded:
            target = "耐药机制分析"
        elif "机制" in text and "探索" not in text:
            target = "机制分析"
        elif "关联" in text or "相关" in text:
            target = "关联分析"
        return ResearchGoal(object=obj, target=target, domain=domain if domain != "unknown" else None, raw_text=text or None)

    @staticmethod
    def _needs_focus_question(text: str, goal: ResearchGoal) -> bool:
        folded = text.casefold()
        if "疗效预测" in text or "机制探索" in text:
            return False
        return bool(goal.target) or "耐药" in text or "机制" in text or "resistance" in folded

    @staticmethod
    def _apply_focus_answer(text: str, clarifications: list[ClarificationRecord]) -> bool:
        answer = None
        if "疗效预测" in text:
            answer = "疗效预测"
        elif "机制探索" in text or (text.strip() == "机制"):
            answer = "机制探索"
        if answer is None:
            return False
        for item in clarifications:
            if item.question_id == FOCUS_QUESTION_ID:
                item.answer = answer
                return True
        clarifications.append(
            ClarificationRecord(question_id=FOCUS_QUESTION_ID, question=FOCUS_QUESTION, answer=answer)
        )
        return True

    @staticmethod
    def _extract_constraints(text: str) -> list[str]:
        found: list[str] = []
        for match in re.finditer(r"(?:不要|排除|不用|禁止)\s*([A-Za-z0-9_\-]+|[\u4e00-\u9fff]{2,20})", text):
            token = match.group(1).strip()
            if token:
                found.append(f"排除 {token}")
        return found

    @staticmethod
    def _concept_reply(text: str) -> str:
        compact = re.sub(r"\s+", "", text).casefold()
        for aliases, card in _CONCEPT_CARDS:
            if any(alias.casefold() in compact for alias in aliases):
                return card
        topic = re.sub(r"^(什么是|什么叫|何为|what is|what's|whats|解释一下|解释下)\s*", "", text, flags=re.I)
        topic = topic.strip("？?。 ") or "该概念"
        return f"{topic}属于概念解释请求。我可以说明含义，但这一步不会检索数据集，也不会生成研究数据。"

    @staticmethod
    def _research_reply(
        goal: ResearchGoal,
        questions: list[ClarifyingQuestion],
        ready: bool,
        answered: bool,
        route: RouteDecision,
    ) -> str:
        object_label = goal.object or "尚未明确的研究对象"
        target_label = goal.target or "尚未明确的分析目标"
        lines = [
            f"我理解你想研究的对象是{object_label}，目标偏向{target_label}。",
            "建议的数据需求还只是方向，尚未检索任何公开数据集，也没有生成数据。",
        ]
        if questions:
            lines.append("在形成研究方案前，需要先确认：" + questions[0].question)
        elif ready:
            if route.route is RouteKind.PLAN:
                lines.append("澄清已经齐，但本阶段尚未挂载 Planner，不会生成研究方案，也不会取数。")
            elif answered:
                lines.append("已记录你的澄清。当前可以进入规划，但本阶段还不会自动生成方案或取数。")
            else:
                lines.append("目标已足够清楚。本阶段仍不会自动生成方案或取数。")
        return "".join(lines)
