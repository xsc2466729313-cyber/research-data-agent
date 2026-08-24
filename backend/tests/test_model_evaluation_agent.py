from __future__ import annotations

import json

import httpx

from backend.app.agent import (
    ModelEvaluationGenerateRequest,
    ModelEvaluationRunRequest,
    ModelEvaluationService,
    QwenClient,
    QwenSettings,
)
from backend.app.agent.model_evaluation_agent import ModelTarget


def qwen_spec_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "research_goal": "测试乳腺癌治疗响应",
                                "disease": "Breast Cancer",
                                "subtype": "HER2-positive",
                                "genes": ["PIK3CA"],
                                "variants": [],
                                "drugs": [],
                                "outcomes": ["treatment_response"],
                                "required_data_types": ["clinical", "mutation"],
                                "target_fields": ["patient_id", "response"],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        },
        request=request,
    )


def test_dry_run_generates_questions_without_scores() -> None:
    report = ModelEvaluationService().generate(
        ModelEvaluationGenerateRequest(
            question_count=2,
            seed_question="乳腺癌治疗响应",
            models=["qwen-plus", "qwen-max"],
        )
    )

    assert len(report.questions) == 2
    assert report.status == "待运行"
    assert all(not row.metrics for row in report.model_rows)
    assert "禁止" in report.no_fake_scores_notice


def test_live_run_only_fills_the_model_backed_by_current_session() -> None:
    service = ModelEvaluationService()
    report = service.generate(
        ModelEvaluationGenerateRequest(
            question_count=1,
            questions=["研究 HER2 阳性乳腺癌治疗响应"],
            models=["qwen-plus", "qwen-max"],
        )
    )
    client = QwenClient(
        settings=QwenSettings(
            api_key="rotated-test-key",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="qwen-plus",
            workspace_id=None,
        ),
        client=httpx.Client(transport=httpx.MockTransport(qwen_spec_handler)),
    )

    updated = service.run(
        ModelEvaluationRunRequest(report_id=report.report_id),
        client,
    )

    plus = next(row for row in updated.model_rows if row.model_id == "qwen-plus")
    max_row = next(row for row in updated.model_rows if row.model_id == "qwen-max")
    assert plus.status == "已完成"
    assert plus.metrics["结构化解析通过"] == 1
    assert max_row.status == "待实测"
    assert not max_row.metrics
    assert "独立会话" in max_row.note


def test_multi_provider_run_fills_each_connected_target() -> None:
    service = ModelEvaluationService()
    report = service.generate(
        ModelEvaluationGenerateRequest(
            question_count=2,
            questions=["比较乳腺癌分子标志物与治疗响应"],
            targets=[
                ModelTarget(
                    target_id="qwen-plus-target",
                    provider="qwen",
                    model_id="qwen-plus",
                    model_label="千问 Plus",
                ),
                ModelTarget(
                    target_id="deepseek-chat-target",
                    provider="deepseek",
                    model_id="deepseek-chat",
                    model_label="DeepSeek Chat",
                ),
            ],
        )
    )

    def build_client(provider: str, model: str) -> QwenClient:
        return QwenClient(
            settings=QwenSettings(
                api_key=f"{provider}-test-key",
                base_url=(
                    "https://dashscope.aliyuncs.com/compatible-mode/v1"
                    if provider == "qwen"
                    else "https://api.deepseek.com"
                ),
                model=model,
                workspace_id=None,
                provider=provider,
            ),
            client=httpx.Client(transport=httpx.MockTransport(qwen_spec_handler)),
        )

    updated = service.run(
        ModelEvaluationRunRequest(
            report_id=report.report_id,
            session_ids={
                "qwen-plus-target": "session-qwen",
                "deepseek-chat-target": "session-deepseek",
            },
        ),
        {
            "qwen-plus-target": build_client("qwen", "qwen-plus"),
            "deepseek-chat-target": build_client("deepseek", "deepseek-chat"),
        },
    )

    assert {row.provider for row in updated.model_rows} == {"qwen", "deepseek"}
    assert all(row.status == "已完成" for row in updated.model_rows)
    assert all("综合可观察分" in row.metrics for row in updated.model_rows)
    assert "已连接 2/2" in updated.summary_zh
