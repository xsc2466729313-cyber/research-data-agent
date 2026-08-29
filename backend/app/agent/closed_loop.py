from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from backend.app.agent.closed_loop_models import (
    ClosedLoopAction,
    ClosedLoopAudit,
    ClosedLoopDiagnosis,
    ClosedLoopHighlightCard,
    ClosedLoopImprovement,
    ClosedLoopIteration,
    ClosedLoopMetricSnapshot,
    ClosedLoopRequest,
    ClosedLoopResponse,
)
from backend.app.agent.models import AgentTaskRequest, AgentTaskResult
from backend.app.agent.outcome_repair import diagnose_outcome_gap


SAFETY_CONSTRAINTS = [
    "第二轮不得放宽患者/样本身份关联；低置信度关联继续保持 unresolved/review。",
    "第二轮不得自动修改 HER2 assay/status、response_domain/response 或关键 provenance。",
    "所有新字段仍必须保留 source_id、raw_field、raw_value；不可用 fallback 冒充模型成绩。",
]

GENERIC_STOP_REASONS = {
    "达到最大闭环轮次。",
    "上一轮未达到最小可验证改进，停止空转。",
    "未生成新的安全修正动作，停止空转。",
}

NO_FOLLOWUP_NOTICE = "第二轮没有新的合法补法，指标未变。"
NO_CHANGE_PRESENTATION = "第二轮没有新的合法补法，指标未变。下面只展示本次最好一轮。"


class ClosedLoopService:
    """Run bounded result-feedback iterations on top of the existing research agent."""

    VERSION = "closed-loop-v2-two-round-default"

    def __init__(
        self,
        agent_service: object,
        *,
        runner: Callable[..., AgentTaskResult] | None = None,
    ) -> None:
        self.agent_service = agent_service
        self._runner = runner
        self._runs: dict[str, ClosedLoopResponse] = {}
        self._lock = threading.Lock()

    def run(self, payload: ClosedLoopRequest, *, qwen_client: object | None = None) -> ClosedLoopResponse:
        loop_id = f"loop-{uuid4().hex[:12]}"
        current = payload.initial_request
        iterations: list[ClosedLoopIteration] = []
        seen_inputs: set[str] = set()
        previous_metrics: ClosedLoopMetricSnapshot | None = None
        stop_reason = "达到最大闭环轮次。"
        all_unresolved: list[str] = []

        for number in range(1, payload.max_iterations + 1):
            input_hash = self._hash(current.model_dump(mode="json"))
            duplicate_required_second_round = payload.require_two_rounds and number == 2 and input_hash in seen_inputs
            if input_hash in seen_inputs and not duplicate_required_second_round:
                stop_reason = "检测到重复闭环输入，停止以避免空转。"
                break
            seen_inputs.add(input_hash)
            result = self._execute(current, qwen_client=qwen_client, task_id=f"{loop_id}:r{number}")
            metrics = self._metrics(result, number)
            diagnoses = self._diagnose(result, metrics)
            unresolved = [field for item in diagnoses for field in item.unresolved_fields]
            all_unresolved = list(dict.fromkeys([*all_unresolved, *unresolved]))
            minimum_rounds_reached = number >= (2 if payload.require_two_rounds else 1)
            actions = self._actions(
                result,
                diagnoses,
                can_continue=number < payload.max_iterations,
                require_followup=payload.require_two_rounds and number < 2,
            )
            improvement = self._compare(previous_metrics, metrics, payload.min_improvement) if previous_metrics else None
            strategies = self._strategy_ids(result)
            audit = ClosedLoopAudit(
                iteration=number,
                input_hash=input_hash,
                output_hash=self._hash(result.model_dump(mode="json")),
                attempted_call_count=len(result.tool_calls),
                attempted_call_ids=[item.call_id for item in result.tool_calls],
                strategy_ids=strategies,
                safety_constraints=list(SAFETY_CONSTRAINTS),
                created_at=datetime.now(timezone.utc),
            )
            iterations.append(
                ClosedLoopIteration(
                    iteration=number,
                    input_request=current,
                    result=result,
                    metrics=metrics,
                    diagnoses=diagnoses,
                    actions=actions,
                    improvement=improvement,
                    audit=audit,
                )
            )

            gate_cleared = metrics.publish_allowed or not diagnoses
            if minimum_rounds_reached and gate_cleared:
                stop_reason = "质量门已通过，停止继续修正。"
                break
            if number >= payload.max_iterations:
                break
            if (
                payload.stop_on_no_improvement
                and improvement is not None
                and not improvement.improved
                and minimum_rounds_reached
            ):
                stop_reason = "上一轮未达到最小可验证改进，停止空转。"
                break
            next_request = self._correct_request(current, result, diagnoses)
            next_hash = self._hash(next_request.model_dump(mode="json"))
            force_verification = payload.require_two_rounds and number == 1 and gate_cleared
            material_followup = self._is_material_followup(current, next_request, result)
            if next_hash == input_hash and not force_verification:
                stop_reason = "第二轮没有新的合法补法，指标未变。"
                break
            if not material_followup and not force_verification:
                stop_reason = "第二轮没有新的合法补法，指标未变。"
                iterations[-1] = iterations[-1].model_copy(update={
                    "actions": [item.model_copy(update={"status": "skipped"}) for item in actions],
                })
                break
            iterations[-1] = iterations[-1].model_copy(update={
                "actions": [item.model_copy(update={"status": "applied"}) for item in actions],
            })
            current = next_request
            previous_metrics = metrics

        final_result = iterations[-1].result if iterations else None
        status = "completed" if iterations else "stopped"
        presented = self._present(iterations, stop_reason)
        if stop_reason in GENERIC_STOP_REASONS:
            stop_reason = presented["user_notice"]
        attempted = presented.get("attempted_repairs") or []
        if attempted and "没有新的合法补法" in stop_reason:
            stop_reason = "；".join(attempted)
        response = ClosedLoopResponse(
            loop_id=loop_id,
            status=status,
            completed_iterations=len(iterations),
            stop_reason=stop_reason,
            iterations=iterations,
            final_result=final_result,
            improvement_summary=presented["improvement_summary"],
            unresolved_items=all_unresolved,
            audit_notice=(
                f"{self.VERSION}：每轮输入/输出均有哈希和调用审计；闭环只修正检索策略与字段缺口，"
                "不改变医学事实或安全规则。progress_score 是任务内反馈指标，不是正式 benchmark 或 SDTI。"
            ),
            improved=presented["improved"],
            presentation=presented["presentation"],
            best_iteration=presented["best_iteration"],
            user_notice=presented["user_notice"],
            highlight_cards=presented["highlight_cards"],
            display_iterations=presented["display_iterations"],
            attempted_repairs=attempted,
        )
        with self._lock:
            self._runs[loop_id] = response
        return response

    def get(self, loop_id: str) -> ClosedLoopResponse | None:
        with self._lock:
            return self._runs.get(loop_id)

    def _execute(self, request: AgentTaskRequest, *, qwen_client: object | None, task_id: str) -> AgentTaskResult:
        if self._runner is not None:
            return self._runner(request, qwen_client=qwen_client, task_id=task_id)
        return self.agent_service.run(request, qwen_client=qwen_client, task_id=task_id)

    @staticmethod
    def _hash(value: object) -> str:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def _metrics(cls, result: AgentTaskResult, iteration: int) -> ClosedLoopMetricSnapshot:
        readiness = result.readiness
        coverage = float(readiness.requested_variable_coverage_rate or 0.0)
        target = readiness.target_match_rate
        if target is None:
            target = 1.0 if readiness.target_match else 0.0
        report = result.quality_gate_report
        traceability = float(report.traceability if report and report.traceability is not None else 0.0)
        quality_gate = report.overall if report else (
            result.collection_agent.quality_gate if result.collection_agent else "REVIEW"
        )
        publish_allowed = bool(report.publish_allowed) if report else quality_gate == "PASS"
        critical = len(result.collection_agent.critical_gaps) if result.collection_agent else 0
        unresolved_identity = result.data_alignment.unresolved_identity_row_count if result.data_alignment else 0
        unresolved = critical + min(int(unresolved_identity), 100)
        review = min(1.0, unresolved / max(1, result.modeling_dataset.row_count))
        progress = 0.45 * coverage + 0.25 * float(target) + 0.20 * traceability + 0.10 * (1.0 - min(1.0, unresolved / 5.0))
        return ClosedLoopMetricSnapshot(
            iteration=iteration,
            progress_score=max(0.0, min(1.0, progress)),
            required_field_coverage=max(0.0, min(1.0, coverage)),
            target_match_rate=max(0.0, min(1.0, float(target))),
            traceability=max(0.0, min(1.0, traceability)),
            unresolved_gap_count=unresolved,
            review_burden=review,
            quality_gate=quality_gate,
            publish_allowed=publish_allowed,
        )

    @staticmethod
    def _diagnose(result: AgentTaskResult, metrics: ClosedLoopMetricSnapshot) -> list[ClosedLoopDiagnosis]:
        diagnoses: list[ClosedLoopDiagnosis] = []
        collection = result.collection_agent
        critical = collection.critical_gaps if collection else []
        plan = diagnose_outcome_gap(
            spec=result.research_spec,
            dataset=result.modeling_dataset,
            target_match_rate=metrics.target_match_rate,
            question=result.research_spec.research_goal,
        )
        if critical:
            remaining = list(dict.fromkeys(item.variable_id for item in critical))
            if metrics.target_match_rate >= 0.45:
                remaining = [field for field in remaining if field not in {"outcome", "pcr", "treatment_response"}]
            if remaining:
                diagnoses.append(ClosedLoopDiagnosis(
                    diagnosis_id="missing_required_fields",
                    label="关键研究字段缺口",
                    severity="high",
                    evidence=[item.reason for item in critical[:5]],
                    unresolved_fields=remaining,
                    recommended_tools=["search_geo", "search_cbioportal", "inspect_dataset_schema"],
                ))
        if metrics.target_match_rate < 0.45:
            diagnoses.append(ClosedLoopDiagnosis(
                diagnosis_id="outcome_or_target_gap",
                label="结局或目标字段尚未充分匹配",
                severity="high",
                evidence=[
                    f"当前目标匹配率 {metrics.target_match_rate:.0%}",
                    plan.rationale or "需要补齐与 Research Contract 同域的结局。",
                ],
                unresolved_fields=["outcome"],
                recommended_tools=list(plan.focus_tools) or ["search_geo", "search_trials"],
                repair_kind=plan.gap_kind,
            ))
        elif plan.gap_kind == "wrong_cohort":
            diagnoses.append(ClosedLoopDiagnosis(
                diagnosis_id="outcome_or_target_gap",
                label="结局或目标字段尚未充分匹配",
                severity="high",
                evidence=[plan.rationale],
                unresolved_fields=["outcome"],
                recommended_tools=list(plan.focus_tools) or ["search_geo"],
                repair_kind=plan.gap_kind,
            ))
        if metrics.traceability < 0.95:
            diagnoses.append(ClosedLoopDiagnosis(
                diagnosis_id="traceability_gap",
                label="关键字段证据链不完整",
                severity="medium",
                evidence=[f"当前可追溯率 {metrics.traceability:.0%}，低于 95% 门槛"],
                unresolved_fields=["provenance"],
                recommended_tools=["check_provenance"],
            ))
        if not diagnoses and metrics.quality_gate not in {"PASS", "READY"}:
            diagnoses.append(ClosedLoopDiagnosis(
                diagnosis_id="quality_review",
                label="质量门仍需复核",
                severity="medium",
                evidence=[f"当前质量门 {metrics.quality_gate}"],
            ))
        return diagnoses

    @staticmethod
    def _actions(
        result: AgentTaskResult,
        diagnoses: list[ClosedLoopDiagnosis],
        *,
        can_continue: bool,
        require_followup: bool = False,
    ) -> list[ClosedLoopAction]:
        if not can_continue or (not diagnoses and not require_followup):
            return []
        collection = result.collection_agent
        strategies = [item.strategy_id for item in (collection.next_actions if collection else []) if item.strategy_id]
        return [ClosedLoopAction(
            action_id="closed-loop-correct-search",
            action_type="refocus_retrieval" if diagnoses else "supplemental_verification",
            status="planned",
            rationale=(
                next((item.evidence[-1] for item in diagnoses if item.evidence), "")
                or (
                    "把本轮诊断出的缺口显式写回下一轮输入，并优先使用尚未尝试的来源；不修改事实字段。"
                    if diagnoses else
                    "第一轮虽已通过质量门，第二轮仍执行独立完整性复核并补充证据；不修改事实字段。"
                )
            ),
            changed_request_fields=["question", "preferred_sources", "focus_accessions", "focus_tools", "iterative_collection"],
            strategy_ids=list(dict.fromkeys([
                *strategies,
                *[tool for item in diagnoses for tool in item.recommended_tools],
            ])),
        )]

    @classmethod
    def _unused_followups(cls, result: AgentTaskResult) -> list:
        collection = result.collection_agent
        return list(collection.next_actions) if collection and collection.next_actions else []

    @classmethod
    def _correct_request(cls, request: AgentTaskRequest, result: AgentTaskResult, diagnoses: list[ClosedLoopDiagnosis]) -> AgentTaskRequest:
        fields = list(dict.fromkeys(field for item in diagnoses for field in item.unresolved_fields))
        unused = cls._unused_followups(result)
        source_names = [item.source_name for item in unused if item.source_name]
        strategy_labels = [item.strategy_label or item.strategy_id or item.source_name for item in unused if item.source_name or item.strategy_id]
        plan = diagnose_outcome_gap(
            spec=result.research_spec,
            dataset=result.modeling_dataset,
            target_match_rate=result.readiness.target_match_rate,
            question=result.research_spec.research_goal,
        )
        focus_accessions = list(request.focus_accessions)
        focus_tools = list(request.focus_tools)
        for action in unused:
            focus_tools.append(action.tool_name)
            args = action.arguments or {}
            for key in ("accession", "nct_id", "study_id"):
                value = str(args.get(key) or "").strip()
                if value:
                    focus_accessions.append(value)
        focus_accessions.extend(plan.focus_accessions)
        focus_tools.extend(plan.focus_tools)
        critic = result.critic_report
        if plan.material and critic is not None:
            for item in getattr(critic, "diagnoses", []) or []:
                focus_tools.extend(
                    action
                    for action in (getattr(item, "recommended_actions", []) or [])
                    if str(action).startswith("search_")
                )
        tool_names = [item.tool_name for item in unused if item.tool_name]
        preferred = list(dict.fromkeys([
            *tool_names,
            *plan.focus_tools,
            *source_names,
            *request.preferred_sources,
        ]))[:20]
        focus_accessions = list(dict.fromkeys(focus_accessions))[:20]
        focus_tools = list(dict.fromkeys(focus_tools))[:20]
        readiness = result.readiness
        coverage = float(readiness.requested_variable_coverage_rate or 0.0)
        target = readiness.target_match_rate
        if target is None:
            target = 1.0 if readiness.target_match else 0.0
        tried = list(dict.fromkeys(result.collection_agent.strategies_tried if result.collection_agent else []))[:6]
        feedback = (
            f"；第一轮闭环反馈：协议必选字段对齐 {coverage:.0%}、目标匹配 {float(target):.0%}；"
            f"来源可回查 {float(result.quality_gate_report.traceability if result.quality_gate_report and result.quality_gate_report.traceability is not None else 0.0):.0%}"
        )
        if tried:
            feedback += "，已尝试策略 " + "、".join(tried)
        if strategy_labels:
            feedback += "；下一轮改用尚未尝试的 " + "、".join(strategy_labels[:4])
        if plan.rationale:
            feedback += "；" + plan.rationale
        if plan.forbidden_note:
            feedback += "；" + plan.forbidden_note
        suffix = "；闭环修正：优先补齐 " + "、".join(fields) if fields else "；闭环修正：复核质量门和证据链"
        if focus_accessions:
            suffix += "；强制改搜 " + "、".join(focus_accessions[:6])
        suffix += feedback
        question = request.question
        if suffix not in question:
            question = f"{question}{suffix}。保持同一患者/样本和 response_domain，不跨 cohort 粘贴字段。"
        extra_rounds = 2 if unused or plan.material else 0
        extra_sources = 2 if unused or plan.material else 0
        return request.model_copy(update={
            "question": question[:2000],
            "preferred_sources": preferred,
            "focus_accessions": focus_accessions,
            "focus_tools": focus_tools,
            "remap_outcome_aliases": plan.map_synonyms or request.remap_outcome_aliases,
            "iterative_collection": True,
            "max_collection_rounds": min(12, max(request.max_collection_rounds + extra_rounds, 4 if unused or plan.material else request.max_collection_rounds)),
            "max_sources": min(20, request.max_sources + extra_sources),
        })

    @classmethod
    def _is_material_followup(
        cls,
        request: AgentTaskRequest,
        next_request: AgentTaskRequest,
        result: AgentTaskResult,
    ) -> bool:
        if cls._unused_followups(result):
            return True
        if next_request.iterative_collection and not request.iterative_collection:
            return True
        if next_request.max_sources > request.max_sources:
            return True
        if next_request.max_collection_rounds > request.max_collection_rounds:
            return True
        if set(next_request.preferred_sources) - set(request.preferred_sources):
            return True
        if set(next_request.focus_accessions) - set(request.focus_accessions):
            return True
        if set(next_request.focus_tools) - set(request.focus_tools):
            added = set(next_request.focus_tools) - set(request.focus_tools)
            if any(str(item).startswith("search_") for item in added):
                return True
        if next_request.remap_outcome_aliases and not request.remap_outcome_aliases:
            return True
        plan = diagnose_outcome_gap(
            spec=result.research_spec,
            dataset=result.modeling_dataset,
            target_match_rate=result.readiness.target_match_rate,
            question=result.research_spec.research_goal,
        )
        return plan.material

    @classmethod
    def _compare(cls, previous: ClosedLoopMetricSnapshot, current: ClosedLoopMetricSnapshot, min_improvement: float) -> ClosedLoopImprovement:
        deltas = {
            "progress_score": current.progress_score - previous.progress_score,
            "required_field_coverage": current.required_field_coverage - previous.required_field_coverage,
            "target_match_rate": current.target_match_rate - previous.target_match_rate,
            "traceability": current.traceability - previous.traceability,
            "unresolved_gap_count": float(previous.unresolved_gap_count - current.unresolved_gap_count),
            "review_burden": previous.review_burden - current.review_burden,
        }
        improved = deltas["progress_score"] >= min_improvement or deltas["unresolved_gap_count"] > 0
        summary = cls._zh_delta_lines(previous, current)
        return ClosedLoopImprovement(
            from_iteration=previous.iteration,
            to_iteration=current.iteration,
            score_delta=deltas["progress_score"],
            metric_deltas=deltas,
            improved=improved,
            summary=summary,
        )

    @staticmethod
    def _strategy_ids(result: AgentTaskResult) -> list[str]:
        return list(dict.fromkeys(
            strategy
            for strategy in (result.collection_agent.strategies_tried if result.collection_agent else [])
            if strategy
        ))

    @staticmethod
    def _zh_delta_lines(first: ClosedLoopMetricSnapshot, last: ClosedLoopMetricSnapshot) -> list[str]:
        return [
            f"任务内进度：{first.progress_score:.2f} → {last.progress_score:.2f}",
            f"协议必选字段对齐：{first.required_field_coverage:.2f} → {last.required_field_coverage:.2f}",
            f"目标匹配：{first.target_match_rate:.2f} → {last.target_match_rate:.2f}",
            f"来源可回查：{first.traceability:.2f} → {last.traceability:.2f}",
            f"人工复核负担：{first.review_burden:.2f} → {last.review_burden:.2f}",
            f"未解决缺口：{first.unresolved_gap_count} → {last.unresolved_gap_count}",
        ]

    @classmethod
    def _highlight_cards(
        cls,
        metrics: ClosedLoopMetricSnapshot,
        previous: ClosedLoopMetricSnapshot | None = None,
    ) -> list[ClosedLoopHighlightCard]:
        def pct(value: float) -> str:
            return f"{value * 100:.1f}%"

        def lifted(current: float, attr: str) -> bool:
            return previous is not None and current > getattr(previous, attr) + 1e-9

        cards: list[ClosedLoopHighlightCard] = []
        if previous and metrics.progress_score > previous.progress_score + 1e-9:
            cards.append(ClosedLoopHighlightCard(
                label="任务内进度",
                value=f"{previous.progress_score:.2f} → {metrics.progress_score:.2f}",
                hint="只反映本任务闭环有没有补上缺口，不是正式 SDTI。",
                tone="good",
            ))
        coverage_lifted = lifted(metrics.required_field_coverage, "required_field_coverage")
        if coverage_lifted or metrics.required_field_coverage >= 0.01:
            coverage_hint = "协议要求的字段是否对上；与质量门的本题变量覆盖不是同一个口径。"
            if coverage_lifted:
                coverage_hint = "相对上一轮补上了部分协议必选字段。"
            cards.append(ClosedLoopHighlightCard(
                label="协议必选字段对齐",
                value=pct(metrics.required_field_coverage),
                hint=coverage_hint,
                tone="warn" if metrics.required_field_coverage < 0.8 else "good",
            ))
        target_lifted = lifted(metrics.target_match_rate, "target_match_rate")
        if target_lifted or metrics.target_match_rate >= 0.01:
            target_hint = "本题要的结局或目标字段是否对上。"
            if target_lifted:
                target_hint = "相对上一轮目标匹配有提升。"
            cards.append(ClosedLoopHighlightCard(
                label="目标匹配",
                value=pct(metrics.target_match_rate),
                hint=target_hint,
                tone="warn" if metrics.target_match_rate < 1.0 else "good",
            ))
        if metrics.traceability >= 0.01:
            cards.append(ClosedLoopHighlightCard(
                label="来源可回查",
                value=pct(metrics.traceability),
                hint="已登记来源能点回官方地址；这不是字段覆盖。",
                tone="muted",
            ))
        if metrics.unresolved_gap_count:
            cards.append(ClosedLoopHighlightCard(
                label="还剩缺口",
                value=str(metrics.unresolved_gap_count),
                hint="仍缺结局或必选研究字段。",
                tone="warn",
            ))
        return cards

    @classmethod
    def _best_iteration(cls, iterations: list[ClosedLoopIteration]) -> ClosedLoopIteration:
        return max(
            iterations,
            key=lambda item: (
                item.metrics.required_field_coverage,
                item.metrics.target_match_rate,
                item.metrics.progress_score,
                -item.metrics.unresolved_gap_count,
                -item.iteration,
            ),
        )

    @classmethod
    def _attempted_repair_lines(cls, iterations: list[ClosedLoopIteration]) -> list[str]:
        lines: list[str] = []
        if len(iterations) < 2:
            return lines
        second = iterations[1]
        accessions = list(second.input_request.focus_accessions)
        tools = list(second.input_request.focus_tools)
        calls = [
            f"{item.tool_name}:{item.arguments.get('accession') or item.arguments.get('nct_id') or item.arguments.get('study_id') or ''}".rstrip(":")
            for item in second.result.tool_calls
        ]
        if accessions:
            lines.append("第二轮已改搜 " + "、".join(accessions[:8]))
        if tools:
            lines.append("第二轮已调用工具 " + "、".join(tools[:8]))
        if calls:
            lines.append("第二轮实际工具 " + "、".join(item for item in calls[:8] if item))
        if second.input_request.remap_outcome_aliases:
            lines.append("第二轮已请求结局同义列映射，保留 raw_field/raw_value/source_id。")
        last = iterations[-1]
        if last.improvement is not None and not last.improvement.improved:
            remaining = [field for item in last.diagnoses for field in item.unresolved_fields]
            if remaining:
                lines.append("仍缺：" + "、".join(dict.fromkeys(remaining)) + "。未编造成绩。")
        return list(dict.fromkeys(lines))

    @classmethod
    def _present(cls, iterations: list[ClosedLoopIteration], stop_reason: str) -> dict:
        if not iterations:
            return {
                "improved": False,
                "presentation": "best_only",
                "best_iteration": 1,
                "user_notice": stop_reason or "尚未形成可展示的闭环结果。",
                "improvement_summary": ["尚未形成可展示的闭环结果。"],
                "highlight_cards": [],
                "display_iterations": [],
                "attempted_repairs": [],
            }
        best = cls._best_iteration(iterations)
        last_improvement = iterations[-1].improvement if len(iterations) >= 2 else None
        improved = bool(last_improvement and last_improvement.improved)
        attempted = cls._attempted_repair_lines(iterations)
        if len(iterations) < 2 or not improved:
            if attempted:
                notice = "；".join(attempted)
            else:
                notice = NO_CHANGE_PRESENTATION if len(iterations) >= 2 or NO_FOLLOWUP_NOTICE in stop_reason else (
                    stop_reason or "仅完成一轮诊断，下面展示这一轮结果。"
                )
                if len(iterations) < 2 and stop_reason == NO_FOLLOWUP_NOTICE:
                    notice = NO_CHANGE_PRESENTATION
            summary = attempted or (
                [NO_FOLLOWUP_NOTICE] if (len(iterations) >= 2 or stop_reason == NO_FOLLOWUP_NOTICE) else ["仅完成第一轮诊断，暂无前后轮改进对比。"]
            )
            return {
                "improved": False,
                "presentation": "best_only",
                "best_iteration": best.iteration,
                "user_notice": notice,
                "improvement_summary": summary,
                "highlight_cards": cls._highlight_cards(best.metrics),
                "display_iterations": [best.iteration],
                "attempted_repairs": attempted,
            }
        first = iterations[0].metrics
        last = iterations[-1].metrics
        return {
            "improved": True,
            "presentation": "comparison",
            "best_iteration": best.iteration,
            "user_notice": "第二轮相对第一轮有可验证改进。下面对比前后，并突出最好一轮。",
            "improvement_summary": cls._zh_delta_lines(first, last) + attempted,
            "highlight_cards": cls._highlight_cards(last, first),
            "display_iterations": [item.iteration for item in iterations],
            "attempted_repairs": attempted,
        }


__all__ = ["ClosedLoopService", "SAFETY_CONSTRAINTS"]
