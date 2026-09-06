from __future__ import annotations

from pathlib import Path

import yaml

from backend.app.v30.models import RegistrySource, RegistrySourceList

KNOWN_FETCH_BINDINGS = {
    "search_gdc",
    "search_geo",
    "search_cbioportal",
    "search_trials",
    "search_civic",
    "search_europe_pmc",
}

KNOWN_DISCOVERY_BINDINGS = {
    "search_geo_catalog",
    "search_europe_pmc",
}

ALLOWED_STATUS = {"active", "catalog_only", "planned"}
NON_FETCH_DOMAINS = {"astronomy", "materials"}
REQUIRED_FIELDS = (
    "source_key",
    "display_name",
    "domain",
    "resource_kind",
    "modalities",
    "fetch_binding",
    "discovery_binding",
    "status",
)

_DEFAULT_REGISTRY_DIR = Path(__file__).resolve().parents[4] / "configs" / "v30" / "source_registry"


class RegistryConfigError(ValueError):
    pass


class SourceRegistryService:
    """Read-only source capability catalog. This is not a data adapter."""

    def __init__(self, registry_dir: Path | None = None) -> None:
        self.registry_dir = registry_dir or _DEFAULT_REGISTRY_DIR
        self._sources = self._load()

    def list_sources(
        self,
        *,
        domain: str | None = None,
        status: str | None = None,
        integrate_eligible: bool | None = None,
    ) -> RegistrySourceList:
        items = list(self._sources)
        if domain:
            items = [item for item in items if item.domain == domain]
        if status:
            items = [item for item in items if item.status == status]
        if integrate_eligible is not None:
            items = [item for item in items if item.integrate_eligible is integrate_eligible]
        return RegistrySourceList(sources=items)

    def get(self, source_key: str) -> RegistrySource | None:
        key = (source_key or "").strip()
        for item in self._sources:
            if item.source_key == key:
                return item
        return None

    def integrate_eligible_keys(self) -> set[str]:
        return {item.source_key for item in self._sources if item.integrate_eligible}

    def _load(self) -> list[RegistrySource]:
        if not self.registry_dir.is_dir():
            raise RegistryConfigError(f"source registry directory missing: {self.registry_dir}")
        loaded: list[RegistrySource] = []
        seen: set[str] = set()
        for path in sorted(self.registry_dir.glob("*.yaml")):
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for raw in payload.get("sources") or []:
                source = self._validate(raw, path.name)
                if source.source_key in seen:
                    raise RegistryConfigError(f"duplicate source_key: {source.source_key}")
                seen.add(source.source_key)
                loaded.append(source)
        if not loaded:
            raise RegistryConfigError("source registry is empty")
        return loaded

    def _validate(self, raw: dict, filename: str) -> RegistrySource:
        missing = [field for field in REQUIRED_FIELDS if field not in raw]
        if missing:
            raise RegistryConfigError(f"{filename} missing fields {missing}")
        key = str(raw["source_key"]).strip()
        domain = str(raw["domain"]).strip()
        status = str(raw["status"]).strip()
        fetch_binding = _blank_to_none(raw.get("fetch_binding"))
        discovery_binding = _blank_to_none(raw.get("discovery_binding"))
        if not key:
            raise RegistryConfigError(f"{filename} has empty source_key")
        if status not in ALLOWED_STATUS:
            raise RegistryConfigError(f"{filename}:{key} has invalid status {status}")
        if domain in NON_FETCH_DOMAINS:
            if status == "active" or fetch_binding:
                raise RegistryConfigError(
                    f"{filename}:{key} is {domain}; only catalog_only/planned without fetch_binding are allowed"
                )
        if fetch_binding and fetch_binding not in KNOWN_FETCH_BINDINGS:
            raise RegistryConfigError(f"{filename}:{key} fetch_binding is not an existing tool: {fetch_binding}")
        if discovery_binding and discovery_binding not in KNOWN_DISCOVERY_BINDINGS:
            raise RegistryConfigError(
                f"{filename}:{key} discovery_binding is not an existing catalog tool: {discovery_binding}"
            )
        if status == "active" and not fetch_binding:
            raise RegistryConfigError(f"{filename}:{key} active source must bind an existing fetch tool")
        integrate_eligible = status == "active" and fetch_binding in KNOWN_FETCH_BINDINGS
        return RegistrySource(
            source_key=key,
            display_name=str(raw["display_name"]).strip(),
            domain=domain,
            resource_kind=str(raw["resource_kind"]).strip(),
            modalities=[str(item) for item in (raw.get("modalities") or [])],
            fetch_binding=fetch_binding,
            discovery_binding=discovery_binding,
            status=status,
            integrate_eligible=integrate_eligible,
        )


def _blank_to_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
