from __future__ import annotations

from backend.app.contracts.models import ClarifyRequest, ContractCreateRequest, FrozenResearchContract
from backend.app.requirement_agent import RequirementAgentService
from backend.app.research_planning_v2 import ResearchPlanningV2Service
from backend.app.research_planning_v2.models import ResearchPlanningV2Request
from backend.app.v30.models import MemorySnapshot, PlanResponse, PlanningV2View
from backend.app.v30.planner.ready import compile_topic, is_ready_for_planner


class PlannerNotReadyError(ValueError):
    error = "research_goal_not_ready"

    def __init__(self) -> None:
        super().__init__(self.error)


class PlannerFacade:
    """Compile a ready Copilot session into existing research-planning services.

    This is not a new planner. Oncology paths must reuse RequirementAgent,
    ResearchPlanningService (via RequirementAgent), and ResearchPlanningV2.
    """

    def __init__(
        self,
        *,
        requirement_agent: RequirementAgentService,
        planning_v2: ResearchPlanningV2Service | None = None,
    ) -> None:
        self.requirement_agent = requirement_agent
        self.planning_v2 = planning_v2 or ResearchPlanningV2Service()

    def plan(
        self,
        *,
        session_id: str,
        memory: MemorySnapshot,
        question_override: str | None = None,
    ) -> PlanResponse:
        if not is_ready_for_planner(memory):
            raise PlannerNotReadyError()
        topic = compile_topic(memory)
        if len(topic) < 2:
            raise PlannerNotReadyError()
        domain = (memory.goal.domain if memory.goal and memory.goal.domain else "unknown")
        if domain != "oncology":
            return PlanResponse(
                session_id=session_id,
                compiled_from_session=True,
                ready_for_planner=True,
                domain=domain,
                topic=topic,
                used_existing_services=[],
                notice="非肿瘤领域只返回方案草稿，仍需确认领域；不会冒充已冻结的医学 Research Contract。",
                memory=memory,
            )
        return self._plan_oncology(session_id=session_id, memory=memory, topic=topic, question_override=question_override)

    def _plan_oncology(
        self,
        *,
        session_id: str,
        memory: MemorySnapshot,
        topic: str,
        question_override: str | None,
    ) -> PlanResponse:
        clarify = self.requirement_agent.clarify(ClarifyRequest(topic=topic, max_papers=5))
        # Explicit second hop through the existing planning service already used by RequirementAgent.
        self.requirement_agent.planning.question_candidates(clarify.topic_id)
        contract: FrozenResearchContract | None = None
        if clarify.candidates:
            selected = min(clarify.candidates, key=lambda item: item.rank)
            contract = self.requirement_agent.create_contract(
                ContractCreateRequest(
                    topic_id=clarify.topic_id,
                    candidate_id=selected.candidate_id,
                    question_override=question_override,
                )
            )
        v2 = self.planning_v2.plan(
            ResearchPlanningV2Request(
                topic=topic,
                user_constraints={"constraints": list(memory.constraints)},
            )
        )
        notice = (
            "已转调现有 RequirementAgent / ResearchPlanning / ResearchPlanningV2。"
            "本步不取数、不调用 Adapter、不生成 CanonicalRecord、不冻结合同。"
        )
        if contract is None:
            notice = "已调用现有规划服务，但没有可编译的候选问题；未创建 Research Contract。"
        return PlanResponse(
            session_id=session_id,
            compiled_from_session=True,
            ready_for_planner=True,
            domain="oncology",
            topic=topic,
            used_existing_services=[
                "RequirementAgentService",
                "ResearchPlanningService",
                "ResearchPlanningV2Service",
            ],
            contract_id=contract.contract_id if contract else None,
            contract_status=contract.status if contract else None,
            research_goal=contract.research_goal if contract else None,
            clarify_topic_id=clarify.topic_id,
            candidate_count=len(clarify.candidates),
            contract=contract,
            planning_v2=PlanningV2View(
                question_generation_source=v2.question_generation_source,
                candidate_count=len(v2.candidate_questions),
                selected_question=v2.selected_question.question if v2.selected_question else None,
                unresolved_questions=list(v2.unresolved_questions),
                notice=v2.notice,
                fallback_template_only=v2.fallback_template_only,
            ),
            notice=notice,
            memory=memory,
        )
