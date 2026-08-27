from __future__ import annotations

from datetime import datetime, timezone

from backend.app.literature.models import (
    LiteratureProviderTrace,
    LiteratureScan,
    LiteratureSearchRequest,
    PaperRecord,
)
from backend.app.literature.providers import (
    EuropePMCProvider,
    GiiispProvider,
    LiteratureProvider,
)


class LiteratureAgent:
    """Search replaceable providers and normalize papers without patient-level joins."""

    def __init__(self, providers: list[LiteratureProvider] | None = None) -> None:
        self.providers = providers if providers is not None else [GiiispProvider(), EuropePMCProvider()]

    def scan(self, *, topic_id: str, query: str, max_records: int = 20) -> LiteratureScan:
        request = LiteratureSearchRequest(query=query, max_records=max_records)
        papers: list[PaperRecord] = []
        traces: list[LiteratureProviderTrace] = []
        warnings: list[str] = []
        remaining = max_records
        for provider in self.providers:
            if remaining <= 0:
                break
            if not provider.configured:
                now = datetime.now(timezone.utc)
                traces.append(
                    LiteratureProviderTrace(
                        provider=provider.name,
                        query=query,
                        requested_at=now,
                        completed_at=now,
                        status="skipped",
                        result_count=0,
                        error_type="not_configured",
                    )
                )
                warnings.append(f"{provider.name} 未配置，已跳过。")
                continue
            try:
                result = provider.search(request.model_copy(update={"max_records": remaining}))
            except Exception as exc:  # Provider boundary: record type, never credentials/message bodies.
                now = datetime.now(timezone.utc)
                traces.append(
                    LiteratureProviderTrace(
                        provider=provider.name,
                        query=query,
                        requested_at=now,
                        completed_at=now,
                        status="failed",
                        result_count=0,
                        error_type=type(exc).__name__,
                    )
                )
                warnings.append(f"{provider.name} 检索失败，已尝试下一 Provider。")
                continue
            traces.append(result.trace)
            papers.extend(result.papers)
            papers = self._deduplicate(papers)
            remaining = max(0, max_records - len(papers))
        if not papers:
            warnings.append("本次未获得可核验论文记录；候选问题仅为确定性规划草案，不能视为文献结论。")
        return LiteratureScan(
            topic_id=topic_id,
            query=query,
            papers=papers[:max_records],
            provider_traces=traces,
            warnings=list(dict.fromkeys(warnings)),
            scanned_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _deduplicate(papers: list[PaperRecord]) -> list[PaperRecord]:
        seen: set[str] = set()
        output: list[PaperRecord] = []
        for paper in papers:
            key = (
                f"doi:{paper.doi.casefold()}"
                if paper.doi
                else f"pmid:{paper.pmid}"
                if paper.pmid
                else f"title:{paper.title.casefold()}"
            )
            if key in seen:
                continue
            seen.add(key)
            output.append(paper)
        return output
