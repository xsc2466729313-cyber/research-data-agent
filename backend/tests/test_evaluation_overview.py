from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app.evaluation.overview import build_evaluation_overview, retrieval_probe_from_matches
from backend.app.main import app

ROOT = Path(__file__).resolve().parents[2]


client = TestClient(app)


def test_overview_endpoint_keeps_official_metrics_unevaluated() -> None:
    response = client.get("/api/evaluation/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["goldset_row_counts"]["retrieval_gold.csv"] == 50
    assert payload["goldset_row_counts"]["field_gold.csv"] == 26
    assert payload["goldset_row_counts"]["error_gold.csv"] == 18
    assert len(payload["protocol"]) == 5
    development = payload["development_split"]
    assert development["unofficial"] is True
    assert development["available"] is True
    assert development["evaluation_id"] == "development-xsc-qwen-live-20260829"
    assert development["sdti"] is not None
    assert 60 < float(development["sdti"]) < 80
    assert "不得" in development["notice"] or "禁止" in development["notice"]
    official = next(item for item in payload["official_metrics"] if item["key"] == "sdti")
    if official["value"] is None:
        assert payload["evaluation_status"] == "NOT_EVALUATED"
        assert payload["official_metrics_allowed"] is False
        assert official["status"] == "NOT_EVALUATED"
        assert payload["official_run"]["can_run"] is True
    else:
        assert payload["official_run"]["has_score"] is True
        assert "official-candidate" in str(payload["official_run"]["evaluation_id"] or "")
        assert payload["official_run"]["evaluation_id"] != development["evaluation_id"]
    assert all(item["status"] != "TEAM_REFERENCE" for item in payload["official_metrics"])
    assert "66.94" not in str(payload["official_metrics"])
    assert float(development["sdti"]) != (official["value"] or 0) or official["value"] is None


def test_retrieval_probe_uses_selected_candidates_as_relevance() -> None:
    matches = [
        SimpleNamespace(match_score=0.9, selected=True),
        SimpleNamespace(match_score=0.8, selected=False),
        SimpleNamespace(match_score=0.4, selected=True),
        SimpleNamespace(match_score=0.2, selected=False),
    ]

    probe = retrieval_probe_from_matches(matches)

    by_key = {item.key: item.value for item in probe.metrics}
    assert probe.cases == 4
    assert probe.status == "已计算"
    assert by_key["recall@1"] == 0.5
    assert by_key["recall@3"] == 1.0
    assert by_key["ndcg@3"] is not None
    assert 0.0 < by_key["ndcg@3"] <= 1.0


def test_overview_builder_does_not_copy_external_proxy_scores() -> None:
    overview = build_evaluation_overview(goldset_row_counts={"retrieval_gold.csv": 0, "field_gold.csv": 0, "error_gold.csv": 0})

    assert overview.retrieval_probe.status == "待运行"
    assert overview.notice.startswith("评测方法对齐统一评测方案工具包")
    assert "模板为空" in overview.notice
    assert all(item.status == "NOT_EVALUATED" for item in overview.official_metrics)
    assert overview.team_reference.available is False
    assert overview.toolkit_run.status == "待运行"
    assert overview.evaluation_status == "NOT_EVALUATED"
    assert overview.development_split.unofficial is True
    assert overview.official_metrics[-1].value is None
    layer = overview.retrieval_layer
    assert layer.available is True
    assert layer.query_count == 3677
    assert len(layer.rows) == 5
    dumped = layer.model_dump_json()
    assert "evaluation/" not in dumped
    assert ".json" not in dumped
    assert "vnext_retrieval" not in dumped
    cleaning = next(item for item in overview.toolkit_run.metrics if item.key == "cleaning_retention")
    assert cleaning.label == "清洗残留清除率"
    assert cleaning.value is None


def test_overview_builder_keeps_official_sdti_unevaluated_when_templates_filled(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.evaluation.official_run.latest_official_metrics", lambda: None)
    overview = build_evaluation_overview(
        goldset_row_counts={
            "retrieval_gold.csv": 50,
            "field_gold.csv": 26,
            "error_gold.csv": 18,
        }
    )

    assert overview.evaluation_status == "NOT_EVALUATED"
    assert overview.official_metrics_allowed is False
    assert overview.protocol[4].status == "可提交正式评测"
    assert all(item.status == "NOT_EVALUATED" and item.value is None for item in overview.official_metrics)
    assert overview.official_metrics[-1].key == "sdti"
    assert "开始正式评测" in overview.notice or "采集观察" in overview.notice
    assert "66.94" not in overview.notice
    assert overview.development_split.unofficial is True
    assert overview.official_run.can_run is True


def test_overview_endpoint_keeps_official_sdti_unevaluated_when_development_exists() -> None:
    response = client.get("/api/evaluation/overview")

    payload = response.json()
    official = next(item for item in payload["official_metrics"] if item["key"] == "sdti")
    development = payload["development_split"]
    assert development["available"] is True
    assert 60 < float(development["sdti"]) < 80
    if official["value"] is None:
        assert official["status"] == "NOT_EVALUATED"
    else:
        assert "official-candidate" in str(payload["official_run"]["evaluation_id"] or "")
        assert payload["official_run"]["evaluation_id"] != development["evaluation_id"]
    assert "66.94" not in str(payload["official_metrics"])
    layer = payload["retrieval_layer"]
    assert layer["available"] is True
    assert "evaluation/" not in str(layer)
    assert all("json" not in row["dataset"].lower() for row in layer["rows"])
    assert layer["rows"][0]["dataset"] == "SciFact"
    assert layer["rows"][0]["dataset_zh"] == "科学事实"


def test_internal_evaluation_is_removed_from_product_frontend() -> None:
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert 'id="system-evaluation"' not in html
    assert 'href="#system-evaluation"' not in html
    assert 'id="official-eval-run"' not in html
    assert "模型评测报告集合" not in html
    assert "运行候选卷验证" not in html
    assert "闭环修正结果" in html
    assert "Closed-Loop Iteration" not in html
    render_fn = script.split("function renderResult(result)", 1)[1].split("function renderClosedLoop", 1)[0]
    closed_loop_fn = script.split("function renderClosedLoop(loop)", 1)[1].split("function renderResearchBrief", 1)[0]
    readiness_fn = script.split("function renderReadiness(", 1)[1].split("function renderUnifiedEvaluation", 1)[0]
    quality_fn = script.split("function renderQualityGates(", 1)[1].split("function renderSpec(", 1)[0]
    assert "persistAndRenderSystemEvaluation(result)" not in render_fn
    assert "if (!loop?.improved)" in closed_loop_fn
    assert "panel.hidden = true" in closed_loop_fn
    assert "66.94" not in script
    assert "slice(0, 2)" in closed_loop_fn
    assert "第 1 轮 · 基线" in closed_loop_fn
    assert "第 2 轮 · 修正后" in closed_loop_fn
    assert "主要必需字段覆盖" in closed_loop_fn
    assert "无变化" in closed_loop_fn
    assert "必要字段覆盖 ${(Number(metrics.required_field_coverage || 0) * 100).toFixed(1)}%" not in closed_loop_fn
    assert "research-metric-note" in readiness_fn
    assert 'label: "清洗与隔离"' not in readiness_fn
    assert "未识别到可统计的研究结局字段" not in readiness_fn
    assert '"未点名"' not in readiness_fn
    assert "本题还没有可对照的队列匹配表" not in quality_fn
    assert "入口命中 F1" not in quality_fn
    assert "非正式 SDTI" not in script
    assert "读法：" not in script
    assert "v=20260830-research-workbench-5" in html
    report = ROOT / "evaluation" / "agent_stratified_ablation_20260829" / "report.md"
    assert report.is_file()


def test_result_presentation_does_not_posterize_empty_or_pending_states() -> None:
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")
    assert 'id="official-eval-run"' not in html
    assert '<details id="review-queue-panel"' in html
    assert 'class="report-drawer compact-report-drawer readiness-audit"' in html
    assert 'id="scientific-usability" class="scientific-usability" hidden' in html
    assert 'id="outcome-visual" class="outcome-visual" hidden' in html
    assert "panel.hidden = !hasFindings" in script
    assert "outcomeVisual.hidden = !distribution.length" in script
    assert "percent <= 0" in script
    assert ".eval-pending-note" in styles
    assert ".research-metric-note" in styles
    assert ".review-queue-summary" in styles
    assert "quality-gate-layers article[data-decision=\"REVIEW\"]" in styles
