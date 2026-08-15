from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.app.agent.dataset_builder import ResearchDatasetBuilder
from backend.app.agent.models import (
    AgentConfigurationStatus,
    AgentDataMode,
    AgentPlanStep,
    AgentTaskRequest,
    AgentTaskResult,
    AgentToolCall,
)
from backend.app.agent.qwen_client import QwenClient, QwenClientError
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


TOOL_LABELS = {
    "search_gdc": "检索 GDC / TCGA",
    "search_geo": "检索 NCBI GEO",
    "search_cbioportal": "检索 cBioPortal 患者队列",
    "search_trials": "检索 ClinicalTrials.gov",
    "search_civic": "检索 CIViC 医学证据",
}


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
        dataset_builder: ResearchDatasetBuilder | None = None,
    ) -> None:
        self.qwen = qwen_client or QwenClient()
        self.gdc = gdc_adapter or GDCAdapter()
        self.geo = geo_adapter or GEOAdapter()
        self.cbioportal = cbioportal_adapter or CBioPortalAdapter()
        self.aact = aact_adapter or AACTClinicalTrialsAdapter()
        self.civic = civic_adapter or CIViCAdapter()
        self.dataset_builder = dataset_builder or ResearchDatasetBuilder()
        self._results: dict[str, AgentTaskResult] = {}
        self._lock = threading.Lock()

    def configuration(self) -> AgentConfigurationStatus:
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

    def run(
        self,
        request: AgentTaskRequest,
        *,
        qwen_client: QwenClient | None = None,
    ) -> AgentTaskResult:
        active_qwen = qwen_client or self.qwen
        task_id = f"agent-{uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc)
        plan_steps = [
            AgentPlanStep(step_id="理解问题", label="千问解析科研问题", status="进行中", detail="提取疾病、基因、治疗和研究结局。"),
            AgentPlanStep(step_id="选择工具", label="选择真实数据工具", status="等待", detail="由千问函数调用或确定性规划器选择。"),
            AgentPlanStep(step_id="获取数据", label="调用公开数据库", status="等待", detail="执行受控、可审计的数据库工具。"),
            AgentPlanStep(step_id="构建数据集", label="生成科研数据宽表", status="等待", detail="按患者/样本汇总研究变量并识别研究结局。"),
            AgentPlanStep(step_id="检查可用性", label="检查可科研性", status="等待", detail="检查记录规模、结局完整性、重复患者、上游截断和来源可追溯性。"),
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
        plan_steps[0].status = "完成"
        plan_steps[0].detail = f"识别疾病 {spec.disease}；基因 {', '.join(spec.genes) or '未指定'}；结局 {', '.join(spec.outcomes) or '未指定'}。"

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
        plan_steps[1].detail = "已选择：" + "、".join(
            TOOL_LABELS.get(call["name"], call["name"]) for call in calls
        )

        executed: list[AgentToolCall] = []
        raw_results: list[tuple[str, Any]] = []
        candidates: list[CandidateSource] = []
        source_items: list[SourceItem] = []
        if request.data_mode == AgentDataMode.LIVE:
            for call in calls:
                log, result = self._execute_tool(call, spec, request.max_records)
                executed.append(log)
                if result is not None:
                    raw_results.append((call["name"], result))
                    candidates.extend(self._candidates(call["name"], result))
                    source_items.extend(getattr(result, "source_items", []))
            success_count = sum(item.status == "完成" for item in executed)
            plan_steps[2].status = "完成" if success_count else "失败"
            plan_steps[2].detail = f"{success_count}/{len(executed)} 个工具成功；登记 {len(source_items)} 个真实来源。"
        else:
            plan_steps[2].status = "跳过"
            plan_steps[2].detail = "当前为仅规划模式，未访问外部数据库。"

        built_datasets: list[tuple[Any, Any]] = []
        for name, raw_result in raw_results:
            if name == "search_cbioportal" and isinstance(raw_result, CBioPortalAdapterResult):
                built_datasets.append(self.dataset_builder.build_from_cbioportal(raw_result, spec))
            elif name == "search_geo" and isinstance(raw_result, GEOAdapterResult):
                geo_dataset = self.dataset_builder.build_from_geo(raw_result, spec)
                if geo_dataset is not None:
                    built_datasets.append(geo_dataset)
        if built_datasets:
            dataset, readiness = max(built_datasets, key=self._dataset_selection_score)
        else:
            dataset, readiness = self.dataset_builder.empty()
            if raw_results:
                readiness.warnings.insert(
                    0,
                    "已检索到来源或关系表，但当前结果不包含可直接解析的患者/样本级数据文件。",
                )
        plan_steps[3].status = "完成" if dataset.row_count else "数据不足"
        plan_steps[3].detail = f"生成 {dataset.row_count} 行、{len(dataset.columns)} 列科研数据；分析单位：{dataset.unit_of_analysis}。"
        plan_steps[4].status = "完成"
        plan_steps[4].detail = f"结论：{readiness.status}；目标字段：{readiness.target_column or '未识别'}。"

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
            plan=plan_steps,
            tool_calls=executed,
            candidate_sources=self._deduplicate_candidates(candidates),
            source_items=self._deduplicate_sources(source_items),
            modeling_dataset=dataset,
            readiness=readiness,
            summary_zh=summary,
            created_at=created_at,
        )
        with self._lock:
            self._results[task_id] = result
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
            "search_cbioportal": "cBioPortal",
            "search_trials": "AACT",
            "search_civic": "CIViC",
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
            parse_patient_metadata = accession.upper() == "GSE76360"
            options = GEOAdapterOptions(
                accession=accession,
                max_files_per_type=min(int(args.get("max_files") or 5), 20),
                resource_types=(
                    [GEOResourceType.SERIES_MATRIX]
                    if parse_patient_metadata
                    else list(GEOResourceType)
                ),
                download=parse_patient_metadata,
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
        options = CIViCAdapterOptions(
            disease_name=str(args.get("disease_name") or spec.disease),
            molecular_profile_name=self._optional_text(args.get("molecular_profile_name")),
            therapy_name=self._optional_text(args.get("therapy_name")),
            max_evidence_items=min(int(args.get("max_items") or 5), 10),
            max_rows_per_table=max_records,
        )
        return self.civic.run(CIViCAdapterRequest(search_plan=plan, options=options))

    @staticmethod
    def _deterministic_spec(question: str, task_id: str) -> ResearchSpec:
        upper = question.upper()
        known_genes = ["ERBB2", "PIK3CA", "TP53", "BRCA1", "BRCA2", "ESR1", "AKT1", "PTEN"]
        genes = [gene for gene in known_genes if gene in upper]
        if "HER2" in upper and "ERBB2" not in genes:
            genes.insert(0, "ERBB2")
        drugs = []
        for alias, standard in {
            "曲妥珠单抗": "Trastuzumab",
            "HERCEPTIN": "Trastuzumab",
            "TRASTUZUMAB": "Trastuzumab",
            "帕妥珠单抗": "Pertuzumab",
        }.items():
            if alias in upper or alias in question:
                drugs.append(standard)
        subtype = "HER2-positive" if "HER2" in upper and any(term in question for term in ("阳性", "+")) else None
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
        candidates.append(("search_cbioportal", {"study_id": "brca_metabric", "gene_symbols": genes, "max_records": request.max_records}))
        if "expression" in spec.required_data_types or "treatment_response" in spec.required_data_types:
            candidates.append(("search_geo", {"accession": self._default_geo_accession(spec), "max_files": 5}))
        candidates.append(("search_gdc", {"project_id": "TCGA-BRCA", "data_types": ["Clinical Supplement"], "max_files": 5}))
        if spec.drugs or "evidence" in spec.required_data_types:
            candidates.append(("search_civic", {"disease_name": "Breast Cancer", "molecular_profile_name": " ".join(genes), "therapy_name": spec.drugs[0] if spec.drugs else None, "max_items": 5}))
        trial_call = ("search_trials", {"condition": "Breast Cancer", "query_terms": " ".join(spec.drugs + genes), "max_trials": 5})
        if any(term in spec.research_goal for term in ("试验", "招募", "临床研究")):
            candidates.insert(0, trial_call)
        elif spec.drugs or "treatment_response" in spec.required_data_types:
            candidates.append(trial_call)
        if preferred:
            candidates.sort(key=lambda item: 0 if any(token in item[0].casefold() for token in preferred) else 1)
        return [
            {"id": f"rule-call-{index + 1}", "name": name, "arguments": args}
            for index, (name, args) in enumerate(candidates[: request.max_sources])
        ]

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
            if not name or name in seen:
                continue
            seen.add(name)
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
        for call in calls:
            normalized = {**call, "arguments": dict(call.get("arguments") or {})}
            arguments = normalized["arguments"]
            if call.get("name") == "search_geo":
                # The curated accession resolver prevents a generic expression
                # cohort from replacing an outcome-matched HER2 response cohort.
                arguments["accession"] = self._default_geo_accession(spec)
                arguments["max_files"] = 1
            elif call.get("name") == "search_cbioportal":
                arguments["max_records"] = request.max_records
            elif call.get("name") == "search_gdc":
                data_types = ["Clinical Supplement"]
                if "mutation" in spec.required_data_types:
                    data_types.append("Masked Somatic Mutation")
                if "expression" in spec.required_data_types:
                    data_types.append("Gene Expression Quantification")
                arguments.update({"project_id": "TCGA-BRCA", "data_types": data_types, "max_files": 5})
            elif call.get("name") == "search_civic":
                arguments["disease_name"] = "Breast Cancer"
                arguments["molecular_profile_name"] = spec.genes[0] if spec.genes else None
                arguments["therapy_name"] = None
                arguments["max_items"] = 5
            guarded.append(normalized)
        return guarded

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
    def _dataset_selection_score(item: tuple[Any, Any]) -> tuple[float, float, float, int]:
        dataset, readiness = item
        target_score = 1.0 if readiness.target_match else 0.0
        coverage = readiness.requested_variable_coverage_rate
        completeness = readiness.field_completeness_rate or 0.0
        return (target_score, coverage if coverage is not None else 1.0, completeness, dataset.row_count)

    @staticmethod
    def _default_geo_accession(spec: ResearchSpec) -> str:
        text = spec.research_goal.upper()
        if "HER2" in text or "TRASTUZUMAB" in text or "曲妥珠" in spec.research_goal:
            return "GSE76360"
        if "RESPONSE" in text or any(term in spec.research_goal for term in ("响应", "疗效", "新辅助")):
            return "GSE25066"
        return "GSE96058"

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
        return 0

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
                    sample_count=metadata.get("allSampleCount"),
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
            ]
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
                url=(result.evidence_items[0].evidence_url if result.evidence_items else "https://civicdb.org/"),
                accession=(result.evidence_items[0].evidence_id if result.evidence_items else None),
            )
        ]

    @staticmethod
    def _safe_arguments(name: str, args: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "search_gdc": {"project_id", "data_types", "max_files"},
            "search_geo": {"accession", "max_files"},
            "search_cbioportal": {"study_id", "gene_symbols", "max_records"},
            "search_trials": {"condition", "query_terms", "max_trials"},
            "search_civic": {"disease_name", "molecular_profile_name", "therapy_name", "max_items"},
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
