"""Build an auditable DeepSeek-assisted Gold Set draft.

This command intentionally produces a draft only. DeepSeek is an annotator,
not the ground-truth authority; official-source verification and independent
human review are still required before rows can be frozen.
"""

from __future__ import annotations

import csv
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

from backend.app.goldset.models import SourceDatabase, SourceReference
from backend.app.goldset.source_verifier import OfficialSourceVerifier


ENV_PATH = ROOT / "evaluation" / "deepseek.local.env"
TEMPLATE = ROOT / "evaluation" / "retrieval_gold.template.jsonl"
OUTPUT = ROOT / "evaluation" / "goldset_deepseek_draft.json"

SOURCE_MAP: dict[str, SourceReference] = {
    "brca_metabric": SourceReference(
        source_id="cbioportal:brca_metabric",
        source_database=SourceDatabase.CBIOPORTAL,
        accession="brca_metabric",
        url="https://www.cbioportal.org/study/summary?id=brca_metabric",
    ),
    "GSE76360": SourceReference(
        source_id="geo:GSE76360",
        source_database=SourceDatabase.GEO,
        accession="GSE76360",
        url="https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE76360",
    ),
    "TCGA-BRCA": SourceReference(
        source_id="cbioportal:brca_tcga",
        source_database=SourceDatabase.CBIOPORTAL,
        accession="brca_tcga",
        url="https://www.cbioportal.org/study/summary?id=brca_tcga",
    ),
}


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_PATH.is_file():
        for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    for key in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"):
        if os.getenv(key):
            values[key] = os.environ[key]
    return values


def load_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for raw in TEMPLATE.read_text(encoding="utf-8-sig").splitlines():
        if raw.strip() and not raw.lstrip().startswith("#"):
            cases.append(json.loads(raw))
    return cases


def parse_json(content: str) -> dict[str, Any]:
    match = re.search(r"```(?:json)?\s*(.*?)```", content, re.I | re.S)
    text = match.group(1).strip() if match else content.strip()
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("DeepSeek response must be a JSON object")
    label = str(payload.get("label", "")).strip().casefold()
    if label not in {"relevant", "not_relevant"}:
        raise ValueError("DeepSeek label must be relevant or not_relevant")
    confidence = float(payload.get("confidence", 0))
    if not 0 <= confidence <= 1:
        raise ValueError("DeepSeek confidence must be between 0 and 1")
    return {
        "label": label,
        "confidence": confidence,
        "rationale": str(payload.get("rationale", ""))[:4000],
        "evidence_needed": [str(item)[:500] for item in (payload.get("evidence_needed") or [])][:10],
    }


def ask_deepseek(client: httpx.Client, *, api_key: str, base_url: str, model: str, question: str, source: SourceReference) -> dict[str, Any]:
    system = (
        "你是乳腺癌科研数据 Gold Set 的初标员。你只能根据给定问题和官方数据源元数据判断相关性，"
        "不能补充网页外事实，不能把自己的判断当作最终真值。只输出 JSON："
        "label(relevant/not_relevant)、confidence(0到1)、rationale、evidence_needed(数组)。"
    )
    user = {
        "research_question": question,
        "source": source.model_dump(mode="json"),
        "task": "判断该官方数据源是否应作为此科研问题的相关检索结果。",
    }
    response = client.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
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
    content = response.json()["choices"][0]["message"]["content"]
    return parse_json(content)


def main() -> int:
    config = load_env()
    api_key = config.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY is not configured")
    base_url = config.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    model = config.get("DEEPSEEK_MODEL", "deepseek-chat")
    cases = load_cases()
    verifier = OfficialSourceVerifier()
    draft: dict[str, Any] = {
        "status": "draft_pending_independent_review",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "primary_model_id": model,
        "source_template": str(TEMPLATE),
        "notice": "DeepSeek 初标草案，不是冻结 Gold Set；需独立复核、人工裁决、规则验证和 manifest checksum。",
        "retrieval": [],
        "unresolved_sources": [],
    }
    try:
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            for case in cases:
                for dataset_id in case.get("expected_sources", []):
                    source = SOURCE_MAP.get(dataset_id)
                    if source is None:
                        draft["unresolved_sources"].append({
                            "question_id": case["case_id"],
                            "dataset_id": dataset_id,
                            "reason": "No verified source mapping was configured; human mapping required.",
                        })
                        continue
                    verification = verifier.verify(source)
                    item: dict[str, Any] = {
                        "question_id": case["case_id"],
                        "research_question": case["question"],
                        "source": source.model_dump(mode="json"),
                        "source_verification": verification.model_dump(mode="json"),
                    }
                    if verification.status.value != "verified":
                        item["deepseek"] = None
                        item["review_status"] = "pending_source_verification"
                    else:
                        item["deepseek"] = ask_deepseek(
                            client,
                            api_key=api_key,
                            base_url=base_url,
                            model=model,
                            question=case["question"],
                            source=source,
                        )
                        item["review_status"] = "pending_independent_review"
                    draft["retrieval"].append(item)
    finally:
        verifier.close()
    OUTPUT.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT),
        "retrieval_drafts": len(draft["retrieval"]),
        "unresolved_sources": len(draft["unresolved_sources"]),
        "status": draft["status"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
