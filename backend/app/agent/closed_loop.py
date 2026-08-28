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
    ClosedLoopImprovement,
    ClosedLoopIteration,
    ClosedLoopMetricSnapshot,
    ClosedLoopRequest,
    ClosedLoopResponse,
)
from backend.app.agent.models import AgentTaskRequest, AgentTaskResult


SAFETY_CONSTRAINTS = [
    "第二轮不得放宽患者/样本身份关联；低置信度关联继续保持 unresolved/review。",
    "第二轮不得自动修改 HER2 assay/status、response_domain/response 或关键 provenance。",
    "所有新字段仍必须保留 source_id、raw_field、raw_value；不可用 fallback 冒充模型成绩。",
]


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

            # A two-round run is the product default: the second pass is a
            # completeness/independent verification pass even when round one
            # already clears the quality gate.
            if minimum_rounds_reached and (metrics.publish_allowed or not diagnoses):
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
            if next_hash == input_hash and not (payload.require_two_rounds and number == 1):
                stop_reason = "未生成新的安全修正动作，停止空转。"
                break
            iterations[-1] = iterations[-1].model_copy(update={
                "actions": [item.model_copy(update={"status": "applied"}) for item in actions],
            })
            current = next_request
            previous_metrics = metrics

        final_result = iterations[-1].result if iterations else None
        status = "completed" if iterations else "stopped"
        summaries = self._summary(iterations)
        response = ClosedLoopResponse(
            loop_id=loop_id,
            status=status,
            completed_iterations=len(iterations),
            stop_reason=stop_reason,
            iterations=iterations,
            final_result=final_result,
            improvement_summary=summaries,
            unresolved_items=all_unresolved,
            audit_notice=(
                f"{self.VERSION}：每轮输入/输出均有哈希和调用审计；闭环只修正检索策略与字段缺口，"
                "不改变医学事实或安全规则。progress_score 是任务内反馈指标，不是正式 benchmark 或 SDTI。"
            ),
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
        if critical:
            fields = list(dict.fromkeys(item.variable_id for item in critical))
            diagnoses.append(ClosedLoopDiagnosis(
                diagnosis_id="missing_required_fields",
                label="关键研究字段缺口",
                severity="high",
                evidence=[item.reason for item in critical[:5]],
                unresolved_fields=fields,
            ))
        if metrics.target_match_rate < 1.0:
            diagnoses.append(ClosedLoopDiagnosis(
                diagnosis_id="outcome_or_target_gap",
                label="结局或目标字段尚未充分匹配",
                severity="high",
                evidence=[f"当前目标匹配率 {metrics.target_match_rate:.0%}"],
                unresolved_fields=["outcome"],
            ))
        if metrics.traceability < 0.95:
            diagnoses.append(ClosedLoopDiagnosis(
                diagnosis_id="traceability_gap",
                label="关键字段证据链不完整",
                severity="medium",
                evidence=[f"当前可追溯率 {metrics.traceability:.0%}，低于 95% 门槛"],
                unresolved_fields=["provenance"],
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
                "把本轮诊断出的缺口显式写回下一轮输入，并优先使用尚未尝试的来源；不修改事实字段。"
                if diagnoses else
                "第一轮虽已通过质量门，第二轮仍执行独立完整性复核并补充证据；不修改事实字段。"
            ),
            changed_request_fields=["question", "preferred_sources", "iterative_collection"],
            strategy_ids=list(dict.fromkeys(strategies)),
        )]

    @staticmethod
    def _correct_request(request: AgentTaskRequest, result: AgentTaskResult, diagnoses: list[ClosedLoopDiagnosis]) -> AgentTaskRequest:
        fields = list(dict.fromkeys(field for item in diagnoses for field in item.unresolved_fields))
        collection = result.collection_agent
        source_names = [item.source_name for item in (collection.next_actions if collection else []) if item.source_name]
        readiness = result.readiness
        coverage = float(readiness.requested_variable_coverage_rate or 0.0)
        target = readiness.target_match_rate
        if target is None:
            target = 1.0 if readiness.target_match else 0.0
        tried = list(dict.fromkeys(collection.strategies_tried if collection else []))[:6]
        feedback = (
            f"；第一轮闭环反馈：字段覆盖 {coverage:.0%}、目标匹配 {float(target):.0%}；"
            f"可追溯率 {float(result.quality_gate_report.traceability if result.quality_gate_report and result.quality_gate_report.traceability is not None else 0.0):.0%}"
        )
        if tried:
            feedback += "，已尝试策略 " + "、".join(tried)
        suffix = "；闭环修正：优先补齐 " + "、".join(fields) if fields else "；闭环修正：复核质量门和证据链"
        suffix += feedback
        question = request.question
        if suffix not in question:
            question = f"{question}{suffix}。保持同一患者/样本和 response_domain，不跨 cohort 粘贴字段。"
        return request.model_copy(update={
            "question": question[:2000],
            "preferred_sources": list(dict.fromkeys([*request.preferred_sources, *source_names]))[:20],
            "iterative_collection": True,
            "max_collection_rounds": max(2, request.max_collection_rounds),
        })

    @staticmethod
    def _compare(previous: ClosedLoopMetricSnapshot, current: ClosedLoopMetricSnapshot, min_improvement: float) -> ClosedLoopImprovement:
        deltas = {
            "progress_score": current.progress_score - previous.progress_score,
            "required_field_coverage": current.required_field_coverage - previous.required_field_coverage,
            "target_match_rate": current.target_match_rate - previous.target_match_rate,
            "traceability": current.traceability - previous.traceability,
            "unresolved_gap_count": float(previous.unresolved_gap_count - current.unresolved_gap_count),
            "review_burden": previous.review_burden - current.review_burden,
        }
        improved = deltas["progress_score"] >= min_improvement or deltas["unresolved_gap_count"] > 0
        summary = [
            f"required field coverage: {previous.required_field_coverage:.2f} -> {current.required_field_coverage:.2f}",
            f"target match: {previous.target_match_rate:.2f} -> {current.target_match_rate:.2f}",
            f"traceability: {previous.traceability:.2f} -> {current.traceability:.2f}",
            f"review burden: {previous.review_burden:.2f} -> {current.review_burden:.2f}",
            f"unresolved gaps: {previous.unresolved_gap_count} -> {current.unresolved_gap_count}",
        ]
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
    def _summary(iterations: list[ClosedLoopIteration]) -> list[str]:
        if len(iterations) < 2:
            return ["仅完成第一轮诊断，暂无前后轮改进对比。"]
        first = iterations[0].metrics
        last = iterations[-1].metrics
        return [
            f"progress score: {first.progress_score:.2f} -> {last.progress_score:.2f}",
            f"required field coverage: {first.required_field_coverage:.2f} -> {last.required_field_coverage:.2f}",
            f"target match: {first.target_match_rate:.2f} -> {last.target_match_rate:.2f}",
            f"traceability: {first.traceability:.2f} -> {last.traceability:.2f}",
            f"review burden: {first.review_burden:.2f} -> {last.review_burden:.2f}",
            f"unresolved gaps: {first.unresolved_gap_count} -> {last.unresolved_gap_count}",
        ]


__all__ = ["ClosedLoopService", "SAFETY_CONSTRAINTS"]
