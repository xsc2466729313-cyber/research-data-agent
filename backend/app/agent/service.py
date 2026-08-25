from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.app.agent.competition_report import CompetitionReportBuilder
from backend.app.agent.accession_harvest import catalog_query, harvest_from_raw_results, literature_query
from backend.app.agent.alignment_audit import DataAlignmentAuditor
from backend.app.agent.collection_agent import CollectionAgent
from backend.app.agent.goal_loop import DIAGNOSIS_LABELS
from backend.app.agent.dataset_builder import ResearchDatasetBuilder
from backend.app.agent.models import (
    AgentConfigurationStatus,
    AgentDataMode,
    AgentPlanStep,
    AgentTaskRequest,
    AgentTaskResult,
    AgentToolCall,
    ResearchTaskStatus,
)
from backend.app.agent.qwen_client import QwenClient, QwenClientError, QwenSettings
from backend.app.agent.quality_gate import QualityGateBuilder
from backend.app.agent.research_parser import ResearchQuestionParser
from backend.app.agent.study_design import StudyDesignBuilder
from backend.app.agent.source_registry import (
    GEO_ACCESSION_PATTERN,
    MAX_ENTRIES_PER_TOOL,
    MAX_SOURCE_ENTRIES,
    call_key,
    entry_key,
    is_breast_cancer_study_id,
    is_gdc_breast_project_id,
)
from backend.app.models import (
    CandidateSource,
    ResearchSpec,
    SearchPlan,
    SearchPlanItem,
    SourceItem,
)
from backend.app.sources.aact import AACTClinicalTrialsAdapter
from backend.app.sources.aact.models import AACTAdapterOptions, AACTAdapterRequest
from backend.app.sources.cbioportal import CBioPortalAdapter
from backend.app.sources.cbioportal.models import (
    CBioPortalAdapterOptions,
    CBioPortalAdapterRequest,
    CBioPortalAdapterResult,
)
from backend.app.sources.civic import CIViCAdapter
from backend.app.sources.civic.models import CIViCAdapterOptions, CIViCAdapterRequest
from backend.app.sources.discovery import DiscoveryAdapter, DiscoveryAdapterError
from backend.app.sources.gdc import GDCAdapter
from backend.app.sources.gdc.models import GDCAdapterOptions, GDCAdapterRequest
from backend.app.sources.geo import GEOAdapter
from backend.app.sources.geo.models import (
    GEOAdapterOptions,
    GEOAdapterRequest,
    GEOAdapterResult,
    GEOResourceType,
)


class AgentConfigurationError(RuntimeError):
    pass


class AgentExecutionError(RuntimeError):
    pass


logger = logging.getLogger(__name__)


TOOL_LABELS = {
    "search_gdc": "检索 GDC / TCGA",
    "search_geo": "检索 NCBI GEO",
    "search_geo_catalog": "检索 NCBI GEO 目录",
    "search_cbioportal": "检索 cBioPortal 患者队列",
    "search_trials": "检索 ClinicalTrials.gov",
    "search_civic": "检索 CIViC 医学证据",
    "search_biosample": "检索 NCBI BioSample 样本元数据",
    "search_europe_pmc": "检索 Europe PMC 文献证据",
}

FOLLOW_UP_BUDGET = 4


class ResearchAgentService:
    def __init__(
        self,
        *,
        qwen_client: QwenClient | None = None,
        gdc_adapter: GDCAdapter | None = None,
        geo_adapter: GEOAdapter | None = None,
        cbioportal_adapter: CBioPortalAdapter | None = None,
        aact_adapter: AACTClinicalTrialsAdapter | None = None,
        civic_adapter: CIViCAdapter | None = None,
        discovery_adapter: DiscoveryAdapter | None = None,
        dataset_builder: ResearchDatasetBuilder | None = None,
    ) -> None:
        self._qwen_injected = qwen_client is not None
        self.qwen = qwen_client or QwenClient()
        self.gdc = gdc_adapter or GDCAdapter()
        self.geo = geo_adapter or GEOAdapter()
        self.cbioportal = cbioportal_adapter or CBioPortalAdapter()
        self.aact = aact_adapter or AACTClinicalTrialsAdapter()
        self.civic = civic_adapter or CIViCAdapter()
        self.discovery = discovery_adapter or DiscoveryAdapter()
        self.dataset_builder = dataset_builder or ResearchDatasetBuilder()
        self.alignment_auditor = DataAlignmentAuditor()
        self.competition_report_builder = CompetitionReportBuilder()
        self.study_design_builder = StudyDesignBuilder()
        self.collection_agent = CollectionAgent()
        self.question_parser = ResearchQuestionParser()
        self.quality_gate_builder = QualityGateBuilder()
        self._results: dict[str, AgentTaskResult] = {}
        self._statuses: dict[str, ResearchTaskStatus] = {}
        self._lock = threading.Lock()

    def _refresh_env_qwen(self) -> None:
        if self._qwen_injected:
            return
        settings = QwenSettings.from_env()
        current = self.qwen.settings
        if (
            settings.api_key == current.api_key
            and settings.base_url == current.base_url
            and settings.model == current.model
            and settings.workspace_id == current.workspace_id
        ):
            return
        self.qwen = QwenClient(settings=settings)

    def configuration(self) -> AgentConfigurationStatus:
        self._refresh_env_qwen()
        settings = self.qwen.settings
        configured = settings.configured
        return AgentConfigurationStatus(
            configured=configured,
            model=settings.model,
            base_url_configured=bool(settings.base_url),
            workspace_configured=bool(settings.workspace_id or ".maas.aliyuncs.com" in settings.base_url),
            message=(
                "千问已配置，可执行结构化规划和函数调用。"
                if configured
                else "未配置千问凭据；可使用确定性规划兜底，但不属于完整千问 Agent 模式。"
            ),
        )

    def get(self, task_id: str) -> AgentTaskResult | None:
        with self._lock:
            return self._results.get(task_id)

    def status(self, task_id: str) -> ResearchTaskStatus | None:
        with self._lock:
            return self._statuses.get(task_id)

    def start(
        self,
        request: AgentTaskRequest,
        *,
        qwen_client: QwenClient | None = None,
    ) -> ResearchTaskStatus:
        task_id = f"agent-{uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc)
        status = ResearchTaskStatus(
            task_id=task_id,
            status="running",
            stage="理解问题",
            progress=8,
            message="正在解析科研问题并生成研究设计。",
            created_at=created_at,
        )
        with self._lock:
            self._statuses[task_id] = status
        worker = threading.Thread(
            target=self._run_background,
            args=(task_id, request, qwen_client),
            daemon=True,
            name=f"research-task-{task_id}",
        )
        worker.start()
        return status

    def _run_background(
        self,
        task_id: str,
        request: AgentTaskRequest,
        qwen_client: QwenClient | None,
    ) -> None:
        try:
            self.run(request, qwen_client=qwen_client, task_id=task_id)
            self._set_status(
                task_id,
                status="completed",
                stage="质量检查",
                progress=100,
                message="科研数据任务已完成。",
            )
        except AgentConfigurationError as exc:
            self._set_status(task_id, status="failed", stage="理解问题", progress=100, message=str(exc), error=str(exc))
        except AgentExecutionError as exc:
            self._set_status(task_id, status="failed", stage="搜索数据库", progress=100, message=str(exc), error=str(exc))
        except Exception:
            logger.exception("Background research task failed task_id=%s", task_id)
            self._set_status(
                task_id,
                status="failed",
                stage="质量检查",
                progress=100,
                message="科研任务执行失败。",
                error="科研任务执行失败。请重试；若持续失败，请提供该任务编号。",
            )

    def _set_status(
        self,
        task_id: str,
        *,
        status: str,
        stage: str,
        progress: int,
        message: str,
        error: str | None = None,
    ) -> None:
        with self._lock:
            current = self._statuses.get(task_id)
            created_at = current.created_at if current is not None else datetime.now(timezone.utc)
            self._statuses[task_id] = ResearchTaskStatus(
                task_id=task_id,
                status=status,
                stage=stage,
                progress=progress,
                message=message,
                error=error,
                created_at=created_at,
            )

    def run(
        self,
        request: AgentTaskRequest,
        *,
        qwen_client: QwenClient | None = None,
        task_id: str | None = None,
    ) -> AgentTaskResult:
        if qwen_client is None:
            self._refresh_env_qwen()
        active_qwen = qwen_client or self.qwen
        task_id = task_id or f"agent-{uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc)
        plan_steps = [
            AgentPlanStep(step_id="理解问题", label="解析科研问题", status="进行中", detail="提取疾病、人群、暴露、结局和所需变量。"),
            AgentPlanStep(step_id="研究设计", label="生成研究设计与数据规划", status="等待", detail="判断研究类型并推荐数据库与字段。"),
            AgentPlanStep(step_id="搜索数据库", label="搜索并解析公开数据库", status="等待", detail="执行受控、可审计的数据库工具。"),
            AgentPlanStep(step_id="数据整合", label="Schema 匹配与实体对齐", status="等待", detail="统一字段、关联患者/样本，禁止无证据合并。"),
            AgentPlanStep(step_id="质量检查", label="质量门检查", status="等待", detail="来源可信、字段质量、实体一致性和科研适用性。"),
        ]

        qwen_used = False
        agent_mode = "确定性科研规划"
        tool_message: dict[str, Any] | None = None
        qwen_warning: str | None = None
        if request.use_qwen:
            if not active_qwen.available and not request.allow_deterministic_fallback:
                raise AgentConfigurationError(
                    "千问模式需要 DASHSCOPE_API_KEY 与 QWEN_BASE_URL。"
                )
            if active_qwen.available:
                try:
                    spec = active_qwen.extract_research_spec(request.question, task_id)
                    qwen_used = True
                    agent_mode = "千问科研数据智能体"
                except QwenClientError as exc:
                    if not request.allow_deterministic_fallback:
                        raise AgentExecutionError(str(exc)) from exc
                    spec = self._deterministic_spec(request.question, task_id)
                    qwen_warning = f"千问问题解析失败，已使用确定性兜底：{exc}"
            else:
                spec = self._deterministic_spec(request.question, task_id)
                qwen_warning = "未配置千问凭据，已使用确定性规划兜底。"
        else:
            spec = self._deterministic_spec(request.question, task_id)
        spec = self._enrich_research_spec(spec, request.question)
        plan_steps[0].status = "完成"
        plan_steps[0].detail = f"识别疾病 {spec.disease}；基因 {', '.join(spec.genes) or '未指定'}；结局 {', '.join(spec.outcomes) or '未指定'}。"
        self._set_status(
            task_id,
            status="running",
            stage="研究设计",
            progress=22,
            message="正在生成研究设计与数据规划。",
        )

        calls: list[dict[str, Any]] = []
        if qwen_used:
            try:
                tool_message, calls = active_qwen.choose_tools(
                    spec,
                    max_sources=request.max_sources,
                    preferred_sources=request.preferred_sources,
                )
            except QwenClientError as exc:
                if not request.allow_deterministic_fallback:
                    raise AgentExecutionError(str(exc)) from exc
                qwen_warning = f"千问工具选择失败，已使用确定性兜底：{exc}"
        deterministic_calls = self._deterministic_tool_calls(spec, request)
        if calls:
            calls = self._merge_tool_calls(calls, deterministic_calls, request.max_sources)
            calls = self._guard_tool_arguments(calls, spec, request)
            if tool_message is not None:
                tool_message = self._synchronize_tool_message(tool_message, calls)
        else:
            calls = self._guard_tool_arguments(deterministic_calls, spec, request)
            tool_message = None
        plan_steps[1].status = "完成"
        plan_steps[1].detail = "已规划数据源并选择：" + "、".join(
            TOOL_LABELS.get(call["name"], call["name"]) for call in calls
        )
        self._set_status(
            task_id,
            status="running",
            stage="搜索数据库",
            progress=40,
            message="正在搜索并解析公开数据库。",
        )

        executed: list[AgentToolCall] = []
        raw_results: list[tuple[str, Any]] = []
        candidates: list[CandidateSource] = []
        source_items: list[SourceItem] = []
        iterations = []
        collection_actions = []
        critical_gaps = []
        recommended_gaps = []
        attempted_calls: set[str] = set()
        pending_calls = list(calls)
        last_decision = None
        strategies_tried: list[str] = []
        max_rounds = (
            min(request.max_collection_rounds, self.collection_agent.max_rounds)
            if request.iterative_collection
            else 1
        )
        dataset, readiness = self.dataset_builder.empty()
        provisional_design, provisional_cohort = self.study_design_builder.build(
            spec,
            dataset,
            readiness,
            [],
            [],
            request.data_mode.value,
        )

        for round_number in range(1, max_rounds + 1):
            round_actions: list[str] = []
            if request.data_mode == AgentDataMode.LIVE:
                for call in pending_calls:
                    attempted_calls.add(CollectionAgent.call_key(call))
                    log, raw_result = self._execute_tool(call, spec, request.max_records)
                    executed.append(log)
                    if raw_result is not None:
                        raw_results.append((call["name"], raw_result))
                        try:
                            candidates.extend(self._candidates(call["name"], raw_result))
                        except Exception as exc:
                            logger.exception("Failed to register candidates for tool %s", call["name"])
                            executed[-1] = log.model_copy(
                                update={
                                    "message": f"{log.message} 候选来源登记失败：{type(exc).__name__}。"
                                }
                            )
                        source_items.extend(getattr(raw_result, "source_items", []))
                pending_calls = []
            elif round_number > 1:
                break

            built_datasets: list[tuple[Any, Any]] = []
            for name, raw_result in raw_results:
                if name == "search_cbioportal" and isinstance(raw_result, CBioPortalAdapterResult):
                    built_datasets.append(self.dataset_builder.build_from_cbioportal(raw_result, spec))
                elif name == "search_geo" and isinstance(raw_result, GEOAdapterResult):
                    geo_dataset = self.dataset_builder.build_from_geo(raw_result, spec)
                    if geo_dataset is not None:
                        built_datasets.append(geo_dataset)
            if built_datasets:
                dataset, readiness = max(
                    built_datasets,
                    key=lambda item: self._dataset_selection_score(item, spec),
                )
                switched_from_unmatched = readiness.target_match and any(
                    not other_readiness.target_match for _, other_readiness in built_datasets
                )
                if switched_from_unmatched:
                    readiness.warnings.insert(
                        0,
                        "已切换到含治疗响应的独立队列；未把其他研究的分子字段拼到该队列患者上。",
                    )
                    readiness.recommendations.insert(
                        0,
                        "PIK3CA 等分子暴露必须来自同一研究的患者/样本检测，不能用 METABRIC 突变补到 GEO 响应队列。",
                    )
            else:
                dataset, readiness = self.dataset_builder.empty()
                if raw_results:
                    readiness.warnings.insert(
                        0,
                        "已检索到来源或关系表，但当前结果不包含可直接解析的患者/样本级数据文件。",
                    )

            provisional_design, provisional_cohort = self.study_design_builder.build(
                spec,
                dataset,
                readiness,
                self._deduplicate_candidates(candidates),
                self._deduplicate_sources(source_items),
                request.data_mode.value,
            )
            iteration, critical, recommended = self.collection_agent.inspect(
                spec=spec,
                dataset=dataset,
                readiness=readiness,
                design=provisional_design,
                source_names=[item.source_name for item in source_items],
                source_items=source_items,
                round_number=round_number,
                attempted_calls=attempted_calls,
                actions=round_actions,
            )
            decision = self.collection_agent.decide(
                spec=spec,
                dataset=dataset,
                readiness=readiness,
                gaps=critical,
                attempted_calls=attempted_calls,
                max_records=request.max_records,
                round_number=round_number,
                max_rounds=max_rounds,
                cohort=provisional_cohort,
            )
            last_decision = decision
            iteration = iteration.model_copy(
                update={
                    "phase": "观察-诊断-换方法",
                    "status": (
                        "已达成目标"
                        if decision.action == "stop_pass"
                        else "主目标已达成"
                        if decision.action == "stop_partial"
                        else "方法已用尽"
                        if decision.action == "stop_exhausted"
                        else "准备更换方法"
                    ),
                    "quality_gate": decision.quality_gate,
                    "diagnosis": decision.diagnosis,
                    "diagnosis_label": DIAGNOSIS_LABELS.get(decision.diagnosis, decision.diagnosis),
                    "decision": decision.action,
                    "strategy_ids": decision.next_strategy_ids,
                    "goals_met": [goal.label for goal in decision.goals if goal.met],
                    "goals_open": [goal.label for goal in decision.goals if goal.required and not goal.met],
                    "note": decision.note,
                    "actions": round_actions or [decision.note],
                }
            )
            iterations.append(iteration)
            critical_gaps = critical
            recommended_gaps = recommended
            self._set_status(
                task_id,
                status="running",
                stage="搜索数据库",
                progress=min(40 + round_number * 8, 68),
                message=f"第 {round_number} 轮：{decision.note}",
            )

            if request.data_mode != AgentDataMode.LIVE or decision.action == "stop_pass":
                collection_actions = decision.actions
                break
            follow_up_calls = self._autonomous_follow_up_calls(
                spec=spec,
                request=request,
                decision=decision,
                raw_results=raw_results,
                critical=critical,
                dataset=dataset,
                readiness=readiness,
                attempted_calls=attempted_calls,
                qwen_client=active_qwen if qwen_used else None,
                round_number=round_number,
                max_rounds=max_rounds,
            )
            if not follow_up_calls or round_number >= max_rounds:
                collection_actions = decision.actions
                break
            pending_calls = self._guard_tool_arguments(
                follow_up_calls,
                spec,
                request.model_copy(update={"max_sources": min(FOLLOW_UP_BUDGET, request.max_sources)}),
            )
            pending_calls = [
                call
                for call in pending_calls
                if CollectionAgent.call_key(call) not in attempted_calls
            ]
            if not pending_calls:
                collection_actions = decision.actions
                break
            strategies_tried.extend(action.strategy_id or action.action_id for action in (decision.actions or []))
            round_actions = [
                f"{call['name']}：{json.dumps(call.get('arguments') or {}, ensure_ascii=False)}"
                for call in pending_calls
            ]
            if iterations:
                iterations[-1] = iterations[-1].model_copy(
                    update={
                        "status": "准备更换方法",
                        "actions": round_actions,
                        "note": f"{decision.note} 自主补搜 {len(pending_calls)} 个入口。",
                    }
                )

        if request.data_mode == AgentDataMode.LIVE:
            success_count = sum(item.status == "完成" for item in executed)
            plan_steps[2].status = "完成" if success_count else "失败"
            plan_steps[2].detail = (
                f"完成 {len(iterations)} 轮搜集；{success_count}/{len(executed)} 个工具成功；"
                f"登记 {len(source_items)} 个真实来源。"
            )
        else:
            plan_steps[2].status = "跳过"
            plan_steps[2].detail = "当前为仅规划模式，未访问外部数据库；质量门仅展示待执行规则。"
        self._set_status(
            task_id,
            status="running",
            stage="数据整合",
            progress=72,
            message="正在进行 Schema 匹配与实体对齐。",
        )

        plan_steps[3].status = "完成" if dataset.row_count else "数据不足"
        plan_steps[3].detail = (
            f"生成 {dataset.row_count} 行、{len(dataset.columns)} 列科研宽表；"
            f"实体匹配将按研究命名空间判定 MATCH/REVIEW/UNMATCH。"
        )
        plan_steps[4].status = "完成"
        plan_steps[4].detail = "正在汇总来源、字段、实体和科研适用性质量门。"
        self._set_status(
            task_id,
            status="running",
            stage="质量检查",
            progress=88,
            message="正在执行四层质量门检查。",
        )

        summary = self._fallback_summary(dataset.row_count, readiness.warnings)
        if qwen_used and tool_message is not None and executed:
            tool_summaries = [
                {
                    "call_id": item.call_id,
                    "tool": item.tool_name,
                    "status": item.status,
                    "source_count": item.source_count,
                    "record_count": item.record_count,
                    "message": item.message,
                }
                for item in executed
            ]
            try:
                summary = active_qwen.summarize(
                    request.question,
                    spec,
                    tool_message,
                    tool_summaries,
                    {
                        "dataset_name": dataset.name,
                        "unit_of_analysis": dataset.unit_of_analysis,
                        "row_count": dataset.row_count,
                        "patient_count": dataset.patient_count,
                        "sample_count": dataset.sample_count,
                        "column_count": len(dataset.columns),
                        "column_names": [column.name for column in dataset.columns],
                        "target_column": dataset.target_column,
                        "class_distribution": dataset.class_distribution,
                    },
                    readiness.model_dump(mode="json"),
                )
            except QwenClientError as exc:
                qwen_warning = f"千问总结失败，保留确定性质量报告：{exc}"

        notice_parts = [
            "主结果来自真实公开数据库工具；仅规划模式不会生成或冒充患者数据。",
            "千问负责科研问题结构化、工具选择和数据层总结；医学安全规则与发布门控不由模型覆盖。",
        ]
        if qwen_warning:
            notice_parts.append(qwen_warning)
        result = AgentTaskResult(
            task_id=task_id,
            status="完成" if any(item.status == "完成" for item in executed) or request.data_mode == AgentDataMode.PLAN_ONLY else "部分失败",
            agent_mode=agent_mode,
            model_provider="阿里云百炼 / 千问",
            model_name=active_qwen.settings.model,
            used_qwen=qwen_used,
            notice=" ".join(notice_parts),
            research_spec=spec,
            parsed_question=self.question_parser.parse(request.question, spec, provisional_design),
            plan=plan_steps,
            tool_calls=executed,
            candidate_sources=self._deduplicate_candidates(candidates),
            source_items=self._deduplicate_sources(source_items),
            modeling_dataset=dataset,
            readiness=readiness,
            summary_zh=summary,
            created_at=created_at,
        )
        collection_report = None
        alignment_report = None
        competition_report = None
        try:
            collection_report = self.collection_agent.report(
                iterations=iterations,
                critical=critical_gaps,
                recommended=recommended_gaps,
                actions=collection_actions,
                source_coverage=self._source_coverage(source_items),
                max_rounds=max_rounds,
                stop_reason=last_decision.note if last_decision is not None else "",
                diagnosis=last_decision.diagnosis if last_decision is not None else None,
                goals=last_decision.goals if last_decision is not None else [],
                strategies_tried=list(dict.fromkeys(strategies_tried)),
            )
        except Exception:
            logger.exception("Failed to build collection report for task %s", task_id)
        try:
            alignment_report = self.alignment_auditor.build(
                dataset,
                self._deduplicate_sources(source_items),
            )
        except Exception:
            logger.exception("Failed to build alignment report for task %s", task_id)
            alignment_report = None
        result = result.model_copy(
            update={
                "study_design": provisional_design,
                "cohort_construction": provisional_cohort,
                "collection_agent": collection_report,
                "data_alignment": alignment_report,
            }
        )
        try:
            competition_report = self.competition_report_builder.build(result)
        except Exception:
            logger.exception("Failed to build competition report for task %s", task_id)
            competition_report = None
        result = result.model_copy(update={"competition_report": competition_report})
        try:
            quality_gate_report = self.quality_gate_builder.build(result)
        except Exception:
            logger.exception("Failed to build quality gate report for task %s", task_id)
            quality_gate_report = None
        if quality_gate_report is not None:
            plan_steps[4].detail = (
                f"总体质量门：{quality_gate_report.overall}；"
                f"变量覆盖={'未计算' if quality_gate_report.variable_coverage is None else f'{quality_gate_report.variable_coverage:.1%}'}；"
                f"可追溯率={'未计算' if quality_gate_report.traceability is None else f'{quality_gate_report.traceability:.1%}'}。"
            )
        result = result.model_copy(
            update={
                "quality_gate_report": quality_gate_report,
                "plan": list(plan_steps),
            }
        )
        with self._lock:
            self._results[task_id] = result
        self._set_status(
            task_id,
            status="completed",
            stage="质量检查",
            progress=100,
            message="科研数据任务已完成。",
        )
        return result

    def _execute_tool(
        self,
        call: dict[str, Any],
        spec: ResearchSpec,
        max_records: int,
    ) -> tuple[AgentToolCall, Any | None]:
        started = datetime.now(timezone.utc)
        name = str(call.get("name") or "")
        arguments = dict(call.get("arguments") or {})
        call_id = str(call.get("id") or f"call-{uuid4().hex[:8]}")
        safe_arguments: dict[str, Any] = {}
        try:
            result = self._dispatch(name, arguments, spec, max_records)
            safe_arguments = self._safe_arguments(name, arguments)
            source_count = len(getattr(result, "source_items", []))
            record_count = self._record_count(result)
            message = f"真实接口调用成功；返回 {record_count} 条记录/资源，登记 {source_count} 个来源。"
            status = "完成"
        except Exception as exc:  # adapters expose structured domain errors upstream
            result = None
            safe_arguments = self._safe_arguments(name, arguments)
            source_count = 0
            record_count = 0
            status = "失败"
            message = f"{type(exc).__name__}: {exc}"
        completed = datetime.now(timezone.utc)
        return (
            AgentToolCall(
                call_id=call_id,
                tool_name=name,
                tool_label=TOOL_LABELS.get(name, name or "未知工具"),
                arguments=safe_arguments,
                status=status,
                source_count=source_count,
                record_count=record_count,
                message=message,
                started_at=started,
                completed_at=completed,
            ),
            result,
        )

    def _autonomous_follow_up_calls(
        self,
        *,
        spec: ResearchSpec,
        request: AgentTaskRequest,
        decision: Any,
        raw_results: list[tuple[str, Any]],
        critical: list[Any],
        dataset: Any,
        readiness: Any,
        attempted_calls: set[str],
        qwen_client: QwenClient | None,
        round_number: int,
        max_rounds: int,
    ) -> list[dict[str, Any]]:
        harvested = harvest_from_raw_results(raw_results, spec)
        harvest_calls = [
            {
                "id": f"harvest-geo-{accession}",
                "name": "search_geo",
                "arguments": {"accession": accession, "max_files": 5},
            }
            for accession in harvested
        ]
        loop_calls = [
            call
            for call in (
                self._follow_up_call(action, spec, request.max_records)
                for action in (decision.actions or [])
            )
            if call is not None
        ]
        qwen_calls: list[dict[str, Any]] = []
        planner = getattr(qwen_client, "plan_next_tools", None) if qwen_client is not None else None
        if callable(planner) and getattr(qwen_client, "available", False):
            try:
                qwen_calls = planner(
                    spec,
                    {
                        "diagnosis": decision.diagnosis,
                        "diagnosis_label": DIAGNOSIS_LABELS.get(decision.diagnosis, decision.diagnosis),
                        "quality_gate": decision.quality_gate,
                        "goals_open": [goal.label for goal in decision.goals if goal.required and not goal.met],
                        "critical_gaps": [getattr(gap, "label", str(gap)) for gap in critical],
                        "row_count": getattr(dataset, "row_count", 0),
                        "target_match": bool(getattr(readiness, "target_match", False)),
                        "harvested_gse": harvested,
                        "attempted_calls": sorted(attempted_calls)[:50],
                        "round_number": round_number,
                        "max_rounds": max_rounds,
                    },
                    max_calls=FOLLOW_UP_BUDGET,
                )
            except QwenClientError:
                logger.exception("Qwen next-tool planning failed for task %s", spec.task_id)
        merged = self._merge_tool_calls(qwen_calls, harvest_calls + loop_calls, FOLLOW_UP_BUDGET)
        return [
            call
            for call in merged
            if CollectionAgent.call_key(call) not in attempted_calls
        ]

    def _follow_up_call(
        self,
        action: Any,
        spec: ResearchSpec,
        max_records: int,
    ) -> dict[str, Any] | None:
        if action.tool_name in {
            "search_cbioportal",
            "search_geo",
            "search_geo_catalog",
            "search_gdc",
            "search_trials",
            "search_civic",
            "search_biosample",
            "search_europe_pmc",
        }:
            arguments = dict(action.arguments or {})
            arguments.setdefault("max_records", max_records)
            return {
                "id": action.action_id,
                "name": action.tool_name,
                "arguments": arguments,
            }
        return None

    @staticmethod
    def _source_coverage(source_items: list[SourceItem]) -> dict[str, str]:
        coverage: dict[str, str] = {}
        for item in source_items:
            current = coverage.get(item.source_name)
            if current is None:
                coverage[item.source_name] = item.status
            elif current != "retrieved" and item.status in {"retrieved", "downloaded", "cached"}:
                coverage[item.source_name] = item.status
        return coverage

    def _dispatch(
        self,
        name: str,
        args: dict[str, Any],
        spec: ResearchSpec,
        max_records: int,
    ) -> Any:
        source_names = {
            "search_gdc": "GDC",
            "search_geo": "GEO",
            "search_geo_catalog": "GEO",
            "search_cbioportal": "cBioPortal",
            "search_trials": "AACT",
            "search_civic": "CIViC",
            "search_biosample": "BioSample",
            "search_europe_pmc": "Europe PMC",
        }
        if name not in source_names:
            raise ValueError(f"千问请求了未注册工具：{name}")
        plan = SearchPlan(
            task_id=spec.task_id,
            plans=[
                SearchPlanItem(
                    source=source_names[name],
                    goal=TOOL_LABELS[name],
                    priority=1,
                    mode="live",
                )
            ],
        )
        if name == "search_gdc":
            options = GDCAdapterOptions(
                project_id=str(args.get("project_id") or "TCGA-BRCA"),
                data_types=list(args.get("data_types") or ["Clinical Supplement"]),
                max_files=min(int(args.get("max_files") or 5), 20),
                download=False,
            )
            return self.gdc.run(GDCAdapterRequest(research_spec=spec, search_plan=plan, options=options))
        if name == "search_geo":
            accession = str(args.get("accession") or self._default_geo_accession(spec))
            options = GEOAdapterOptions(
                accession=accession,
                max_files_per_type=min(int(args.get("max_files") or 5), 20),
                resource_types=[GEOResourceType.SERIES_MATRIX],
                download=True,
                max_download_bytes=30_000_000,
            )
            return self.geo.run(GEOAdapterRequest(search_plan=plan, options=options))
        if name == "search_cbioportal":
            genes = [
                str(gene).strip().upper()
                for gene in (args.get("gene_symbols") or spec.genes or ["ERBB2", "PIK3CA"])
                if str(gene).strip()
            ]
            options = CBioPortalAdapterOptions(
                study_id=str(args.get("study_id") or "brca_metabric"),
                gene_symbols=list(dict.fromkeys(genes))[:20],
                max_records_per_table=min(int(args.get("max_records") or max_records), max_records),
            )
            return self.cbioportal.run(CBioPortalAdapterRequest(search_plan=plan, options=options))
        if name == "search_trials":
            options = AACTAdapterOptions(
                condition=str(args.get("condition") or spec.disease),
                query_terms=self._optional_text(args.get("query_terms")),
                max_trials=min(int(args.get("max_trials") or 5), 10),
                max_rows_per_table=max_records,
            )
            return self.aact.run(AACTAdapterRequest(search_plan=plan, options=options))
        if name == "search_civic":
            options = CIViCAdapterOptions(
                disease_name=str(args.get("disease_name") or spec.disease),
                molecular_profile_name=self._optional_text(args.get("molecular_profile_name")),
                therapy_name=self._optional_text(args.get("therapy_name")),
                max_evidence_items=min(int(args.get("max_items") or 5), 10),
                max_rows_per_table=max_records,
            )
            return self.civic.run(CIViCAdapterRequest(search_plan=plan, options=options))
        query = str(args.get("query") or f"{spec.disease} {' '.join(spec.genes + spec.drugs)}").strip()
        limit = min(int(args.get("max_records") or 20), 100)
        if name == "search_geo_catalog":
            return self.discovery.search_geo_catalog(
                task_id=spec.task_id,
                query=query or catalog_query(spec),
                max_records=limit,
                search_plan=plan,
            )
        if name == "search_biosample":
            return self.discovery.search_biosample(task_id=spec.task_id, query=query, max_records=limit, search_plan=plan)
        if name == "search_europe_pmc":
            return self.discovery.search_europe_pmc(task_id=spec.task_id, query=query, max_records=limit, search_plan=plan)
        raise ValueError(f"千问请求了未注册工具：{name}")

    @staticmethod
    def _deterministic_spec(question: str, task_id: str) -> ResearchSpec:
        upper = question.upper()
        known_genes = ["ERBB2", "PIK3CA", "TP53", "BRCA1", "BRCA2", "ESR1", "AKT1", "PTEN"]
        genes = [gene for gene in known_genes if gene in upper]
        her2_negative = ResearchAgentService._mentions_her2_negative(question)
        her2_positive = ResearchAgentService._mentions_her2_positive(question)
        drugs = []
        for alias, standard in {
            "曲妥珠单抗": "Trastuzumab",
            "HERCEPTIN": "Trastuzumab",
            "TRASTUZUMAB": "Trastuzumab",
            "帕妥珠单抗": "Pertuzumab",
            "ALPELISIB": "Alpelisib",
            "阿培利司": "Alpelisib",
            "CAPIVASERTIB": "Capivasertib",
            "卡匹伐塞替": "Capivasertib",
        }.items():
            if alias in upper or alias in question:
                drugs.append(standard)
        if "PI3K" in upper and any(term in question for term in ("抑制剂", "抑制", "inhibitor", "Inhibitor")):
            drugs.append("Alpelisib")
        if "HR+" in upper or "HR阳性" in question or "HR 阳性" in question:
            subtype = "HR-positive/HER2-negative" if her2_negative else "HR-positive"
        elif her2_negative:
            subtype = "HER2-negative"
        elif her2_positive:
            subtype = "HER2-positive"
        else:
            subtype = None
        outcomes: list[str] = []
        if any(term in upper for term in ("PCR", "RESPONSE")) or any(term in question for term in ("响应", "疗效", "缓解")):
            outcomes.append("treatment_response")
        if any(term in upper for term in ("SURVIVAL", " OS ", "DFS")) or "生存" in question:
            outcomes.append("survival")
        if not outcomes:
            outcomes.append("treatment_response")
        required = ["clinical"]
        if genes:
            required.append("mutation")
        if "表达" in question:
            required.append("expression")
        if "treatment_response" in outcomes:
            required.append("treatment_response")
        required.append("evidence")
        return ResearchSpec(
            task_id=task_id,
            research_goal=question,
            disease="Breast Cancer" if "乳腺" in question or "BREAST" in upper else "Breast Cancer",
            subtype=subtype,
            genes=genes,
            variants=[],
            drugs=list(dict.fromkeys(drugs)),
            outcomes=outcomes,
            required_data_types=list(dict.fromkeys(required)),
            target_fields=[
                "patient_id",
                "sample_id",
                "subtype",
                "stage",
                "gene",
                "mutation_status",
                "treatment",
                "response",
            ],
        )

    def _deterministic_tool_calls(
        self,
        spec: ResearchSpec,
        request: AgentTaskRequest,
    ) -> list[dict[str, Any]]:
        preferred = {value.casefold() for value in request.preferred_sources}
        candidates: list[tuple[str, dict[str, Any]]] = []
        genes = spec.genes or ["ERBB2", "PIK3CA"]
        # Several real study/accession entries can be explored in one task.
        # They remain separate provenance namespaces; dataset selection still
        # chooses one primary patient/sample cohort below.
        cbio_studies = ["brca_metabric", "brca_tcga_pan_can_atlas_2018", "brca_tcga"]
        if self._is_pi3k_inhibitor_question(spec):
            cbio_studies.insert(0, "breast_alpelisib_2020")
        candidates.append(
            (
                "search_cbioportal",
                {"study_id": cbio_studies[0], "gene_symbols": genes, "max_records": request.max_records},
            )
        )
        if self._should_search_geo(spec):
            geo_accessions = [self._default_geo_accession(spec), "GSE25066", "GSE96058"]
            candidates.append(("search_geo", {"accession": geo_accessions[0], "max_files": 5}))
        if spec.genes or "treatment_response" in spec.required_data_types:
            candidates.append(
                (
                    "search_geo_catalog",
                    {"query": catalog_query(spec), "max_records": 20},
                )
            )
        candidates.append(
            (
                "search_gdc",
                {"project_id": "TCGA-BRCA", "data_types": ["Clinical Supplement"], "max_files": 5},
            )
        )
        if spec.drugs or "evidence" in spec.required_data_types:
            candidates.append(("search_civic", {"disease_name": "Breast Cancer", "molecular_profile_name": " ".join(genes), "therapy_name": spec.drugs[0] if spec.drugs else None, "max_items": 5}))
        trial_call = ("search_trials", {"condition": "Breast Cancer", "query_terms": " ".join(spec.drugs + genes), "max_trials": 5})
        if any(term in spec.research_goal for term in ("试验", "招募", "临床研究")):
            candidates.insert(0, trial_call)
        elif spec.drugs or "treatment_response" in spec.required_data_types:
            candidates.append(trial_call)
        # Broadening entries are appended after the task-matched anchors so a
        # small budget still returns useful sources. They remain independent
        # calls and are never silently joined into the primary cohort.
        for study_id in cbio_studies[1:]:
            candidates.append(
                (
                    "search_cbioportal",
                    {"study_id": study_id, "gene_symbols": genes, "max_records": request.max_records},
                )
            )
        if self._should_search_geo(spec):
            for accession in geo_accessions[1:]:
                candidates.append(("search_geo", {"accession": accession, "max_files": 5}))
        for project_id in ("CPTAC-2", "CPTAC-3"):
            candidates.append(
                (
                    "search_gdc",
                    {"project_id": project_id, "data_types": ["Clinical Supplement"], "max_files": 5},
                )
            )
        if spec.target_fields or spec.required_data_types:
            candidates.append(
                (
                    "search_biosample",
                    {
                        "query": f"{spec.disease} {' '.join(spec.genes or [])} {' '.join(spec.drugs or [])}".strip(),
                        "max_records": 20,
                    },
                )
            )
        if spec.drugs or "evidence" in spec.required_data_types or spec.genes:
            candidates.append(
                (
                    "search_europe_pmc",
                    {
                        "query": literature_query(spec),
                        "max_records": 20,
                    },
                )
            )
        if preferred:
            candidates.sort(key=lambda item: 0 if any(token in item[0].casefold() for token in preferred) else 1)
        calls = [
            {"id": f"rule-call-{index + 1}", "name": name, "arguments": args}
            for index, (name, args) in enumerate(candidates)
        ]
        return self._limit_tool_calls(calls, request.max_sources)

    @staticmethod
    def _merge_tool_calls(
        qwen_calls: list[dict[str, Any]],
        deterministic_calls: list[dict[str, Any]],
        max_sources: int,
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for call in [*qwen_calls, *deterministic_calls]:
            name = str(call.get("name") or "")
            key = call_key(call)
            if not name or key in seen:
                continue
            seen.add(key)
            merged.append(call)
            if len(merged) >= max_sources:
                break
        return merged

    def _guard_tool_arguments(
        self,
        calls: list[dict[str, Any]],
        spec: ResearchSpec,
        request: AgentTaskRequest,
    ) -> list[dict[str, Any]]:
        guarded: list[dict[str, Any]] = []
        seen_entries: set[str] = set()
        tool_counts: dict[str, int] = {}
        for call in calls:
            normalized = {**call, "arguments": dict(call.get("arguments") or {})}
            arguments = normalized["arguments"]
            name = str(call.get("name") or "")
            if name == "search_geo":
                accession = str(
                    arguments.get("accession") or self._default_geo_accession(spec)
                ).upper()
                if not GEO_ACCESSION_PATTERN.fullmatch(accession):
                    continue
                if accession == "GSE76360" and not self._should_search_geo(spec):
                    continue
                arguments["accession"] = accession
                arguments["max_files"] = min(int(arguments.get("max_files") or 1), 5)
            elif name == "search_cbioportal":
                study_id = str(arguments.get("study_id") or "brca_metabric").strip().casefold()
                if not is_breast_cancer_study_id(study_id):
                    study_id = "brca_metabric"
                arguments["study_id"] = study_id
                arguments["gene_symbols"] = spec.genes or arguments.get("gene_symbols") or ["PIK3CA"]
                arguments["max_records"] = request.max_records
            elif name == "search_gdc":
                data_types = ["Clinical Supplement"]
                if "mutation" in spec.required_data_types:
                    data_types.append("Masked Somatic Mutation")
                if "expression" in spec.required_data_types:
                    data_types.append("Gene Expression Quantification")
                project_id = str(arguments.get("project_id") or "TCGA-BRCA").strip().upper()
                if not is_gdc_breast_project_id(project_id):
                    project_id = "TCGA-BRCA"
                arguments.update({"project_id": project_id, "data_types": data_types, "max_files": 5})
            elif name == "search_trials":
                arguments["condition"] = str(arguments.get("condition") or spec.disease)[:200]
                arguments["query_terms"] = self._optional_text(arguments.get("query_terms"))
                arguments["max_trials"] = min(int(arguments.get("max_trials") or 5), 10)
            elif name == "search_civic":
                arguments["disease_name"] = "Breast Cancer"
                arguments["molecular_profile_name"] = spec.genes[0] if spec.genes else None
                arguments["therapy_name"] = spec.drugs[0] if spec.drugs else self._optional_text(arguments.get("therapy_name"))
                arguments["max_items"] = 5
            elif name in {"search_biosample", "search_europe_pmc", "search_geo_catalog"}:
                default_query = (
                    catalog_query(spec)
                    if name == "search_geo_catalog"
                    else literature_query(spec)
                    if name == "search_europe_pmc"
                    else f"{spec.disease} {' '.join(spec.genes + spec.drugs)}"
                )
                arguments["query"] = self._optional_text(arguments.get("query")) or default_query
                arguments["max_records"] = min(int(arguments.get("max_records") or 20), 100)
            else:
                continue
            normalized["arguments"] = arguments
            key = entry_key(normalized)
            if key in seen_entries:
                continue
            if tool_counts.get(name, 0) >= MAX_ENTRIES_PER_TOOL:
                continue
            seen_entries.add(key)
            tool_counts[name] = tool_counts.get(name, 0) + 1
            guarded.append(normalized)
            if len(guarded) >= min(request.max_sources, MAX_SOURCE_ENTRIES):
                break
        if not guarded:
            genes = spec.genes or ["PIK3CA"]
            guarded.append(
                {
                    "id": "guard-fallback-cbio",
                    "name": "search_cbioportal",
                    "arguments": {
                        "study_id": "brca_metabric",
                        "gene_symbols": genes,
                        "max_records": request.max_records,
                    },
                }
            )
        return self._limit_tool_calls(guarded, min(request.max_sources, MAX_SOURCE_ENTRIES))

    @staticmethod
    def _limit_tool_calls(calls: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        tool_counts: dict[str, int] = {}
        for call in calls:
            name = str(call.get("name") or "")
            key = call_key(call)
            if not name or key in seen or tool_counts.get(name, 0) >= MAX_ENTRIES_PER_TOOL:
                continue
            seen.add(key)
            tool_counts[name] = tool_counts.get(name, 0) + 1
            result.append(call)
            if len(result) >= min(limit, MAX_SOURCE_ENTRIES):
                break
        return result

    @staticmethod
    def _synchronize_tool_message(
        tool_message: dict[str, Any],
        calls: list[dict[str, Any]],
    ) -> dict[str, Any]:
        synchronized = dict(tool_message)
        synchronized["tool_calls"] = [
            {
                "id": call["id"],
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call.get("arguments") or {}, ensure_ascii=False),
                },
            }
            for call in calls
        ]
        return synchronized

    @staticmethod
    def _dataset_selection_score(item: tuple[Any, Any], spec: ResearchSpec) -> tuple[float, float, float, int]:
        dataset, readiness = item
        coverage = readiness.requested_variable_coverage_rate
        target_score = 1.0 if readiness.target_match else 0.0
        completeness = readiness.field_completeness_rate or 0.0
        variable_score = coverage if coverage is not None else 0.0
        needs_response = "treatment_response" in spec.outcomes or "treatment_response" in spec.required_data_types
        # When the question asks for treatment response, keep trying a different
        # independent cohort that actually has the outcome. Do not keep a larger
        # molecular table that cannot support the analysis, and do not merge patients.
        if needs_response:
            return (target_score, variable_score, completeness, dataset.row_count)
        return (variable_score, target_score, completeness, dataset.row_count)

    @staticmethod
    def _default_geo_accession(spec: ResearchSpec) -> str:
        text = spec.research_goal.upper()
        subtype = (spec.subtype or "").casefold()
        if (
            ("her2-positive" in subtype or "TRASTUZUMAB" in text or "曲妥珠" in spec.research_goal)
            and "her2-negative" not in subtype
            and not ResearchAgentService._is_pi3k_inhibitor_question(spec)
        ):
            return "GSE76360"
        if "RESPONSE" in text or any(term in spec.research_goal for term in ("响应", "疗效", "新辅助")):
            return "GSE25066"
        return "GSE96058"

    @staticmethod
    def _enrich_research_spec(spec: ResearchSpec, question: str) -> ResearchSpec:
        upper = question.upper()
        genes = list(dict.fromkeys(spec.genes))
        if "PIK3CA" in upper and "PIK3CA" not in genes:
            genes.append("PIK3CA")
        if ResearchAgentService._mentions_her2_negative(question) and "ERBB2" not in upper:
            genes = [gene for gene in genes if gene != "ERBB2"]
        if "PI3K" in upper:
            genes = [gene for gene in genes if gene == "PIK3CA" or gene in upper]
        subtype = spec.subtype
        if ("HR+" in upper or "HR阳性" in question or "HR 阳性" in question) and ResearchAgentService._mentions_her2_negative(question):
            subtype = "HR-positive/HER2-negative"
        elif ResearchAgentService._mentions_her2_negative(question):
            subtype = "HER2-negative"
        elif ResearchAgentService._mentions_her2_positive(question):
            subtype = "HER2-positive"

        drugs = list(dict.fromkeys(spec.drugs))
        if "PI3K" in upper and any(term in question for term in ("抑制剂", "抑制", "inhibitor", "Inhibitor")):
            drugs.append("Alpelisib")
        if "ALPELISIB" in upper or "阿培利司" in question:
            drugs.append("Alpelisib")
        if "CAPIVASERTIB" in upper or "卡匹伐塞替" in question:
            drugs.append("Capivasertib")
        outcomes = list(dict.fromkeys(spec.outcomes or ["treatment_response"]))
        if any(term in upper for term in ("RESPONSE", "PCR")) or any(term in question for term in ("响应", "疗效", "缓解")):
            if "treatment_response" not in outcomes:
                outcomes.append("treatment_response")
        required = list(dict.fromkeys(spec.required_data_types))
        for item in ("clinical", "mutation", "evidence"):
            if item not in required:
                required.append(item)
        if "treatment_response" in outcomes and "treatment_response" not in required:
            required.append("treatment_response")
        return spec.model_copy(
            update={
                "research_goal": question,
                "subtype": subtype,
                "genes": list(dict.fromkeys(genes)),
                "drugs": list(dict.fromkeys(drugs)),
                "outcomes": outcomes,
                "required_data_types": required,
            }
        )

    @staticmethod
    def _mentions_her2_positive(question: str) -> bool:
        upper = question.upper()
        if "HER2" not in upper and "HER-2" not in upper:
            return False
        negative_patterns = ("HER2-", "HER-2-", "HER2 阴性", "HER2阴性", "HER-2 阴性", "HER-2阴性")
        if any(pattern in upper or pattern in question for pattern in negative_patterns):
            return False
        return any(term in upper or term in question for term in ("HER2+", "HER-2+", "HER2 阳性", "HER2阳性", "HER-2 阳性", "HER-2阳性"))

    @staticmethod
    def _mentions_her2_negative(question: str) -> bool:
        upper = question.upper()
        return any(
            pattern in upper or pattern in question
            for pattern in ("HER2-", "HER-2-", "HER2 阴性", "HER2阴性", "HER-2 阴性", "HER-2阴性")
        )

    @staticmethod
    def _is_pi3k_inhibitor_question(spec: ResearchSpec) -> bool:
        text = f"{spec.research_goal} {' '.join(spec.drugs)}".upper()
        return "PI3K" in text or "ALPELISIB" in text or "CAPIVASERTIB" in text or "阿培利司" in spec.research_goal

    @staticmethod
    def _should_search_geo(spec: ResearchSpec) -> bool:
        if ResearchAgentService._is_pi3k_inhibitor_question(spec):
            return False
        if "expression" in spec.required_data_types:
            return True
        if "treatment_response" not in spec.required_data_types:
            return False
        subtype = (spec.subtype or "").casefold()
        if "hr-positive" in subtype and ("her2-negative" in subtype or "her2-" in subtype):
            return False
        return True

    @staticmethod
    def _record_count(result: Any) -> int:
        if hasattr(result, "tables"):
            return sum(getattr(table, "row_count", 0) for table in result.tables)
        if hasattr(result, "files"):
            return len(result.files)
        if hasattr(result, "resources"):
            return len(result.resources)
        if hasattr(result, "trials"):
            return len(result.trials)
        if hasattr(result, "evidence_items"):
            return len(result.evidence_items)
        if hasattr(result, "records"):
            return len(result.records)
        return 0

    @staticmethod
    def _optional_count(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            count = int(value)
        except (TypeError, ValueError):
            return None
        return count if count >= 0 else None

    @staticmethod
    def _candidates(name: str, result: Any) -> list[CandidateSource]:
        if name == "search_gdc":
            return [
                CandidateSource(
                    dataset_id=result.project.project_id,
                    dataset_name="TCGA 乳腺浸润癌临床与组学队列",
                    source_database="GDC",
                    data_type="临床/组学文件目录",
                    sample_count=result.project.case_count,
                    has_treatment=False,
                    has_response=False,
                    public_access=True,
                    relevance_score=0.95,
                    url=result.project.portal_url,
                    accession=result.project.project_id,
                )
            ]
        if name == "search_geo":
            geo_names = {
                "GSE76360": "HER2 阳性乳腺癌术前曲妥珠单抗响应队列",
                "GSE25066": "乳腺癌新辅助化疗响应与生存队列",
                "GSE96058": "乳腺癌长期随访表达谱队列",
            }
            geo_counts = {"GSE76360": 100, "GSE25066": 508, "GSE96058": 3273}
            return [
                CandidateSource(
                    dataset_id=result.accession,
                    dataset_name=geo_names.get(result.accession, f"NCBI GEO 队列 {result.accession}"),
                    source_database="GEO",
                    data_type="表达谱/补充文件",
                    sample_count=geo_counts.get(result.accession),
                    has_treatment=True,
                    has_response=True,
                    public_access=True,
                    relevance_score=0.90,
                    url=result.portal_url,
                    accession=result.accession,
                )
            ]
        if name == "search_geo_catalog":
            return ResearchAgentService._discovery_candidates(name, result)
        if name == "search_cbioportal":
            metadata = result.study.raw_metadata
            return [
                CandidateSource(
                    dataset_id=result.study.study_id,
                    dataset_name=(
                        "乳腺癌 METABRIC 临床与分子队列"
                        if result.study.study_id == "brca_metabric"
                        else str(metadata.get("name") or result.study.study_id)
                    ),
                    source_database="cBioPortal",
                    data_type="患者临床/突变/拷贝数",
                    sample_count=ResearchAgentService._optional_count(metadata.get("allSampleCount")),
                    has_treatment=True,
                    has_response=any("response" in field.casefold() or "pcr" in field.casefold() for table in result.tables for field in table.raw_fields),
                    public_access=bool(metadata.get("publicStudy", True)),
                    relevance_score=0.96,
                    url=result.study.portal_url,
                    accession=result.study.study_id,
                )
            ]
        if name == "search_trials":
            return [
                CandidateSource(
                    dataset_id=trial.nct_id,
                    dataset_name=trial.brief_title,
                    source_database="ClinicalTrials.gov",
                    data_type="临床试验",
                    sample_count=trial.enrollment_count,
                    has_treatment=True,
                    has_response=trial.has_results is True,
                    public_access=True,
                    relevance_score=0.85,
                    url=trial.study_url,
                    accession=trial.nct_id,
                )
                for trial in result.trials
                if str(trial.nct_id or "").strip() and str(trial.brief_title or "").strip() and str(trial.study_url or "").strip()
            ]
        if name in {"search_biosample", "search_europe_pmc", "search_geo_catalog"}:
            return ResearchAgentService._discovery_candidates(name, result)
        if name == "search_civic":
            items = list(getattr(result, "evidence_items", None) or [])
            first = items[0] if items else None
            return [
                CandidateSource(
                    dataset_id="CIViC-BREAST-CANCER",
                    dataset_name="CIViC 乳腺癌医学证据集",
                    source_database="CIViC",
                    data_type="基因-变异-药物医学证据",
                    sample_count=None,
                    has_treatment=True,
                    has_response=True,
                    public_access=True,
                    relevance_score=0.88,
                    url=(getattr(first, "evidence_url", None) or "https://civicdb.org/"),
                    accession=getattr(first, "evidence_id", None),
                )
            ]
        return []

    @staticmethod
    def _discovery_candidates(name: str, result: Any) -> list[CandidateSource]:
        is_biosample = name == "search_biosample"
        is_geo_catalog = name == "search_geo_catalog"
        source_database = (
            "NCBI BioSample" if is_biosample else "NCBI GEO" if is_geo_catalog else "Europe PMC"
        )
        data_type = "样本元数据" if is_biosample else "GEO 目录候选" if is_geo_catalog else "文献证据"
        relevance = 0.78 if is_geo_catalog else 0.72 if is_biosample else 0.68
        candidates: list[CandidateSource] = []
        for record in getattr(result, "records", []) or []:
            dataset_id = str(
                getattr(record, "accession", None)
                or getattr(record, "pmid", None)
                or getattr(record, "record_id", None)
                or getattr(record, "uid", None)
                or ""
            ).strip()
            dataset_name = str(getattr(record, "title", None) or dataset_id).strip()
            url = str(getattr(record, "url", None) or "").strip()
            if not dataset_id or not dataset_name or not url:
                continue
            candidates.append(
                CandidateSource(
                    dataset_id=dataset_id,
                    dataset_name=dataset_name,
                    source_database=source_database,
                    data_type=data_type,
                    sample_count=None,
                    has_treatment=False,
                    has_response=False,
                    public_access=True,
                    relevance_score=relevance,
                    url=url,
                    accession=dataset_id,
                )
            )
        return candidates

    @staticmethod
    def _safe_arguments(name: str, args: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "search_gdc": {"project_id", "data_types", "max_files"},
            "search_geo": {"accession", "max_files"},
            "search_geo_catalog": {"query", "max_records"},
            "search_cbioportal": {"study_id", "gene_symbols", "max_records"},
            "search_trials": {"condition", "query_terms", "max_trials"},
            "search_civic": {"disease_name", "molecular_profile_name", "therapy_name", "max_items"},
            "search_biosample": {"query", "max_records"},
            "search_europe_pmc": {"query", "max_records"},
        }.get(name, set())
        return {key: value for key, value in args.items() if key in allowed and value is not None}

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _fallback_summary(row_count: int, warnings: list[str]) -> str:
        if not row_count:
            return "已经执行数据源规划，但尚未形成患者/样本级科研宽表。需要成功获取 cBioPortal 临床与组学表，或继续解析 GEO/GDC 下载文件。"
        warning = warnings[0] if warnings else "未发现阻断性问题。"
        return f"已生成 {row_count} 行患者/样本级科研数据。当前首要限制：{warning}"

    @staticmethod
    def _deduplicate_sources(items: list[SourceItem]) -> list[SourceItem]:
        return list({item.source_id: item for item in items}.values())

    @staticmethod
    def _deduplicate_candidates(items: list[CandidateSource]) -> list[CandidateSource]:
        return list({f"{item.source_database}:{item.dataset_id}": item for item in items}.values())
