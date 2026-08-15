from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from backend.app.models import SourceItem
from backend.app.sources.civic.errors import CIViCAdapterError, CIViCErrorCode
from backend.app.sources.civic.models import (
    CIViCAdapterRequest,
    CIViCAdapterResult,
    CIViCEvidenceRecord,
    CIViCRawTable,
    CIViCRequestTrace,
    CIViCTableName,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "civic"


@dataclass(frozen=True)
class _SearchPayload:
    payload: dict[str, Any]
    cache_hit: bool
    payload_path: Path
    sha256: str
    request: CIViCRequestTrace


class CIViCAdapter:
    GRAPHQL_URL = "https://civicdb.org/api/graphql"
    SITE_URL = "https://civicdb.org"
    ACCEPTED_STATUS = "ACCEPTED"
    GRAPHQL_QUERY = """\
query BreastEvidence(
  $diseaseName: String!
  $first: Int!
  $after: String
  $molecularProfileName: String
  $therapyName: String
  $evidenceType: EvidenceType
  $evidenceLevel: EvidenceLevel
) {
  evidenceItems(
    diseaseName: $diseaseName
    status: ACCEPTED
    first: $first
    after: $after
    molecularProfileName: $molecularProfileName
    therapyName: $therapyName
    evidenceType: $evidenceType
    evidenceLevel: $evidenceLevel
  ) {
    totalCount
    pageInfo {
      endCursor
      hasNextPage
    }
    nodes {
      id
      name
      link
      status
      description
      evidenceType
      evidenceLevel
      evidenceRating
      evidenceDirection
      significance
      variantOrigin
      therapyInteractionType
      disease {
        id
        doid
        name
        displayName
        diseaseAliases
        diseaseUrl
        link
        deprecated
      }
      therapies {
        id
        name
        ncitId
        therapyAliases
        therapyUrl
        link
        deprecated
        description
      }
      source {
        id
        sourceType
        citationId
        citation
        title
        authorString
        journal
        publicationDate
        publicationYear
        pmcId
        sourceUrl
        link
        retracted
        deprecated
      }
      molecularProfile {
        id
        name
        rawName
        link
        isComplex
        isMultiVariant
        deprecated
        molecularProfileAliases
        variants {
          __typename
          id
          name
          link
          variantAliases
          feature {
            id
            name
            fullName
            featureType
            featureAliases
            featureInstance {
              __typename
              ... on Gene {
                id
                name
                entrezId
              }
              ... on Fusion {
                id
                name
                fivePrimeGene { id name entrezId }
                threePrimeGene { id name entrezId }
                knownPartnerGenes { id name entrezId }
              }
            }
          }
        }
      }
    }
  }
}
"""

    def __init__(
        self,
        *,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        client: httpx.Client | None = None,
        timeout_seconds: float = 90.0,
        cache_ttl_seconds: int = 86_400,
        graphql_url: str = GRAPHQL_URL,
        api_key: str | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self.graphql_url = graphql_url
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "breast-cancer-research-data-agent/0.6",
        }
        token = api_key if api_key is not None else os.getenv("CIVIC_API_KEY")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers=headers,
        )

    def run(self, request: CIViCAdapterRequest) -> CIViCAdapterResult:
        self._validate_input(request)
        options = request.options
        variables: dict[str, Any] = {
            "diseaseName": options.disease_name,
            "first": options.max_evidence_items,
        }
        optional_variables = {
            "after": options.after_cursor,
            "molecularProfileName": options.molecular_profile_name,
            "therapyName": options.therapy_name,
            "evidenceType": (
                options.evidence_type.value if options.evidence_type else None
            ),
            "evidenceLevel": (
                options.evidence_level.value if options.evidence_level else None
            ),
        }
        variables.update(
            {key: value for key, value in optional_variables.items() if value is not None}
        )
        search = self._acquire_search(
            variables=variables,
            refresh=options.refresh_cache,
        )
        connection = self._connection(search.payload)
        total_count = connection.get("totalCount")
        if not isinstance(total_count, int) or total_count < 0:
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_RESPONSE,
                "CIViC response has an invalid totalCount.",
            )
        nodes = connection.get("nodes")
        if not isinstance(nodes, list) or not all(isinstance(node, dict) for node in nodes):
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_RESPONSE,
                "CIViC response does not contain an evidence item object list.",
            )
        if len(nodes) > options.max_evidence_items:
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_RESPONSE,
                "CIViC returned more evidence items than requested.",
                details={"requested": options.max_evidence_items, "returned": len(nodes)},
            )
        if not nodes:
            raise CIViCAdapterError(
                CIViCErrorCode.NO_EVIDENCE,
                "CIViC returned no accepted evidence for the requested query.",
                details={
                    "disease_name": options.disease_name,
                    "molecular_profile_name": options.molecular_profile_name,
                    "therapy_name": options.therapy_name,
                },
            )
        page_info = self._required_dict(connection, "pageInfo", context="evidenceItems")
        has_next_page = page_info.get("hasNextPage")
        end_cursor = page_info.get("endCursor")
        if not isinstance(has_next_page, bool) or (
            end_cursor is not None and not isinstance(end_cursor, str)
        ):
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_RESPONSE,
                "CIViC response has invalid pagination metadata.",
            )

        evidence_records: list[CIViCEvidenceRecord] = []
        table_rows: dict[CIViCTableName, list[dict[str, Any]]] = {
            name: [] for name in CIViCTableName
        }
        seen: dict[CIViCTableName, set[Any]] = {
            name: set() for name in CIViCTableName
        }
        for index, raw_evidence in enumerate(nodes):
            raw_field = f"evidenceItems.nodes[{index}]"
            evidence_record = self._build_evidence_record(
                task_id=request.search_plan.task_id,
                raw_evidence=raw_evidence,
                raw_field=raw_field,
                cache_hit=search.cache_hit,
                refresh=options.refresh_cache,
            )
            evidence_records.append(evidence_record)
            self._append_rows(
                raw_evidence=raw_evidence,
                raw_field=raw_field,
                record=evidence_record,
                table_rows=table_rows,
                seen=seen,
            )

        tables = [
            self._table(
                table_name=table_name,
                rows=table_rows[table_name],
                max_rows=options.max_rows_per_table,
            )
            for table_name in CIViCTableName
        ]
        return CIViCAdapterResult(
            task_id=request.search_plan.task_id,
            disease_name=options.disease_name,
            total_count=total_count,
            next_cursor=end_cursor if has_next_page else None,
            search_request=search.request,
            evidence_items=evidence_records,
            tables=tables,
            source_items=[record.source_item for record in evidence_records],
            cache_hit=search.cache_hit,
            queried_at=datetime.now(timezone.utc),
            notice=(
                "仅接入 CIViC ACCEPTED 知识证据；证据陈述、分子谱、疾病、治疗和出版物"
                "均保留原始值。复杂分子谱只按整体上下文建立关系，不把成员变异自动解释为"
                "独立疗效结论，也不与患者记录自动合并。"
            ),
        )

    def _validate_input(self, request: CIViCAdapterRequest) -> None:
        if not any(
            plan.source.casefold() in {"civic", "civicdb", "civic knowledgebase"}
            for plan in request.search_plan.plans
        ):
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_PLAN,
                "SearchPlan does not contain a CIViC task.",
            )
        values = {
            "disease_name": request.options.disease_name,
            "molecular_profile_name": request.options.molecular_profile_name,
            "therapy_name": request.options.therapy_name,
            "after_cursor": request.options.after_cursor,
        }
        invalid = {
            name: value
            for name, value in values.items()
            if value is not None
            and (not value or any(ord(character) < 32 for character in value))
        }
        if invalid:
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_QUERY,
                "CIViC query contains invalid control characters.",
                details={"fields": sorted(invalid)},
            )

    def _acquire_search(
        self, *, variables: dict[str, Any], refresh: bool
    ) -> _SearchPayload:
        trace = CIViCRequestTrace(
            method="POST",
            url=self.graphql_url,
            query=self.GRAPHQL_QUERY,
            variables=variables,
        )
        request_hash = self._request_hash(trace)
        payload_path = self.cache_dir / "responses" / f"{request_hash}.json"
        manifest_path = self.cache_dir / "responses" / f"{request_hash}.cache.json"
        if not refresh:
            cached = self._read_search_cache(
                payload_path=payload_path,
                manifest_path=manifest_path,
                trace=trace,
            )
            if cached is not None:
                return cached

        try:
            response = self.client.post(
                self.graphql_url,
                json={"query": self.GRAPHQL_QUERY, "variables": variables},
            )
        except httpx.TimeoutException as exc:
            raise CIViCAdapterError(
                CIViCErrorCode.TIMEOUT,
                "CIViC GraphQL request timed out.",
                retryable=True,
                details={"url": self.graphql_url},
            ) from exc
        except httpx.RequestError as exc:
            raise CIViCAdapterError(
                CIViCErrorCode.NETWORK_ERROR,
                "CIViC GraphQL network request failed.",
                retryable=True,
                details={
                    "url": self.graphql_url,
                    "error_type": type(exc).__name__,
                },
            ) from exc
        self._raise_for_status(response, url=self.graphql_url)
        try:
            payload = response.json()
        except ValueError as exc:
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_RESPONSE,
                "CIViC returned non-JSON content.",
                details={"content_type": response.headers.get("content-type")},
            ) from exc
        if not isinstance(payload, dict):
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_RESPONSE,
                "CIViC GraphQL response is not an object.",
            )
        self._raise_graphql_errors(payload)
        self._connection(payload)
        sha256 = self._write_search_cache(
            payload_path=payload_path,
            manifest_path=manifest_path,
            payload=payload,
            trace=trace,
        )
        return _SearchPayload(
            payload=payload,
            cache_hit=False,
            payload_path=payload_path,
            sha256=sha256,
            request=trace,
        )

    def _build_evidence_record(
        self,
        *,
        task_id: str,
        raw_evidence: dict[str, Any],
        raw_field: str,
        cache_hit: bool,
        refresh: bool,
    ) -> CIViCEvidenceRecord:
        civic_id = self._required_int(raw_evidence, "id", context=raw_field)
        name = self._required_str(raw_evidence, "name", context=raw_field)
        status = self._required_str(raw_evidence, "status", context=raw_field)
        if status != self.ACCEPTED_STATUS:
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_RESPONSE,
                f"CIViC returned non-accepted evidence item EID{civic_id}.",
                details={"status": status},
            )
        evidence_type = self._required_str(
            raw_evidence, "evidenceType", context=raw_field
        )
        evidence_level = self._required_str(
            raw_evidence, "evidenceLevel", context=raw_field
        )
        evidence_direction = self._required_str(
            raw_evidence, "evidenceDirection", context=raw_field
        )
        significance = self._required_str(
            raw_evidence, "significance", context=raw_field
        )
        disease = self._required_dict(raw_evidence, "disease", context=raw_field)
        molecular_profile = self._required_dict(
            raw_evidence, "molecularProfile", context=raw_field
        )
        source = self._required_dict(raw_evidence, "source", context=raw_field)
        therapies = self._object_list(
            raw_evidence, "therapies", context=f"{raw_field}.therapies"
        )
        self._object_list(
            molecular_profile,
            "variants",
            context=f"{raw_field}.molecularProfile.variants",
            require_nonempty=True,
        )
        evidence_rating = raw_evidence.get("evidenceRating")
        if evidence_rating is not None and (
            not isinstance(evidence_rating, int) or not 1 <= evidence_rating <= 5
        ):
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_RESPONSE,
                f"CIViC EID{civic_id} has an invalid evidence rating.",
            )
        raw_path, sha256 = self._write_evidence_payload(
            civic_id=civic_id,
            raw_evidence=raw_evidence,
            refresh=refresh,
        )
        link = raw_evidence.get("link")
        evidence_url = self._absolute_civic_url(link, fallback=f"/evidence/{civic_id}")
        source_item = SourceItem(
            source_id=f"civic:EID{civic_id}",
            task_id=task_id,
            source_name="CIViC",
            source_type="knowledgebase",
            accession=f"EID{civic_id}",
            url=evidence_url,
            file_type="json:evidence-item",
            local_path=self._display_path(raw_path),
            checksum=f"sha256:{sha256}",
            status="cached" if cache_hit else "retrieved",
        )
        citation = source.get("citation")
        citation_id = source.get("citationId")
        return CIViCEvidenceRecord(
            civic_evidence_id=civic_id,
            evidence_id=f"CIViC:EID{civic_id}",
            name=name,
            evidence_url=evidence_url,
            status=status,
            evidence_type=evidence_type,
            evidence_level=evidence_level,
            evidence_rating=evidence_rating,
            evidence_direction=evidence_direction,
            significance=significance,
            disease_name=self._required_str(disease, "name", context=f"{raw_field}.disease"),
            molecular_profile_name=self._required_str(
                molecular_profile, "name", context=f"{raw_field}.molecularProfile"
            ),
            therapy_names=[
                self._required_str(
                    therapy,
                    "name",
                    context=f"{raw_field}.therapies[{index}]",
                )
                for index, therapy in enumerate(therapies)
            ],
            publication_citation=citation if isinstance(citation, str) else None,
            publication_id=citation_id if isinstance(citation_id, str) else None,
            raw_evidence=raw_evidence,
            source_item=source_item,
        )

    def _append_rows(
        self,
        *,
        raw_evidence: dict[str, Any],
        raw_field: str,
        record: CIViCEvidenceRecord,
        table_rows: dict[CIViCTableName, list[dict[str, Any]]],
        seen: dict[CIViCTableName, set[Any]],
    ) -> None:
        civic_id = record.civic_evidence_id
        evidence_key = record.evidence_id
        source_item_id = record.source_item.source_id
        table_rows[CIViCTableName.EVIDENCE_ITEMS].append(
            {
                **raw_evidence,
                "civic_evidence_id": civic_id,
                "evidence_id": evidence_key,
                "source_id": source_item_id,
                "raw_field": raw_field,
                "raw_value": raw_evidence,
            }
        )

        disease = self._required_dict(raw_evidence, "disease", context=raw_field)
        disease_id = self._required_int(disease, "id", context=f"{raw_field}.disease")
        self._add_unique_row(
            CIViCTableName.DISEASES,
            disease_id,
            {
                **disease,
                "civic_disease_id": disease_id,
                "raw_field": f"{raw_field}.disease",
                "raw_value": disease,
            },
            table_rows,
            seen,
        )

        molecular_profile = self._required_dict(
            raw_evidence, "molecularProfile", context=raw_field
        )
        profile_id = self._required_int(
            molecular_profile, "id", context=f"{raw_field}.molecularProfile"
        )
        self._add_unique_row(
            CIViCTableName.MOLECULAR_PROFILES,
            profile_id,
            {
                **molecular_profile,
                "civic_molecular_profile_id": profile_id,
                "raw_field": f"{raw_field}.molecularProfile",
                "raw_value": molecular_profile,
            },
            table_rows,
            seen,
        )

        variants = self._object_list(
            molecular_profile,
            "variants",
            context=f"{raw_field}.molecularProfile.variants",
            require_nonempty=True,
        )
        variant_ids: list[int] = []
        variant_names: list[str] = []
        gene_ids: list[int] = []
        gene_symbols: list[str] = []
        for variant_index, variant in enumerate(variants):
            variant_path = f"{raw_field}.molecularProfile.variants[{variant_index}]"
            variant_id = self._required_int(variant, "id", context=variant_path)
            variant_name = self._required_str(variant, "name", context=variant_path)
            feature = self._required_dict(variant, "feature", context=variant_path)
            feature_id = self._required_int(feature, "id", context=f"{variant_path}.feature")
            variant_ids.append(variant_id)
            variant_names.append(variant_name)
            self._add_unique_row(
                CIViCTableName.VARIANTS,
                variant_id,
                {
                    **variant,
                    "civic_variant_id": variant_id,
                    "civic_feature_id": feature_id,
                    "civic_molecular_profile_id": profile_id,
                    "raw_field": variant_path,
                    "raw_value": variant,
                },
                table_rows,
                seen,
            )
            for gene_id, gene_symbol, gene, gene_path in self._genes_from_feature(
                feature=feature,
                feature_path=f"{variant_path}.feature",
            ):
                if gene_id not in gene_ids:
                    gene_ids.append(gene_id)
                    gene_symbols.append(gene_symbol)
                self._add_unique_row(
                    CIViCTableName.GENES,
                    gene_id,
                    {
                        **gene,
                        "civic_gene_id": gene_id,
                        "gene_symbol": gene_symbol,
                        "entrez_id": self._gene_entrez_id(gene),
                        "raw_field": gene_path,
                        "raw_value": gene,
                    },
                    table_rows,
                    seen,
                )

        therapies = self._object_list(
            raw_evidence, "therapies", context=f"{raw_field}.therapies"
        )
        therapy_ids: list[int] = []
        therapy_names: list[str] = []
        for therapy_index, therapy in enumerate(therapies):
            therapy_path = f"{raw_field}.therapies[{therapy_index}]"
            therapy_id = self._required_int(therapy, "id", context=therapy_path)
            therapy_name = self._required_str(therapy, "name", context=therapy_path)
            therapy_ids.append(therapy_id)
            therapy_names.append(therapy_name)
            self._add_unique_row(
                CIViCTableName.THERAPIES,
                therapy_id,
                {
                    **therapy,
                    "civic_therapy_id": therapy_id,
                    "raw_field": therapy_path,
                    "raw_value": therapy,
                },
                table_rows,
                seen,
            )

        source = self._required_dict(raw_evidence, "source", context=raw_field)
        civic_source_id = self._required_int(source, "id", context=f"{raw_field}.source")
        self._add_unique_row(
            CIViCTableName.SOURCES,
            civic_source_id,
            {
                **source,
                "civic_source_id": civic_source_id,
                "publication_id": source.get("citationId"),
                "raw_field": f"{raw_field}.source",
                "raw_value": source,
            },
            table_rows,
            seen,
        )

        relation = {
            "evidence_id": evidence_key,
            "civic_evidence_id": civic_id,
            "civic_disease_id": disease_id,
            "civic_molecular_profile_id": profile_id,
            "civic_gene_ids": gene_ids,
            "gene_symbols": gene_symbols,
            "civic_variant_ids": variant_ids,
            "variant_names": variant_names,
            "civic_therapy_ids": therapy_ids,
            "therapy_names": therapy_names,
            "civic_source_id": civic_source_id,
            "publication_id": source.get("citationId"),
            "source_id": source_item_id,
            "relation_scope": "molecular_profile_context",
            "is_complex_molecular_profile": molecular_profile.get("isComplex"),
            "raw_field": raw_field,
            "raw_value": raw_evidence,
        }
        table_rows[CIViCTableName.EVIDENCE_RELATIONS].append(relation)

    def _genes_from_feature(
        self, *, feature: dict[str, Any], feature_path: str
    ) -> list[tuple[int, str, dict[str, Any], str]]:
        feature_type = feature.get("featureType")
        feature_instance = feature.get("featureInstance")
        if feature_type == "GENE":
            gene_id = self._required_int(feature, "id", context=feature_path)
            gene_symbol = self._required_str(feature, "name", context=feature_path)
            return [(gene_id, gene_symbol, feature, feature_path)]
        if not isinstance(feature_instance, dict) or (
            feature_instance.get("__typename") != "Fusion"
        ):
            return []
        genes: list[tuple[int, str, dict[str, Any], str]] = []
        for field_name in ("fivePrimeGene", "threePrimeGene"):
            gene = feature_instance.get(field_name)
            if isinstance(gene, dict):
                genes.append(
                    self._gene_tuple(
                        gene,
                        f"{feature_path}.featureInstance.{field_name}",
                    )
                )
        known_partners = feature_instance.get("knownPartnerGenes")
        if known_partners is not None:
            if not isinstance(known_partners, list) or not all(
                isinstance(gene, dict) for gene in known_partners
            ):
                raise CIViCAdapterError(
                    CIViCErrorCode.INVALID_RESPONSE,
                    f"CIViC {feature_path}.featureInstance.knownPartnerGenes is invalid.",
                )
            genes.extend(
                self._gene_tuple(
                    gene,
                    f"{feature_path}.featureInstance.knownPartnerGenes[{index}]",
                )
                for index, gene in enumerate(known_partners)
            )
        unique: dict[int, tuple[int, str, dict[str, Any], str]] = {}
        for gene in genes:
            unique.setdefault(gene[0], gene)
        return list(unique.values())

    def _gene_tuple(
        self, gene: dict[str, Any], gene_path: str
    ) -> tuple[int, str, dict[str, Any], str]:
        return (
            self._required_int(gene, "id", context=gene_path),
            self._required_str(gene, "name", context=gene_path),
            gene,
            gene_path,
        )

    @staticmethod
    def _gene_entrez_id(gene: dict[str, Any]) -> int | None:
        direct = gene.get("entrezId")
        if isinstance(direct, int) and not isinstance(direct, bool):
            return direct
        feature_instance = gene.get("featureInstance")
        if isinstance(feature_instance, dict):
            nested = feature_instance.get("entrezId")
            if isinstance(nested, int) and not isinstance(nested, bool):
                return nested
        return None

    @staticmethod
    def _add_unique_row(
        table_name: CIViCTableName,
        key: Any,
        row: dict[str, Any],
        table_rows: dict[CIViCTableName, list[dict[str, Any]]],
        seen: dict[CIViCTableName, set[Any]],
    ) -> None:
        if key in seen[table_name]:
            return
        seen[table_name].add(key)
        table_rows[table_name].append(row)

    @staticmethod
    def _table(
        *, table_name: CIViCTableName, rows: list[dict[str, Any]], max_rows: int
    ) -> CIViCRawTable:
        visible_rows = rows[:max_rows]
        return CIViCRawTable(
            table_name=table_name,
            raw_fields=sorted({key for row in rows for key in row}),
            rows=visible_rows,
            row_count=len(visible_rows),
            upstream_row_count=len(rows),
            truncated=len(rows) > len(visible_rows),
        )

    def _write_evidence_payload(
        self,
        *,
        civic_id: int,
        raw_evidence: dict[str, Any],
        refresh: bool,
    ) -> tuple[Path, str]:
        payload_bytes = self._json_bytes(raw_evidence)
        sha256 = hashlib.sha256(payload_bytes).hexdigest()
        target = self.cache_dir / "evidence" / f"EID{civic_id}" / f"{sha256[:24]}.json"
        if target.is_file() and not refresh:
            actual_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
            if actual_sha256 != sha256:
                raise CIViCAdapterError(
                    CIViCErrorCode.CACHE_ERROR,
                    f"Cached CIViC EID{civic_id} failed SHA-256 verification.",
                    details={"expected": sha256, "actual": actual_sha256},
                )
            return target, sha256
        temporary = target.with_suffix(target.suffix + ".tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(payload_bytes)
            temporary.replace(target)
        except OSError as exc:
            if temporary.is_file():
                temporary.unlink()
            raise CIViCAdapterError(
                CIViCErrorCode.CACHE_ERROR,
                f"Could not write CIViC EID{civic_id} cache.",
            ) from exc
        return target, sha256

    def _read_search_cache(
        self,
        *,
        payload_path: Path,
        manifest_path: Path,
        trace: CIViCRequestTrace,
    ) -> _SearchPayload | None:
        if not payload_path.exists() and not manifest_path.exists():
            return None
        if not payload_path.is_file() or not manifest_path.is_file():
            raise CIViCAdapterError(
                CIViCErrorCode.CACHE_ERROR,
                f"CIViC cache is incomplete: {payload_path.name}",
            )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            cached_at = datetime.fromisoformat(manifest["cached_at"])
            expected_sha256 = str(manifest["sha256"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CIViCAdapterError(
                CIViCErrorCode.CACHE_ERROR,
                f"CIViC cache manifest is unreadable: {manifest_path.name}",
            ) from exc
        if cached_at.tzinfo is None:
            raise CIViCAdapterError(
                CIViCErrorCode.CACHE_ERROR,
                f"CIViC cache timestamp lacks a timezone: {manifest_path.name}",
            )
        if datetime.now(timezone.utc) - cached_at > self.cache_ttl:
            return None
        try:
            payload_bytes = payload_path.read_bytes()
            actual_sha256 = hashlib.sha256(payload_bytes).hexdigest()
            payload = json.loads(payload_bytes)
        except (OSError, ValueError, TypeError) as exc:
            raise CIViCAdapterError(
                CIViCErrorCode.CACHE_ERROR,
                f"CIViC cached response is unreadable: {payload_path.name}",
            ) from exc
        if actual_sha256 != expected_sha256:
            raise CIViCAdapterError(
                CIViCErrorCode.CACHE_ERROR,
                f"CIViC cached response failed SHA-256 verification: {payload_path.name}",
                details={"expected": expected_sha256, "actual": actual_sha256},
            )
        if not isinstance(payload, dict):
            raise CIViCAdapterError(
                CIViCErrorCode.CACHE_ERROR,
                f"CIViC cached response has an invalid shape: {payload_path.name}",
            )
        self._raise_graphql_errors(payload)
        self._connection(payload)
        return _SearchPayload(
            payload=payload,
            cache_hit=True,
            payload_path=payload_path,
            sha256=actual_sha256,
            request=trace,
        )

    def _write_search_cache(
        self,
        *,
        payload_path: Path,
        manifest_path: Path,
        payload: dict[str, Any],
        trace: CIViCRequestTrace,
    ) -> str:
        payload_bytes = self._json_bytes(payload)
        sha256 = hashlib.sha256(payload_bytes).hexdigest()
        payload_temporary = payload_path.with_suffix(payload_path.suffix + ".tmp")
        manifest_temporary = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
        try:
            payload_path.parent.mkdir(parents=True, exist_ok=True)
            payload_temporary.write_bytes(payload_bytes)
            manifest_temporary.write_text(
                json.dumps(
                    {
                        "cached_at": datetime.now(timezone.utc).isoformat(),
                        "sha256": sha256,
                        "request": trace.model_dump(mode="json"),
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            payload_temporary.replace(payload_path)
            manifest_temporary.replace(manifest_path)
        except OSError as exc:
            for temporary in (payload_temporary, manifest_temporary):
                if temporary.is_file():
                    temporary.unlink()
            if payload_path.is_file() and not manifest_path.is_file():
                payload_path.unlink()
            raise CIViCAdapterError(
                CIViCErrorCode.CACHE_ERROR,
                f"Could not write CIViC search cache: {payload_path.name}",
            ) from exc
        return sha256

    @staticmethod
    def _connection(payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_RESPONSE,
                "CIViC GraphQL response has no data object.",
            )
        connection = data.get("evidenceItems")
        if not isinstance(connection, dict):
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_RESPONSE,
                "CIViC GraphQL response has no evidenceItems connection.",
            )
        return connection

    @staticmethod
    def _raise_graphql_errors(payload: dict[str, Any]) -> None:
        errors = payload.get("errors")
        if errors is None or errors == []:
            return
        if not isinstance(errors, list):
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_RESPONSE,
                "CIViC GraphQL errors field is invalid.",
            )
        messages = [
            error.get("message")
            for error in errors
            if isinstance(error, dict) and isinstance(error.get("message"), str)
        ]
        raise CIViCAdapterError(
            CIViCErrorCode.GRAPHQL_ERROR,
            "CIViC GraphQL returned one or more errors.",
            details={"messages": messages[:10], "error_count": len(errors)},
        )

    @staticmethod
    def _required_dict(
        payload: dict[str, Any], key: str, *, context: str
    ) -> dict[str, Any]:
        value = payload.get(key)
        if not isinstance(value, dict):
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_RESPONSE,
                f"CIViC {context}.{key} is missing or invalid.",
            )
        return value

    @staticmethod
    def _required_str(payload: dict[str, Any], key: str, *, context: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_RESPONSE,
                f"CIViC {context}.{key} is missing or invalid.",
            )
        return value

    @staticmethod
    def _required_int(payload: dict[str, Any], key: str, *, context: str) -> int:
        value = payload.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_RESPONSE,
                f"CIViC {context}.{key} is missing or invalid.",
            )
        return value

    @staticmethod
    def _object_list(
        payload: dict[str, Any],
        key: str,
        *,
        context: str,
        require_nonempty: bool = False,
    ) -> list[dict[str, Any]]:
        value = payload.get(key)
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_RESPONSE,
                f"CIViC {context} is not a list of objects.",
            )
        if require_nonempty and not value:
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_RESPONSE,
                f"CIViC {context} is unexpectedly empty.",
            )
        return value

    @staticmethod
    def _raise_for_status(response: httpx.Response, *, url: str) -> None:
        status = response.status_code
        if status < 400:
            return
        if status == 400:
            raise CIViCAdapterError(
                CIViCErrorCode.INVALID_QUERY,
                "CIViC rejected the GraphQL request.",
                upstream_status=status,
                details={"url": url},
            )
        if status in {401, 403}:
            raise CIViCAdapterError(
                CIViCErrorCode.AUTHENTICATION_ERROR,
                "CIViC rejected the configured API credentials.",
                upstream_status=status,
                details={"url": url},
            )
        if status == 429:
            raise CIViCAdapterError(
                CIViCErrorCode.RATE_LIMITED,
                "CIViC rate limited the request.",
                retryable=True,
                upstream_status=status,
                details={"url": url},
            )
        raise CIViCAdapterError(
            CIViCErrorCode.REMOTE_ERROR,
            f"CIViC returned HTTP {status}.",
            retryable=status >= 500,
            upstream_status=status,
            details={"url": url},
        )

    @staticmethod
    def _request_hash(trace: CIViCRequestTrace) -> str:
        encoded = json.dumps(
            trace.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:24]

    @staticmethod
    def _json_bytes(payload: Any) -> bytes:
        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")

    @classmethod
    def _absolute_civic_url(cls, value: Any, *, fallback: str) -> str:
        path = value if isinstance(value, str) and value else fallback
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{cls.SITE_URL}/{path.lstrip('/')}"

    @staticmethod
    def _display_path(path: Path) -> str:
        try:
            return path.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return str(path)
