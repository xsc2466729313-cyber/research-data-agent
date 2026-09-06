from __future__ import annotations

from backend.app.integration.schema_matcher_v3 import SchemaMatcherV3
from backend.app.v30.models import (
    FieldMapping,
    FieldMappingResult,
    SchemaMatchRequest,
    SchemaPack,
    SchemaPackRequest,
)
from backend.app.v30.schema_generator.service import ONCOLOGY_ALIASES, ONCOLOGY_PACK_ID, SchemaPackGenerator

_TASK_ALIASES = {
    "mjd": ("observation_time",),
    "obs_time": ("observation_time",),
    "mag": ("flux", "magnitude"),
    "magnitude": ("flux",),
}


class SchemaMatcherBridge:
    """Feed a SchemaPack target list into the existing SchemaMatcher. No algorithm changes."""

    def __init__(
        self,
        *,
        generator: SchemaPackGenerator | None = None,
        matcher: SchemaMatcherV3 | None = None,
    ) -> None:
        self.generator = generator or SchemaPackGenerator()
        self.matcher = matcher

    def map_fields(self, request: SchemaMatchRequest) -> FieldMappingResult:
        pack = self._load_pack(request.schema_pack_id)
        target_fields = [item.name for item in pack.fields]
        target_types = {item.name: item.data_type for item in pack.fields}
        target_descriptions = {item.name: item.field_description for item in pack.fields}
        risk = {item.name: item.risk_level for item in pack.fields}
        matcher = self.matcher or SchemaMatcherV3(aliases=self._aliases(pack))
        matches = matcher.match(
            request.source_fields,
            target_fields,
            source_types=request.source_types or None,
            target_types=target_types,
            target_descriptions=target_descriptions,
        )
        mappings = [
            FieldMapping(
                source_field=item.source_field,
                target_field=item.target_field,
                confidence=item.confidence,
                status=item.decision,
                risk_level=risk.get(item.target_field, "standard"),
            )
            for item in matches
        ]
        return FieldMappingResult(
            schema_pack_id=pack.schema_pack_id,
            domain=pack.domain,
            mappings=mappings,
            matcher_version=matcher.VERSION,
            row_count=0,
            generates_data=False,
            notice="字段映射只来自已有 SchemaMatcher 与 SchemaPack 目标清单，不是数据行，也未进入 Integrate。",
        )

    def _load_pack(self, schema_pack_id: str) -> SchemaPack:
        if schema_pack_id in ONCOLOGY_ALIASES:
            return self.generator.generate(SchemaPackRequest(domain="oncology", research_goal="HER2乳腺癌"))
        try:
            return self.generator.get(schema_pack_id)
        except KeyError:
            if schema_pack_id == ONCOLOGY_PACK_ID:
                return self.generator.generate(SchemaPackRequest(domain="oncology", research_goal="HER2乳腺癌"))
            raise

    @staticmethod
    def _aliases(pack: SchemaPack) -> dict[str, tuple[str, ...]]:
        merged = dict(SchemaMatcherV3._default_aliases())
        if pack.binding == "generated_task":
            merged.update(_TASK_ALIASES)
        return merged
