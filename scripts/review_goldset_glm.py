"""Independent GLM review of a DeepSeek Gold Set draft.

The API key is read only from GLM_API_KEY and is never written to artifacts.
The output remains a review report, not an approved or frozen Gold Set.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INPUT = ROOT / "evaluation" / "goldset_deepseek_draft.json"
OUTPUT = ROOT / "evaluation" / "goldset_glm_review.json"


def parse_json(content: str) -> dict[str, Any]:
    match = re.search(r"```(?:json)?\s*(.*?)```", content, re.I | re.S)
    payload = json.loads(match.group(1).strip() if match else content.strip())
    if not isinstance(payload, dict):
        raise ValueError("GLM response must be a JSON object")
    label = str(payload.get("label", "")).strip().casefold()
    if label not in {"relevant", "not_relevant"}:
        raise ValueError("GLM label must be relevant or not_relevant")
    confidence = float(payload.get("confidence", 0))
    if not 0 <= confidence <= 1:
        raise ValueError("GLM confidence must be between 0 and 1")
    return {
        "label": label,
        "confidence": confidence,
        "rationale": str(payload.get("rationale", ""))[:4000],
        "evidence_needed": [str(x)[:500] for x in (payload.get("evidence_needed") or [])][:10],
    }


def review(client: httpx.Client, *, key: str, base_url: str, model: str, item: dict[str, Any]) -> dict[str, Any]:
    system = (
        "你是独立的乳腺癌科研数据 Gold Set 复核员。请独立判断问题与官方数据源是否相关，"
        "不要盲从 DeepSeek 初标，也不要补充无法从输入确认的事实。只输出 JSON："
        "label(relevant/not_relevant)、confidence(0到1)、rationale、evidence_needed(数组)。"
    )
    user = {
        "research_question": item["research_question"],
        "source": item["source"],
        "deepseek_initial_label": item.get("deepseek", {}).get("label"),
        "deepseek_initial_rationale": item.get("deepseek", {}).get("rationale"),
        "task": "独立复核，不要把任一模型输出直接视作 Ground Truth。",
    }
    response = client.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
        },
    )
    response.raise_for_status()
    return parse_json(response.json()["choices"][0]["message"]["content"])


def main() -> int:
    key = os.getenv("GLM_API_KEY", "").strip()
    if not key:
        raise SystemExit("GLM_API_KEY is not configured")
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    model = os.getenv("GLM_MODEL", "glm-5.2")
    base_url = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    output: dict[str, Any] = {
        "status": "independent_review_pending_human_adjudication",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reviewer_model_id": model,
        "primary_model_id": payload.get("primary_model_id", "deepseek-chat"),
        "source_draft": str(INPUT),
        "reviews": [],
        "errors": [],
    }
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for item in payload.get("retrieval", []):
            try:
                glm = review(client, key=key, base_url=base_url, model=model, item=item)
                deepseek_label = item.get("deepseek", {}).get("label")
                output["reviews"].append({
                    "question_id": item["question_id"],
                    "dataset_id": item["source"]["accession"],
                    "source": item["source"],
                    "deepseek": item.get("deepseek"),
                    "glm": glm,
                    "agreement": deepseek_label == glm["label"],
                    "review_status": "pending_human_adjudication",
                })
            except Exception as exc:
                output["errors"].append({
                    "question_id": item.get("question_id"),
                    "dataset_id": item.get("source", {}).get("accession"),
                    "error": f"{type(exc).__name__}: {exc}",
                })
    output["summary"] = {
        "reviewed": len(output["reviews"]),
        "agreements": sum(item["agreement"] for item in output["reviews"]),
        "disagreements": sum(not item["agreement"] for item in output["reviews"]),
        "errors": len(output["errors"]),
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "summary": output["summary"], "status": output["status"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
