from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from backend.app.evaluation.errors import EvaluationError, EvaluationErrorCode
from backend.app.evaluation.models import ArtifactReference, EvaluationResult


class EvaluationArtifactWriter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def write(self, result: EvaluationResult) -> list[ArtifactReference]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        final_dir = self.output_dir / result.evaluation_id
        if final_dir.exists():
            raise EvaluationError(
                EvaluationErrorCode.DUPLICATE_EVALUATION,
                "Evaluation artifacts already exist for this evaluation_id.",
                details={"evaluation_id": result.evaluation_id},
            )
        temporary_dir = Path(
            tempfile.mkdtemp(prefix=f".{result.evaluation_id}.", dir=self.output_dir)
        )
        try:
            metrics_path = temporary_dir / "metrics.json"
            report_path = temporary_dir / "report.md"
            payload = result.model_dump(mode="json", exclude={"artifacts"})
            metrics_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            report_path.write_text(self._render_report(result), encoding="utf-8")
            temporary_dir.rename(final_dir)
        except EvaluationError:
            raise
        except OSError as exc:
            raise EvaluationError(
                EvaluationErrorCode.ARTIFACT_WRITE_FAILED,
                "Failed to write evaluation artifacts.",
                details={"evaluation_id": result.evaluation_id, "error": str(exc)},
            ) from exc
        finally:
            if temporary_dir.exists():
                shutil.rmtree(temporary_dir)

        return [
            self._reference(final_dir / "metrics.json", "application/json"),
            self._reference(final_dir / "report.md", "text/markdown"),
        ]

    @staticmethod
    def _reference(path: Path, media_type: str) -> ArtifactReference:
        content = path.read_bytes()
        return ArtifactReference(
            name=path.name,
            path=str(path.resolve()),
            url=f"/api/evaluation/artifacts/{path.parent.name}/{path.name}",
            media_type=media_type,
            sha256=hashlib.sha256(content).hexdigest(),
        )

    @staticmethod
    def _render_report(result: EvaluationResult) -> str:
        gold = (
            f"{result.gold_set.gold_set_id} / {result.gold_set.version}"
            if result.gold_set
            else "未提供真实 Gold Set"
        )
        lines = [
            "# 评测与 SDTI 报告",
            "",
            f"- 评测 ID：`{result.evaluation_id}`",
            f"- 评测状态：`{result.evaluation_status.value}`",
            f"- Gold Set：{gold}",
            f"- 安全门：`{result.safety.gate.value}`",
            f"- 允许自动发布：`{str(result.safety.publish_allowed).lower()}`",
            "",
            "## 核心指标",
            "",
            "| 指标 | 值 | 状态 | 分子 / 分母 | 目标 |",
            "|---|---:|---|---:|---:|",
        ]
        for name, metric in result.metrics:
            value = "未评测" if metric.value is None else f"{metric.value:.6f}"
            ratio = (
                "—"
                if metric.numerator is None or metric.denominator is None
                else f"{metric.numerator:g} / {metric.denominator:g}"
            )
            target = "—" if metric.target is None else f"{metric.target:g}"
            lines.append(
                f"| `{name}` | {value} | `{metric.status.value}` | {ratio} | {target} |"
            )
        lines.extend(["", "## 公式", ""])
        for name, metric in result.metrics:
            lines.append(f"- `{name}`: `{metric.formula}`")
        lines.extend(["", "## 安全门与发布阻断", ""])
        if result.safety.redlines:
            lines.extend(f"- 红线：{item}" for item in result.safety.redlines)
        if result.safety.publication_blockers:
            lines.extend(
                f"- 发布阻断：{item}" for item in result.safety.publication_blockers
            )
        if not result.safety.redlines and not result.safety.publication_blockers:
            lines.append("- 未触发安全红线或发布阻断。")
        if result.counts is not None:
            lines.extend(
                [
                    "",
                    "## 原始计数",
                    "",
                    "```json",
                    json.dumps(
                        result.counts.model_dump(mode="json"),
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    ),
                    "```",
                ]
            )
        lines.extend(
            [
                "",
                "## 声明",
                "",
                result.notice,
                "",
            ]
        )
        return "\n".join(lines)
