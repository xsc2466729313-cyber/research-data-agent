"""检查科研数据智能体所依赖公开网站的实时可访问性。

该脚本只访问公开入口，不读取本地缓存，也不把网站可访问等同于
数据已经满足具体研究问题。结构化数据主链与辅助发现来源分别报告，
便于评测时区分“系统检索失败”和“辅助网站暂时不可用”。
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx


SOURCES: tuple[dict[str, Any], ...] = (
    {
        "name": "GDC／TCGA 乳腺癌项目",
        "role": "结构化数据主链",
        "method": "GET",
        "url": "https://api.gdc.cancer.gov/status",
        "expected": "json",
    },
    {
        "name": "NCBI GEO",
        "role": "结构化数据主链",
        "method": "GET",
        "url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE76360",
        "expected": "html",
    },
    {
        "name": "cBioPortal",
        "role": "结构化数据主链",
        "method": "GET",
        "url": "https://www.cbioportal.org/api/studies/brca_metabric",
        "expected": "json",
    },
    {
        "name": "ClinicalTrials.gov",
        "role": "结构化数据主链",
        "method": "GET",
        "url": (
            "https://clinicaltrials.gov/api/v2/studies"
            "?query.cond=Breast%20Cancer&pageSize=1&format=json"
        ),
        "expected": "json",
    },
    {
        "name": "CIViC",
        "role": "结构化数据主链",
        "method": "POST",
        "url": "https://civicdb.org/api/graphql",
        "json": {"query": "query HealthCheck { __typename }"},
        "expected": "json",
    },
    {
        "name": "NCBI BioSample",
        "role": "样本元数据辅助来源",
        "method": "GET",
        "url": (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            "?db=biosample&term=breast%20cancer&retmode=json&retmax=1"
        ),
        "expected": "json",
    },
    {
        "name": "Europe PMC",
        "role": "文献发现辅助来源",
        "method": "GET",
        "url": (
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
            "?query=breast%20cancer&format=json&pageSize=1"
        ),
        "expected": "json",
    },
    {
        "name": "DepMap 官方 Figshare 发布",
        "role": "细胞系资料增强来源",
        "method": "GET",
        "url": "https://api.figshare.com/v2/articles/27993248",
        "expected": "json",
    },
)


async def _check(client: httpx.AsyncClient, source: dict[str, Any]) -> dict[str, Any]:
    started = perf_counter()
    try:
        response = await client.request(
            source["method"],
            source["url"],
            json=source.get("json"),
        )
        elapsed_ms = round((perf_counter() - started) * 1000, 2)
        content_type = response.headers.get("content-type", "").casefold()
        expected = source["expected"]
        type_ok = (
            "json" in content_type
            if expected == "json"
            else "html" in content_type
        )
        available = 200 <= response.status_code < 300 and type_ok
        return {
            "name": source["name"],
            "role": source["role"],
            "available": available,
            "http_status": response.status_code,
            "content_type": content_type.split(";", 1)[0],
            "elapsed_ms": elapsed_ms,
            "url": str(response.url),
            "reason": None if available else "状态码或返回格式不符合预期",
        }
    except httpx.HTTPError as exc:
        return {
            "name": source["name"],
            "role": source["role"],
            "available": False,
            "http_status": None,
            "content_type": None,
            "elapsed_ms": round((perf_counter() - started) * 1000, 2),
            "url": source["url"],
            "reason": type(exc).__name__,
        }


async def _run(timeout_seconds: float) -> dict[str, Any]:
    headers = {"User-Agent": "breast-research-data-agent/online-health-check"}
    async with httpx.AsyncClient(
        timeout=timeout_seconds,
        follow_redirects=True,
        headers=headers,
    ) as client:
        results = await asyncio.gather(*(_check(client, source) for source in SOURCES))
    core = [item for item in results if item["role"] == "结构化数据主链"]
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "mode": "在线实时检查；未读取本地缓存",
        "summary": {
            "source_count": len(results),
            "available_count": sum(bool(item["available"]) for item in results),
            "core_source_count": len(core),
            "core_available_count": sum(bool(item["available"]) for item in core),
        },
        "sources": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="检查项目公开数据源的实时可访问性")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = asyncio.run(_run(args.timeout))
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
