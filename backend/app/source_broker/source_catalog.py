from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from backend.app.oncology import CANCER_PROFILES
from backend.app.source_broker.models import (
    DatasetCandidate,
    ResourceDescriptor,
    SourceCapability,
)


DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parents[3]
    / "configs"
    / "source_capabilities"
    / "seed_datasets.yaml"
)


class SourceCatalogError(RuntimeError):
    pass


class SeedSourceCatalog:
    """Versioned seed knowledge; every capability still requires runtime verification."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_CATALOG_PATH
        try:
            payload = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise SourceCatalogError(f"Cannot load source capability catalog: {type(exc).__name__}") from exc
        self.version = str(payload.get("version") or "unknown")
        self._sources = self._parse_sources(payload.get("sources") or [])
        self._datasets_raw = list(payload.get("datasets") or [])
        self._datasets = self._parse_datasets(self._datasets_raw)

    def sources(self) -> list[SourceCapability]:
        return list(self._sources.values())

    def source(self, source_id: str) -> SourceCapability | None:
        return self._sources.get(source_id)

    def datasets(self) -> list[DatasetCandidate]:
        return list(self._datasets.values())

    def dataset(self, dataset_id: str) -> DatasetCandidate | None:
        return self._datasets.get(dataset_id)

    def legacy_study_profiles(self) -> tuple[dict[str, Any], ...]:
        profiles: list[dict[str, Any]] = []
        for raw in self._datasets_raw:
            tool = str(raw.get("legacy_tool") or "")
            if not tool:
                continue
            profiles.append(
                {
                    "name": str(raw["title"]),
                    "tool": tool,
                    "arg_key": str(raw["legacy_arg_key"]),
                    "arg_value": str(raw["accession"]),
                    "fields": frozenset(str(value) for value in raw.get("field_hints") or []),
                    "needles": frozenset(str(value) for value in raw.get("legacy_needles") or []),
                }
            )
        return tuple(profiles)

    @staticmethod
    def _parse_sources(values: list[dict[str, Any]]) -> dict[str, SourceCapability]:
        output: dict[str, SourceCapability] = {}
        for value in values:
            source = SourceCapability.model_validate(value)
            if source.source_id in output:
                raise SourceCatalogError(f"Duplicate source_id: {source.source_id}")
            output[source.source_id] = source
        return output

    def _parse_datasets(self, values: list[dict[str, Any]]) -> dict[str, DatasetCandidate]:
        values = [*values, *self._configured_oncology_datasets(values)]
        output: dict[str, DatasetCandidate] = {}
        for value in values:
            source = self._sources.get(str(value.get("source_id") or ""))
            if source is None:
                raise SourceCatalogError(f"Unknown source_id for dataset: {value.get('dataset_id')}")
            dataset_id = str(value["dataset_id"])
            access_mode = str(value["access_mode"])
            resources = [
                ResourceDescriptor(
                    resource_id=str(resource["resource_id"]),
                    dataset_id=dataset_id,
                    source_id=source.source_id,
                    resource_type=str(resource["resource_type"]),
                    source_url=str(resource["url"]),
                    access_mode=access_mode,
                    expected_format=resource.get("expected_format"),
                )
                for resource in value.get("resources") or []
            ]
            dataset = DatasetCandidate(
                dataset_id=dataset_id,
                source_id=source.source_id,
                accession=value.get("accession"),
                title=str(value["title"]),
                source_url=str(value["source_url"]),
                diseases=list(value.get("diseases") or []),
                declared_granularity=list(value.get("declared_granularity") or []),
                field_hints=list(value.get("field_hints") or []),
                access_mode=access_mode,
                resources=resources,
                capability_status="seed_requires_runtime_verification",
                authority=source.authority,
                traceability=source.traceability,
                structuredness=source.structuredness,
                cost=source.cost,
            )
            if dataset.dataset_id in output:
                raise SourceCatalogError(f"Duplicate dataset_id: {dataset.dataset_id}")
            output[dataset.dataset_id] = dataset
        return output

    @staticmethod
    def _configured_oncology_datasets(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Expose every verified cancer profile through the seed source catalog."""

        existing = {str(value.get("dataset_id") or "") for value in values}
        generated: list[dict[str, Any]] = []
        fields = [
            "study_id",
            "patient_id",
            "sample_id",
            "source_id",
            "disease",
            "mutation",
            "survival",
            "os_status",
            "subtype",
            "age",
            "stage",
        ]
        for profile in CANCER_PROFILES:
            for study_id in profile.cbioportal_studies:
                dataset_id = f"cbioportal:{study_id}"
                if dataset_id in existing:
                    continue
                generated.append(
                    {
                        "dataset_id": dataset_id,
                        "source_id": "cbioportal",
                        "accession": study_id,
                        "title": f"{profile.canonical_name} (TCGA, PanCancer Atlas)",
                        "source_url": f"https://www.cbioportal.org/study/summary?id={study_id}",
                        "diseases": [profile.key],
                        "declared_granularity": ["patient", "sample"],
                        "field_hints": fields,
                        "access_mode": "OPEN_API",
                        "resources": [
                            {
                                "resource_id": f"{dataset_id}:api",
                                "resource_type": "REST_API",
                                "url": "https://www.cbioportal.org/api",
                                "expected_format": "JSON",
                            }
                        ],
                    }
                )
            for project_id in profile.gdc_projects:
                dataset_id = f"gdc:{project_id}"
                if dataset_id in existing:
                    continue
                generated.append(
                    {
                        "dataset_id": dataset_id,
                        "source_id": "gdc",
                        "accession": project_id,
                        "title": f"GDC {project_id} {profile.canonical_name} Project",
                        "source_url": f"https://portal.gdc.cancer.gov/projects/{project_id}",
                        "diseases": [profile.key],
                        "declared_granularity": ["patient", "sample"],
                        "field_hints": fields,
                        "access_mode": "OPEN_API",
                        "resources": [
                            {
                                "resource_id": f"{dataset_id}:files_api",
                                "resource_type": "REST_API",
                                "url": "https://api.gdc.cancer.gov/files",
                                "expected_format": "JSON",
                            }
                        ],
                    }
                )
        return generated


@lru_cache(maxsize=1)
def default_source_catalog() -> SeedSourceCatalog:
    return SeedSourceCatalog()


def seed_legacy_study_profiles() -> tuple[dict[str, Any], ...]:
    return default_source_catalog().legacy_study_profiles()
