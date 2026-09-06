from __future__ import annotations

from hashlib import sha1
from pathlib import Path

import yaml

from backend.app.v30.models import SchemaPack, SchemaPackField, SchemaPackRequest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_INDEX_PATH = _REPO_ROOT / "configs" / "v30" / "schema_packs.yaml"
_CANONICAL_PATH = _REPO_ROOT / "configs" / "canonical_schema.yaml"

ONCOLOGY_PACK_ID = "oncology_canonical_v0.1"
ONCOLOGY_ALIASES = {"oncology_canonical", ONCOLOGY_PACK_ID}

HIGH_RISK_FIELDS = {
    "patient_id",
    "sample_id",
    "her2_status",
    "her2_assay",
    "her2_raw_value",
    "er_status",
    "pr_status",
    "response",
    "response_domain",
    "response_type",
    "mutation_status",
}

PROVENANCE_FIELDS = ("source_id", "raw_field", "raw_value")

_FROZEN_DESCRIPTIONS = {
    "study_id": "研究或队列标识",
    "patient_id": "患者标识；跨研究不得自动合并",
    "sample_id": "样本标识",
    "disease": "疾病名称",
    "subtype": "分子或临床亚型",
    "stage": "分期",
    "er_status": "ER 状态，取值受冻结医学规则约束",
    "pr_status": "PR 状态，取值受冻结医学规则约束",
    "her2_status": "HER2 状态；IHC 2+ 不得自动判为 Positive",
    "her2_assay": "HER2 检测方法",
    "her2_raw_value": "HER2 原始读数",
    "gene": "基因符号",
    "variant": "变异描述",
    "mutation_status": "突变状态",
    "drug": "药物",
    "treatment": "治疗方案",
    "response_domain": "响应域，须区分临床与临床前",
    "response_type": "响应指标类型",
    "response": "响应结果",
    "source_id": "来源标识",
    "raw_field": "原始字段名",
    "raw_value": "原始值",
    "confidence": "记录置信度",
}

_SN_FIELDS = (
    ("sn_id", "超新星或天体对象标识", "string", True, "standard"),
    ("observation_time", "观测时间", "string", True, "standard"),
    ("band", "测光波段", "string", True, "standard"),
    ("flux", "流量或测光值", "number", True, "standard"),
    ("redshift", "红移", "number", True, "standard"),
    ("source_id", "来源标识", "string", True, "provenance"),
    ("raw_field", "原始字段名", "string", True, "provenance"),
    ("raw_value", "原始值", "string", True, "provenance"),
)


class SchemaPackNotFoundError(KeyError):
    pass


class SchemaPackGenerator:
    """Build a field contract. Never writes data rows or edits the frozen schema file."""

    def __init__(self) -> None:
        self._packs: dict[str, SchemaPack] = {}

    def generate(self, request: SchemaPackRequest) -> SchemaPack:
        domain = request.domain.strip().casefold()
        if domain == "oncology" or self._is_oncology_task(request):
            pack = self._bind_oncology(request)
        elif domain == "astronomy" or self._is_supernova_task(request):
            pack = self._generate_supernova(request)
        else:
            pack = self._generate_generic(request)
        self._packs[pack.schema_pack_id] = pack
        for alias in ONCOLOGY_ALIASES:
            if pack.schema_pack_id == ONCOLOGY_PACK_ID:
                self._packs[alias] = pack
        return pack

    def get(self, schema_pack_id: str) -> SchemaPack:
        if schema_pack_id in self._packs:
            return self._packs[schema_pack_id]
        if schema_pack_id in ONCOLOGY_ALIASES:
            return self.generate(SchemaPackRequest(domain="oncology", research_goal="oncology canonical bind"))
        raise SchemaPackNotFoundError(schema_pack_id)

    def _bind_oncology(self, request: SchemaPackRequest) -> SchemaPack:
        raw = yaml.safe_load(_CANONICAL_PATH.read_text(encoding="utf-8")) or {}
        fields_raw = raw.get("fields") or {}
        fields = [self._frozen_field(name, spec, request.selected_sources) for name, spec in fields_raw.items()]
        return SchemaPack(
            schema_pack_id=ONCOLOGY_PACK_ID,
            domain="oncology",
            entity_type="patient",
            binding="frozen_canonical",
            status="BOUND",
            fields=fields,
            selected_sources=list(request.selected_sources),
            row_count=0,
            generates_data=False,
            canonical_schema_path="configs/canonical_schema.yaml",
            notice="医学任务绑定冻结 Canonical Schema，只读，不生成数据行，也不改写 HER2/response 规则。",
        )

    def _generate_supernova(self, request: SchemaPackRequest) -> SchemaPack:
        pack_id = request.contract_id or "task-astronomy-sn-ia"
        if not str(pack_id).startswith("task-"):
            pack_id = f"task-{pack_id}"
        fields = [
            SchemaPackField(
                name=name,
                field_description=description,
                data_type=data_type,
                required=required,
                source_requirements=list(request.selected_sources),
                risk_level=risk,
                frozen=False,
            )
            for name, description, data_type, required, risk in _SN_FIELDS
        ]
        self._assert_no_medical_names([item.name for item in fields])
        return SchemaPack(
            schema_pack_id=pack_id,
            domain="astronomy",
            entity_type="supernova_observation",
            binding="generated_task",
            status="DRAFT",
            fields=fields,
            selected_sources=list(request.selected_sources),
            row_count=0,
            generates_data=False,
            notice="通用任务级字段契约。含溯源三件套，不是观测数据，也未进入 Matcher。",
        )

    def _generate_generic(self, request: SchemaPackRequest) -> SchemaPack:
        names = [item.strip() for item in request.required_fields if item.strip()]
        self._assert_no_medical_names(names)
        fields = [
            SchemaPackField(
                name="record_id",
                field_description="任务级记录标识",
                data_type="string",
                required=True,
                source_requirements=list(request.selected_sources),
                risk_level="standard",
            )
        ]
        for name in names:
            if name in {"record_id", *PROVENANCE_FIELDS}:
                continue
            fields.append(
                SchemaPackField(
                    name=name,
                    field_description=f"任务字段 {name}",
                    data_type="string",
                    required=True,
                    source_requirements=list(request.selected_sources),
                    risk_level="standard",
                )
            )
        for name in PROVENANCE_FIELDS:
            fields.append(
                SchemaPackField(
                    name=name,
                    field_description=f"溯源字段 {name}",
                    data_type="string",
                    required=True,
                    source_requirements=list(request.selected_sources),
                    risk_level="provenance",
                )
            )
        digest = sha1(f"{request.domain}|{request.research_goal}|{request.contract_id}".encode("utf-8")).hexdigest()[:10]
        pack_id = request.contract_id or f"task-{request.domain}-{digest}"
        if not str(pack_id).startswith("task-"):
            pack_id = f"task-{pack_id}"
        return SchemaPack(
            schema_pack_id=pack_id,
            domain=request.domain,
            entity_type="record",
            binding="generated_task",
            status="DRAFT",
            fields=fields,
            selected_sources=list(request.selected_sources),
            row_count=0,
            generates_data=False,
            notice="通用任务级字段契约，不是数据。",
        )

    @staticmethod
    def _frozen_field(name: str, spec: dict, selected_sources: list[str]) -> SchemaPackField:
        risk = "high" if name in HIGH_RISK_FIELDS else "provenance" if name in PROVENANCE_FIELDS else "standard"
        sources = list(selected_sources)
        if risk == "high":
            sources = ["frozen_medical_rules", *sources]
        return SchemaPackField(
            name=name,
            field_description=_FROZEN_DESCRIPTIONS.get(name, f"冻结字段 {name}"),
            data_type=str(spec.get("type") or "string"),
            required=bool(spec.get("required")),
            source_requirements=sources,
            risk_level=risk,
            allowed=[str(item) for item in (spec.get("allowed") or [])],
            frozen=True,
        )

    @staticmethod
    def _is_oncology_task(request: SchemaPackRequest) -> bool:
        text = f"{request.research_goal} {request.topic}".casefold()
        return any(token in text for token in ("her2", "乳腺", "breast", "oncology", "癌"))

    @staticmethod
    def _is_supernova_task(request: SchemaPackRequest) -> bool:
        text = f"{request.research_goal} {request.topic} {' '.join(request.required_fields)}"
        folded = text.casefold()
        return any(token in folded or token in text for token in ("超新星", "supernova", "sn ia", "ia型", "redshift"))

    @staticmethod
    def _assert_no_medical_names(names: list[str]) -> None:
        overlap = HIGH_RISK_FIELDS.intersection(name.casefold() for name in names)
        if overlap:
            raise ValueError(f"generic schema pack cannot reuse medical high-risk fields: {sorted(overlap)}")


def index_points_to_frozen_schema() -> bool:
    payload = yaml.safe_load(_INDEX_PATH.read_text(encoding="utf-8")) or {}
    packs = payload.get("packs") or []
    return any(
        item.get("schema_pack_id") == ONCOLOGY_PACK_ID
        and str(item.get("canonical_schema_path") or "").replace("\\", "/").endswith("configs/canonical_schema.yaml")
        for item in packs
    )
