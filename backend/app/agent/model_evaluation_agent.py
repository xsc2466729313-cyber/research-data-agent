from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from uuid import uuid4

from openpyxl import Workbook
from pydantic import Field

from backend.app.models import ApiModel
from backend.app.agent.qwen_client import QwenClient, QwenClientError


DEFAULT_MODELS = ["qwen-plus", "qwen-max", "qwen-turbo"]
DEFAULT_TARGETS = [
    ("qwen-plus", "qwen", "千问 Plus"),
    ("qwen-max", "qwen", "千问 Max"),
    ("qwen-turbo", "qwen", "千问 Turbo"),
    ("deepseek-chat", "deepseek", "DeepSeek Chat"),
    ("deepseek-reasoner", "deepseek", "DeepSeek Reasoner"),
]


class ModelTarget(ApiModel):
    target_id: str = Field(min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=40)
    model_id: str = Field(min_length=1, max_length=100)
    model_label: str = Field(min_length=1, max_length=120)


class GeneratedResearchQuestion(ApiModel):
    question_id: str
    question: str
    task_type: str
    required_domains: list[str] = Field(default_factory=list)
    source: str


class ModelEvaluationRow(ApiModel):
    question_id: str
    target_id: str
    provider: str
    model_id: str
    model_label: str
    status: str
    metrics: dict[str, float | None] = Field(default_factory=dict)
    quality_gate: str
    note: str


class ModelComparisonReport(ApiModel):
    report_id: str
    status: str
    created_at: datetime
    questions: list[GeneratedResearchQuestion] = Field(default_factory=list)
    model_rows: list[ModelEvaluationRow] = Field(default_factory=list)
    summary_zh: str
    limitations: list[str] = Field(default_factory=list)
    no_fake_scores_notice: str


class ModelEvaluationGenerateRequest(ApiModel):
    question_count: int = Field(default=3, ge=1, le=20)
    seed_question: str | None = Field(default=None, max_length=2000)
    questions: list[str] = Field(default_factory=list, max_length=20)
    models: list[str] = Field(default_factory=lambda: DEFAULT_MODELS.copy(), max_length=10)
    targets: list[ModelTarget] = Field(default_factory=list, max_length=20)
    run_mode: str = "dry_run"
    qwen_session_id: str | None = None


class ModelEvaluationRunRequest(ApiModel):
    report_id: str = Field(min_length=1, max_length=100)
    qwen_session_id: str | None = None
    session_ids: dict[str, str] = Field(default_factory=dict, max_length=20)


class ModelEvaluationService:
    """Generate auditable test plans and only score observed model outputs."""

    def __init__(self) -> None:
        self._reports: dict[str, ModelComparisonReport] = {}

    def generate(
        self,
        request: ModelEvaluationGenerateRequest,
        *,
        qwen_client: QwenClient | None = None,
    ) -> ModelComparisonReport:
        questions = self._questions(request, qwen_client)
        targets = self._targets(request)
        report_id = f"model-test-{uuid4().hex[:12]}"
        rows = [
            ModelEvaluationRow(
                question_id=item.question_id,
                target_id=target.target_id,
                provider=target.provider,
                model_id=target.model_id,
                model_label=target.model_label,
                status="待运行",
                metrics={},
                quality_gate="REVIEW",
                note="尚未调用模型；当前仅生成测试问题和评价计划。",
            )
            for item in questions
            for target in targets
        ]
        report = ModelComparisonReport(
            report_id=report_id,
            status="待运行",
            created_at=datetime.now(timezone.utc),
            questions=questions,
            model_rows=rows,
            summary_zh=f"已生成 {len(questions)} 个科研问题和 {len(targets)} 个模型目标的多模型测试计划。",
            limitations=[
                "计划模式不产生模型成绩；指标只有在真实调用并通过结构化校验后才填入。",
                "模型回答不等同 Gold Truth；医学安全规则和正式 Gold Set 评测仍需独立审核。",
            ],
            no_fake_scores_notice="未真实运行的模型保持待运行，禁止用模板或推测值填充分数。",
        )
        self._reports[report_id] = report
        return report

    def run(
        self,
        request: ModelEvaluationRunRequest,
        clients: dict[str, QwenClient] | QwenClient,
    ) -> ModelComparisonReport:
        report = self._reports.get(request.report_id)
        if report is None:
            raise ValueError("多模型测试报告不存在或服务已重启。")
        legacy_single_client = isinstance(clients, QwenClient)
        if legacy_single_client:
            single_client = clients
            clients = {
                row.target_id: single_client
                for row in report.model_rows
                if row.model_id == single_client.settings.model
            }
        question_map = {item.question_id: item.question for item in report.questions}
        grouped_rows: dict[str, list[ModelEvaluationRow]] = {}
        for row in report.model_rows:
            grouped_rows.setdefault(row.target_id, []).append(row)

        def run_target(target_id: str, rows: list[ModelEvaluationRow]) -> list[ModelEvaluationRow]:
            client = clients.get(target_id)
            if client is None:
                return [
                    row.model_copy(
                        update={
                            "status": "待实测" if legacy_single_client else "待连接",
                            "quality_gate": "REVIEW",
                            "note": (
                                f"当前临时会话模型为 {single_client.settings.model}，"
                                f"未建立 {row.model_id} 的独立会话。"
                                if legacy_single_client
                                else f"{row.provider} / {row.model_label} 尚未建立独立临时会话。"
                            ),
                        }
                    )
                    for row in rows
                ]
            updated: list[ModelEvaluationRow] = []
            for row in rows:
                try:
                    spec = client.extract_research_spec(
                        question_map[row.question_id],
                        f"eval-{target_id}-{row.question_id}",
                    )
                    metrics = self._observed_metrics(spec, question_map[row.question_id])
                    updated.append(
                        row.model_copy(
                            update={
                                "status": "已完成",
                                "metrics": metrics,
                                "quality_gate": "PASS" if metrics["综合可观察分"] >= 0.8 else "REVIEW",
                                "note": "指标来自真实模型返回的结构化内容，仅表示可观察结构化质量，不替代 Gold Truth。",
                            }
                        )
                    )
                except QwenClientError as exc:
                    updated.append(
                        row.model_copy(
                            update={
                                "status": "失败",
                                "quality_gate": "REVIEW",
                                "note": str(exc),
                            }
                        )
                    )
            return updated

        updated_by_target: dict[str, list[ModelEvaluationRow]] = {}
        with ThreadPoolExecutor(max_workers=max(1, min(len(grouped_rows), 8))) as executor:
            futures = {
                executor.submit(run_target, target_id, rows): target_id
                for target_id, rows in grouped_rows.items()
            }
            for future in as_completed(futures):
                target_id = futures[future]
                try:
                    updated_by_target[target_id] = future.result()
                except Exception as exc:
                    updated_by_target[target_id] = [
                        row.model_copy(update={"status": "失败", "quality_gate": "REVIEW", "note": f"模型任务失败：{exc}"})
                        for row in grouped_rows[target_id]
                    ]
        updated_rows = [
            row
            for target_id in grouped_rows
            for row in updated_by_target.get(target_id, grouped_rows[target_id])
        ]
        completed = sum(row.status == "已完成" for row in updated_rows)
        connected_targets = sum(target_id in clients for target_id in grouped_rows)
        total_targets = len(grouped_rows)
        completed_models = sorted({row.model_label for row in updated_rows if row.status == "已完成"})
        updated = report.model_copy(
            update={
                "status": "已完成" if completed and connected_targets == total_targets else ("部分完成" if completed else "待运行"),
                "model_rows": updated_rows,
                "summary_zh": (
                    f"已完成 {completed} 条模型测试，已连接 {connected_targets}/{total_targets} 个模型目标"
                    + (f"：{'、'.join(completed_models)}。" if completed_models else "。")
                    + (" 未连接模型暂不计分。" if connected_targets < total_targets else "")
                ),
            }
        )
        self._reports[request.report_id] = updated
        return updated

    def get(self, report_id: str) -> ModelComparisonReport | None:
        return self._reports.get(report_id)

    def export_xlsx(self, report_id: str) -> bytes:
        report = self._reports.get(report_id)
        if report is None:
            raise ValueError("多模型测试报告不存在或服务已重启。")
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "对比报告"
        sheet.append(["问题编号", "科研问题", "模型", "状态", "质量门", "指标", "说明"])
        questions = {item.question_id: item.question for item in report.questions}
        for row in report.model_rows:
            sheet.append(
                [
                    row.question_id,
                    questions.get(row.question_id, ""),
                    row.model_label,
                    row.status,
                    row.quality_gate,
                    json.dumps(row.metrics, ensure_ascii=False),
                    row.note,
                ]
            )
        plan = workbook.create_sheet("测试问题")
        plan.append(["问题编号", "科研问题", "任务类型", "所需数据域", "来源"])
        for item in report.questions:
            plan.append([item.question_id, item.question, item.task_type, "、".join(item.required_domains), item.source])
        output = BytesIO()
        workbook.save(output)
        return output.getvalue()

    def _questions(
        self,
        request: ModelEvaluationGenerateRequest,
        qwen_client: QwenClient | None,
    ) -> list[GeneratedResearchQuestion]:
        supplied = [question.strip() for question in request.questions if question.strip()]
        if supplied:
            return [self._question_item(index, question, "用户提供") for index, question in enumerate(supplied, 1)]
        if qwen_client is not None:
            try:
                generated = qwen_client.generate_research_questions(
                    request.seed_question or "乳腺癌精准治疗科研数据分析",
                    request.question_count,
                )
                return [
                    self._question_item(index, question, "千问自主生成")
                    for index, question in enumerate(generated, 1)
                ]
            except QwenClientError:
                pass
        return [
            self._question_item(index, question, "规则生成")
            for index, question in enumerate(
                self._template_questions(request.seed_question or "乳腺癌精准治疗科研数据分析")[
                    : request.question_count
                ],
                1,
            )
        ]

    @staticmethod
    def _targets(request: ModelEvaluationGenerateRequest) -> list[ModelTarget]:
        if request.targets:
            seen: set[str] = set()
            targets: list[ModelTarget] = []
            for target in request.targets:
                if target.target_id in seen:
                    continue
                seen.add(target.target_id)
                targets.append(target)
            return targets
        return [
            ModelTarget(
                target_id=f"qwen-{model}",
                provider="qwen",
                model_id=model,
                model_label=ModelEvaluationService._model_label(model),
            )
            for model in list(dict.fromkeys(request.models or DEFAULT_MODELS))
        ]

    @staticmethod
    def _question_item(index: int, question: str, source: str) -> GeneratedResearchQuestion:
        lowered = question.casefold()
        if any(term in lowered for term in ("生存", "os", "dfs")):
            task_type = "生存分析"
            domains = ["临床", "生存结局", "分子"]
        elif any(term in lowered for term in ("响应", "疗效", "pcr")):
            task_type = "治疗响应分析"
            domains = ["临床", "治疗", "响应结局", "分子"]
        else:
            task_type = "分子关联分析"
            domains = ["临床", "分子", "证据"]
        return GeneratedResearchQuestion(
            question_id=f"q-{index:02d}",
            question=question,
            task_type=task_type,
            required_domains=domains,
            source=source,
        )

    @staticmethod
    def _template_questions(seed: str) -> list[str]:
        return [
            f"{seed}：比较不同分子亚型的治疗响应差异。",
            f"{seed}：分析关键基因突变与患者生存结局的关系。",
            f"{seed}：评估治疗方案、证据等级与临床结局字段的完整性。",
            f"{seed}：检查不同数据源的患者-样本关联和来源可追溯性。",
        ]

    @staticmethod
    def _observed_metrics(spec: Any, question: str) -> dict[str, float]:
        expected = ["disease", "outcomes", "required_data_types"]
        present = sum(bool(getattr(spec, field, None)) for field in expected)
        return {
            "结构化解析通过": 1.0,
            "问题字段响应率": round(present / len(expected), 4),
            "基因字段数量": float(len(spec.genes)),
            "结局字段数量": float(len(spec.outcomes)),
            "问题长度": float(len(question)),
            "综合可观察分": round(present / len(expected), 4),
        }

    @staticmethod
    def _model_label(model: str) -> str:
        return {
            "qwen-plus": "千问 Plus",
            "qwen-max": "千问 Max",
            "qwen-turbo": "千问 Turbo",
            "deepseek-chat": "DeepSeek Chat",
            "deepseek-reasoner": "DeepSeek Reasoner",
        }.get(model, model)
