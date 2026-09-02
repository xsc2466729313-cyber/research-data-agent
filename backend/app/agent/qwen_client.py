from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from backend.app.models import ResearchSpec

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def parse_dotenv(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def apply_dotenv(
    values: dict[str, str],
    environ: MutableMapping[str, str],
    *,
    override: bool = False,
) -> None:
    for key, value in values.items():
        if override or not str(environ.get(key) or "").strip():
            environ[key] = value


def load_local_dotenv(
    environ: MutableMapping[str, str] | None = None,
    *,
    override: bool = False,
    path: Path | None = None,
) -> bool:
    """Load gitignored project-root .env into process env. Skipped under pytest."""
    if environ is None:
        if "pytest" in sys.modules:
            return False
        environ = os.environ
    dotenv_path = path or (_PROJECT_ROOT / ".env")
    if not dotenv_path.is_file():
        return False
    apply_dotenv(
        parse_dotenv(dotenv_path.read_text(encoding="utf-8")),
        environ,
        override=override,
    )
    return True


class QwenClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class QwenSettings:
    api_key: str | None
    base_url: str
    model: str
    workspace_id: str | None
    timeout_seconds: float = 120.0
    provider: str = "qwen"

    @classmethod
    def from_env(cls) -> "QwenSettings":
        load_local_dotenv()
        return cls(
            api_key=os.getenv("DASHSCOPE_API_KEY") or None,
            base_url=(
                os.getenv("QWEN_BASE_URL")
                or "https://dashscope.aliyuncs.com/compatible-mode/v1"
            ).rstrip("/"),
            model=os.getenv("QWEN_MODEL", "qwen3.8-max").strip() or "qwen3.8-max",
            workspace_id=os.getenv("QWEN_WORKSPACE_ID") or None,
            timeout_seconds=float(os.getenv("QWEN_TIMEOUT_SECONDS", "120")),
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url)

    def validate_base_url(self) -> None:
        parsed = urlparse(self.base_url)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https":
            raise QwenClientError(f"{self.provider_label}接口地址必须使用 HTTPS。")
        if self.provider == "qwen":
            allow_custom = os.getenv("QWEN_ALLOW_CUSTOM_BASE_URL") == "1"
            if not allow_custom and not (
                hostname == "dashscope.aliyuncs.com"
                or hostname.endswith(".maas.aliyuncs.com")
            ):
                raise QwenClientError(
                    "千问接口地址必须是阿里云百炼官方域名；如使用受信任代理，"
                    "需显式设置 QWEN_ALLOW_CUSTOM_BASE_URL=1。"
                )
        elif self.provider == "deepseek":
            if hostname != "api.deepseek.com" and not hostname.endswith(".deepseek.com"):
                raise QwenClientError("DeepSeek 接口地址必须是 DeepSeek 官方域名。")
        elif self.provider == "openai_compatible":
            if not hostname:
                raise QwenClientError("OpenAI 兼容接口地址无效。")
        else:
            raise QwenClientError(f"不支持的模型提供商：{self.provider}。")

    @property
    def provider_label(self) -> str:
        return {
            "qwen": "千问",
            "deepseek": "DeepSeek",
            "openai_compatible": "OpenAI 兼容模型",
        }.get(self.provider, self.provider)


class QwenClient:
    TOOL_DEFINITIONS: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "search_gdc",
                "description": "检索 GDC/TCGA 肿瘤项目和临床、突变、表达或拷贝数文件。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "GDC 项目 ID，例如 TCGA-BRCA、TCGA-PAAD 或 TCGA-GBM"},
                        "data_types": {"type": "array", "items": {"type": "string"}},
                        "max_files": {"type": "integer", "minimum": 1, "maximum": 20},
                    },
                    "required": ["project_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_geo",
                "description": "按真实 GSE accession 检索并下载 NCBI GEO Series Matrix，用于构建患者/样本表。若尚不知 accession，先调用 search_geo_catalog。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "accession": {"type": "string", "description": "例如 GSE25066"},
                        "max_files": {"type": "integer", "minimum": 1, "maximum": 20},
                    },
                    "required": ["accession"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_cbioportal",
                "description": "从 cBioPortal 获取肿瘤患者/样本临床表、突变和离散 CNA，用于构建科研数据宽表。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "study_id": {"type": "string", "description": "cBioPortal 研究 ID，例如 brca_metabric 或 paad_tcga_pan_can_atlas_2018"},
                        "gene_symbols": {"type": "array", "items": {"type": "string"}},
                        "max_records": {"type": "integer", "minimum": 10, "maximum": 10000},
                    },
                    "required": ["study_id", "gene_symbols"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_trials",
                "description": "检索 ClinicalTrials.gov 肿瘤临床试验、干预和结局。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "condition": {"type": "string"},
                        "query_terms": {"type": "string"},
                        "max_trials": {"type": "integer", "minimum": 1, "maximum": 10},
                    },
                    "required": ["condition"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_civic",
                "description": "检索 CIViC 中已接受的基因-变异-药物-疾病证据；不能当作患者队列表。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "disease_name": {"type": "string"},
                        "molecular_profile_name": {"type": "string"},
                        "therapy_name": {"type": "string"},
                        "max_items": {"type": "integer", "minimum": 1, "maximum": 10},
                    },
                    "required": ["disease_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_biosample",
                "description": "检索 NCBI BioSample 样本元数据，用于核对组织、物种和样本属性；结果不直接填入患者主表。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "例如 lung adenocarcinoma EGFR"},
                        "max_records": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_geo_catalog",
                "description": "按关键词检索 NCBI GEO 目录，发现真实 GSE accession；发现后必须再调用 search_geo 下载 Series Matrix，不能把目录摘要当患者表。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "例如 lung adenocarcinoma EGFR treatment response",
                        },
                        "max_records": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_europe_pmc",
                "description": "检索 Europe PMC 文献和摘要，用于发现研究、结局定义和证据线索；结果不作为患者级事实。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "癌种、基因、药物和结局组合查询"},
                        "max_records": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_depmap",
                "description": "检索 DepMap 肿瘤细胞系药敏（AUC/IC50）。结果的 response_domain 必须是 preclinical_cell_line，不能当作患者疗效。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "例如 lung adenocarcinoma cell line osimertinib AUC"},
                        "drug": {"type": "string"},
                        "max_records": {"type": "integer", "minimum": 1, "maximum": 200},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "extract_paper_assets",
                "description": "从 Europe PMC 开放全文 XML 提取表格单元格与图注。不从图像素读数。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "pmcid": {"type": "string", "description": "例如 PMC1234567"},
                        "max_records": {"type": "integer", "minimum": 1, "maximum": 20},
                    },
                    "required": ["query"],
                },
            },
        },
    ]

    def __init__(
        self,
        settings: QwenSettings | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or QwenSettings.from_env()
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=self.settings.timeout_seconds,
            follow_redirects=True,
        )

    @property
    def available(self) -> bool:
        return self.settings.configured

    def test_connection(self) -> None:
        message = self._chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是连接测试助手，只回复 CONNECTION_OK。",
                },
                    {"role": "user", "content": f"测试{self.settings.provider_label} API 连接。"},
            ],
        )
        if not str(message.get("content") or "").strip():
            raise QwenClientError("千问连接成功，但未返回可识别内容。")

    def extract_research_spec(self, question: str, task_id: str) -> ResearchSpec:
        prompt = {
            "任务": "把肿瘤科研问题解析为严格 JSON",
            "科研问题": question,
            "JSON字段": {
                "research_goal": "原始目标",
                "disease": "疾病英文标准名",
                "subtype": "亚型或null",
                "genes": ["HUGO基因符号"],
                "variants": ["变异"],
                "drugs": ["药物通用名"],
                "outcomes": ["研究结局"],
                "required_data_types": ["clinical/mutation/expression/treatment_response/evidence"],
                "target_fields": ["希望出现在科研数据集中的字段"],
            },
            "约束": [
                "只输出 JSON 对象",
                "不得虚构患者、样本或结果",
                "HER2 与 ERBB2 检测维度不得混同",
                "字段值未知时使用空数组或 null",
            ],
        }
        message = self._chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是肿瘤科研数据规划器。请严格按照 JSON 输出并保持癌种、队列和医学语义。",
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        try:
            payload = json.loads(message.get("content") or "{}")
            payload["task_id"] = task_id
            payload.setdefault("research_goal", question)
            payload.setdefault("disease", "Cancer")
            payload.setdefault("required_data_types", ["clinical"])
            payload.setdefault("genes", [])
            payload.setdefault("variants", [])
            payload.setdefault("drugs", [])
            payload.setdefault("outcomes", [])
            payload.setdefault("target_fields", [])
            return ResearchSpec.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise QwenClientError("千问返回的科研任务 JSON 未通过 Schema 校验。") from exc

    def normalize_research_field(
        self,
        *,
        source_dataset: str,
        raw_field: str,
        raw_value: str,
        allowed_fields: list[str],
    ) -> dict[str, Any]:
        """Map one observed research field without exposing its gold label."""
        prompt = {
            "任务": "将一条乳腺癌科研数据原始字段映射为冻结 CanonicalRecord 字段",
            "来源数据集": source_dataset,
            "原始字段": raw_field,
            "原始值": raw_value,
            "允许的规范字段": allowed_fields,
            "输出字段": {
                "canonical_values": "对象；列出该原始字段能支持的全部规范字段和值，键只能来自允许字段",
                "confidence": "0 到 1 之间的小数",
                "needs_review": "高风险或语义不确定时为 true",
                "rationale": "不超过 80 字的依据",
            },
            "约束": [
                "不得猜测不存在的患者、样本、治疗响应或来源事实",
                "必须保留 raw_field 与 raw_value，不改写原始值",
                "HER2 IHC 2+ 只能是 Equivocal/REVIEW，不能是 Positive",
                "ERBB2 CNA amplification 不得映射为 HER2 IHC Positive",
                "IC50/AUC 属于 preclinical_cell_line，不能写成患者 pCR",
                "一个原始字段可同时产生多个规范字段，例如 HER2 IHC 3+ 应同时给出 her2_status、her2_assay、her2_raw_value",
                "来源编号字段应带来源命名空间，例如 GSE 为 geo:、NCT 为 nct:、TCGA 为 gdc:",
                "只输出 JSON 对象",
            ],
        }
        message = self._chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是乳腺癌科研数据字段治理器。只做字段语义映射，不编造数据。",
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        try:
            payload = json.loads(message.get("content") or "{}")
        except (json.JSONDecodeError, TypeError) as exc:
            raise QwenClientError("千问字段治理结果不是有效 JSON。") from exc
        if not isinstance(payload, dict):
            raise QwenClientError("千问字段治理结果不是 JSON 对象。")
        return payload

    def diagnose_research_error(self, *, original_record: dict[str, Any]) -> dict[str, Any]:
        """Detect one record-level quality issue without exposing benchmark labels."""
        prompt = {
            "任务": "诊断一条乳腺癌科研记录是否存在数据质量或医学语义错误",
            "原始记录": original_record,
            "输出字段": {
                "detected": "是否发现错误",
                "error_type": "错误类型；无错误时为 null",
                "candidate_repair": "候选修复对象，例如 {field, value}；不能确定时为 null",
                "confidence": "0 到 1 之间的小数",
                "needs_review": "需要人工复核时为 true",
                "rationale": "不超过 100 字的依据",
            },
            "可用错误类型": [
                "her2_assay_error",
                "patient_sample_conflict",
                "schema_mapping_error",
                "provenance_missing",
                "gene_alias",
                "drug_alias",
                "duplicate",
                "missing",
                "unit",
                "typo",
            ],
            "约束": [
                "只能根据原始记录判断，不能假设有隐藏标签或干净表",
                "HER2 IHC 2+ 不得改为 Positive",
                "ERBB2 CNA 不等于 HER2 IHC positive",
                "低置信度或跨研究患者关联必须 unresolved 并 needs_review=true",
                "IC50/AUC 与患者 pCR 必须区分 response_domain",
                "缺 source_id/raw_field/raw_value 时只能报告问题，不能补造值",
                "只输出 JSON 对象",
            ],
        }
        message = self._chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是乳腺癌科研数据质量审查器。优先发现风险，不擅自改写高风险事实。",
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        try:
            payload = json.loads(message.get("content") or "{}")
        except (json.JSONDecodeError, TypeError) as exc:
            raise QwenClientError("千问错误诊断结果不是有效 JSON。") from exc
        if not isinstance(payload, dict):
            raise QwenClientError("千问错误诊断结果不是 JSON 对象。")
        return payload

    def label_pico_batch(
        self, items: list[dict[str, Any]], *, element: str
    ) -> dict[str, list[int]]:
        """Label PICO tokens in a bounded batch without exposing test labels."""
        message = self._chat_json(
            system=(
                "你是医学文献 PICO span 标注器。当前只标注一个指定元素，"
                "只依据文档 token，不猜测隐藏标注。为减少输出，只返回属于该元素的 token 索引。"
            ),
            payload={
                "任务": "识别每个文档中属于当前 PICO 元素的 token",
                "当前元素": element,
                "items": items,
                "输出": "JSON 对象 positive_indices，键为 item_id，值为正类 token 的 0-based 索引数组",
                "约束": [
                    "不得合并、删除或重排 tokens",
                    "只能输出 positive_indices 一个对象",
                    "每个 item_id 必须都有结果",
                    "索引必须在对应 tokens 范围内且不得重复",
                ],
            },
        )
        positive_indices = message.get("positive_indices")
        if not isinstance(positive_indices, dict):
            raise QwenClientError("千问 PICO 结果缺少 positive_indices 对象。")
        output: dict[str, list[int]] = {}
        expected = {str(item["item_id"]): len(item.get("tokens") or []) for item in items}
        for item_id, size in expected.items():
            values = positive_indices.get(item_id)
            if not isinstance(values, list) or any(not isinstance(value, int) or not 0 <= value < size for value in values):
                raise QwenClientError(f"千问 PICO positive_indices 无效：{item_id}")
            if len(set(values)) != len(values):
                raise QwenClientError(f"千问 PICO positive_indices 重复：{item_id}")
            labels = [0] * size
            for index in values:
                labels[index] = 1
            output[item_id] = labels
        return output

    def rewrite_retrieval_batch(self, items: list[dict[str, Any]]) -> dict[str, str]:
        """Rewrite retrieval queries without receiving corpus relevance labels."""
        message = self._chat_json(
            system=(
                "你是科学文献检索查询改写器。保持原问题的事实和否定关系，"
                "为词法检索生成一个简洁英文查询。不得假设任何文档相关性。"
            ),
            payload={
                "任务": "为每个查询生成可用于 BM25 的查询改写",
                "items": items,
                "输出": "JSON 对象 rewrites，键为 item_id，值为查询字符串",
                "约束": [
                    "不得生成答案、文档编号或相关性判断",
                    "保留原查询中的关键实体、否定和比较关系",
                    "每个 item_id 必须都有结果",
                ],
            },
        )
        rewrites = message.get("rewrites")
        if not isinstance(rewrites, dict):
            raise QwenClientError("千问检索改写结果缺少 rewrites 对象。")
        output: dict[str, str] = {}
        for item in items:
            item_id = str(item["item_id"])
            value = rewrites.get(item_id)
            if not isinstance(value, str) or not value.strip():
                raise QwenClientError(f"千问检索改写为空：{item_id}")
            output[item_id] = value.strip()
        return output

    def clean_table_batch(
        self,
        *,
        columns: list[str],
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Propose dirty-table repairs from the dirty table only."""
        message = self._chat_json(
            system=(
                "你是公开数据集错误清洗器。只依据给出的脏表和表内重复模式识别高置信异常；"
                "不能访问清洁参考表，不确定就不修改。"
            ),
            payload={
                "任务": "提出脏表中可由表内证据唯一确认的单元格修复",
                "columns": columns,
                "rows": rows,
                "输出": "JSON 数组 repairs，每项为 {row_index, column, value, reason}",
                "约束": [
                    "row_index 必须是输入行的 index",
                    "column 必须来自 columns",
                    "只提出能由重复值、明显格式模式或跨列约束确认的修复",
                    "不要猜测缺失的真实值，不要整行重写，不要改列名",
                    "value 必须是字符串",
                ],
            },
        )
        repairs = message.get("repairs")
        if not isinstance(repairs, list):
            raise QwenClientError("千问清洗结果不是 repairs 数组。")
        allowed = set(columns)
        output: list[dict[str, Any]] = []
        for item in repairs:
            if not isinstance(item, dict):
                raise QwenClientError("千问清洗 repair 项不是对象。")
            row_index = item.get("row_index")
            column = item.get("column")
            value = item.get("value")
            if not isinstance(row_index, int) or not 0 <= row_index < len(rows):
                raise QwenClientError("千问清洗 row_index 无效。")
            if not isinstance(column, str) or column not in allowed:
                raise QwenClientError("千问清洗 column 不在输入列中。")
            if not isinstance(value, str):
                raise QwenClientError("千问清洗 value 必须是字符串。")
            output.append({
                "row_index": row_index,
                "column": column,
                "value": value,
                "reason": str(item.get("reason") or "")[:200],
            })
        return output

    def match_schema_batch(self, items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Align public-table columns from names and bounded value profiles only."""
        message = self._chat_json(
            system=(
                "你是公开表格字段匹配专家。对每个任务判断 source 列和 target 列是否表达同一字段。"
                "只依据输入列名、有限样例值和表名，不得猜测或使用隐藏标签。每个 source 最多选择一个 target，"
                "不确定时不要强行匹配。缩写、连写、单位和同义词要结合值的形态判断。"
            ),
            payload={
                "任务": "批量完成通用 schema matching",
                "items": items,
                "输出": {
                    "matches": {
                        "每个item_id对应数组": [
                            {"source_column": "原列名", "target_column": "目标列名", "confidence": 0.0, "reason": "简短依据"}
                        ]
                    }
                },
                "约束": [
                    "只能选择输入中存在的列名",
                    "不要输出测试集真值，不要根据列顺序臆测",
                    "confidence 必须是 0 到 1 的数；低于 0.60 的候选不要输出",
                    "同一个 target_column 不得被多个 source_column 使用",
                    "只输出 JSON 对象",
                ],
            },
        )
        matches = message.get("matches")
        if not isinstance(matches, dict):
            raise QwenClientError("千问字段匹配结果缺少 matches 对象。")
        output: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            item_id = str(item["item_id"])
            raw = matches.get(item_id, [])
            if not isinstance(raw, list):
                raise QwenClientError(f"千问字段匹配结果不是数组：{item_id}")
            source_columns = set(map(str, item.get("source_columns", [])))
            target_columns = set(map(str, item.get("target_columns", [])))
            seen_sources: set[str] = set()
            seen_targets: set[str] = set()
            valid: list[dict[str, Any]] = []
            for candidate in raw:
                if not isinstance(candidate, dict):
                    continue
                source = str(candidate.get("source_column") or "")
                target = str(candidate.get("target_column") or "")
                confidence = candidate.get("confidence")
                if source not in source_columns or target not in target_columns:
                    continue
                if source in seen_sources or target in seen_targets:
                    continue
                if not isinstance(confidence, (int, float)):
                    continue
                confidence = max(0.0, min(1.0, float(confidence)))
                if confidence < 0.60:
                    continue
                seen_sources.add(source)
                seen_targets.add(target)
                valid.append({
                    "source_column": source,
                    "target_column": target,
                    "confidence": confidence,
                    "reason": str(candidate.get("reason") or "")[:240],
                })
            output[item_id] = valid
        return output

    def match_entity_batch(
        self,
        items: list[dict[str, Any]],
        *,
        training_examples: list[dict[str, Any]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Judge public candidate record pairs without seeing test labels."""
        message = self._chat_json(
            system=(
                "你是公开实体匹配专家。判断每个 left/right 记录是否指向同一个现实实体。"
                "综合名称、作者/品牌/地址/电话/型号等字段，容忍大小写、标点、缩写、词序和轻微拼写差异；"
                "但不要因为单个通用词或价格相近就匹配。输出 match=true/false，无法确定时按 false，"
                "并给出 0 到 1 的置信度。"
            ),
            payload={
                "任务": "批量完成通用 entity matching",
                "items": items,
                "training_examples": training_examples or [],
                "输出": {
                    "decisions": {
                        "每个pair_id对应对象": {"match": False, "confidence": 0.0, "reason": "简短依据"}
                    }
                },
                "约束": [
                    "只根据输入记录判断，不使用隐藏标签或外部搜索",
                    "match 必须是布尔值，confidence 必须在 0 到 1 之间",
                    "没有足够证据时 match=false；不要为了提高召回猜测",
                    "只输出 JSON 对象",
                ],
            },
        )
        decisions = message.get("decisions")
        if not isinstance(decisions, dict):
            raise QwenClientError("千问实体匹配结果缺少 decisions 对象。")
        output: dict[str, dict[str, Any]] = {}
        for item in items:
            pair_id = str(item["pair_id"])
            decision = decisions.get(pair_id, {})
            if not isinstance(decision, dict):
                raise QwenClientError(f"千问实体匹配结果不是对象：{pair_id}")
            confidence = decision.get("confidence", 0.0)
            if not isinstance(confidence, (int, float)):
                confidence = 0.0
            output[pair_id] = {
                "match": bool(decision.get("match", False)),
                "confidence": max(0.0, min(1.0, float(confidence))),
                "reason": str(decision.get("reason") or "")[:240],
            }
        return output

    def _chat_json(self, *, system: str, payload: dict[str, Any]) -> dict[str, Any]:
        message = self._chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        try:
            value = json.loads(message.get("content") or "{}")
        except (json.JSONDecodeError, TypeError) as exc:
            raise QwenClientError("千问批量结果不是有效 JSON。") from exc
        if not isinstance(value, dict):
            raise QwenClientError("千问批量结果不是 JSON 对象。")
        return value

    def choose_tools(
        self,
        spec: ResearchSpec,
        *,
        max_sources: int,
        preferred_sources: list[str],
        focus_accessions: list[str] | None = None,
        focus_tools: list[str] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        focus = [str(item).strip() for item in (focus_accessions or []) if str(item).strip()]
        instruction = {
            "任务": "为科研问题选择真实数据工具",
            "research_spec": spec.model_dump(mode="json"),
            "最多检索入口数": max_sources,
            "用户指定来源": preferred_sources,
            "必须优先拉取的队列": focus,
            "必须优先调用的工具": list(focus_tools or []),
            "选择原则": [
                "若问题要病理完全缓解 pCR / 新辅助治疗响应，必须调用 search_geo，accession 用 GSE25066、GSE76360 或 GSE50948；禁止只用 METABRIC/TCGA 生存队列交差",
                "METABRIC 的 OS/RFS 不能当作患者 pCR；细胞系 AUC/IC50 不能当作患者 pCR",
                "缺 HER2 临床状态时，从 GEO 样本特征或 cBioPortal HER2_STATUS/HER2_IHC 对齐 her2_status；IHC 2+ 不得写成 Positive",
                "需要患者级科研宽表且本题要生存结局时再优先 cBioPortal",
                "不知道具体 GSE 时先调用 search_geo_catalog 按关键词检索 GEO 目录",
                "文献里提到的 GSE/NCT 再用 search_geo 或 search_trials 拉取",
                "TCGA 临床或组学文件选择 GDC",
                "临床试验关系选择 ClinicalTrials.gov",
                "知识证据选择 CIViC，不能替代患者队列",
                "样本属性不完整时可检索 NCBI BioSample，但只能作为样本元数据核验层",
                "需要研究语境或结局定义时可检索 Europe PMC，但不能把摘要当患者数据",
                "可以为同一工具选择多个真实研究入口，例如多个 GSE accession、cBioPortal study_id 或 GDC project_id",
                "不同研究入口只能作为独立来源审计和候选证据，不能按相同字符串患者编号自动合并",
                "优先覆盖问题所需的样本字段、患者临床字段、分子字段和研究结局；不要为凑数量调用不相关来源",
                "必须调用至少一个工具，不得虚构 accession、study_id 或 project_id",
            ],
        }
        message = self._chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是科研数据智能体的工具规划器。根据问题自主选择相关公开数据库和多个研究入口，遵守入口预算和来源隔离规则。",
                },
                {"role": "user", "content": json.dumps(instruction, ensure_ascii=False)},
            ],
            tools=self.TOOL_DEFINITIONS,
            tool_choice="auto",
            parallel_tool_calls=True,
        )
        calls = message.get("tool_calls") or []
        message = dict(message)
        message["tool_calls"] = calls[:max_sources]
        normalized: list[dict[str, Any]] = []
        for index, call in enumerate(calls[:max_sources]):
            function = call.get("function") or {}
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError as exc:
                raise QwenClientError("千问工具参数不是有效 JSON。") from exc
            normalized.append(
                {
                    "id": call.get("id") or f"qwen-call-{index + 1}",
                    "name": function.get("name"),
                    "arguments": arguments,
                }
            )
        return message, normalized

    def plan_next_tools(
        self,
        spec: ResearchSpec,
        observation: dict[str, Any],
        *,
        max_calls: int = 4,
    ) -> list[dict[str, Any]]:
        instruction = {
            "任务": "根据当前观察继续检索，直到做出可用科研数据包或确认公开数据不足",
            "research_spec": spec.model_dump(mode="json"),
            "观察": observation,
            "本轮最多调用": max_calls,
            "选择原则": [
                "像独立研究员一样换查询词、换数据库、换研究入口，不要重复已经尝试过的完全相同调用",
                "缺 pCR / 治疗响应、或当前是生存队列时，必须 search_geo：GSE25066、GSE76360、GSE50948，禁止再用 METABRIC 生存表空转",
                "缺 HER2 状态时继续拉带 her2_status / HER2 IHC 的临床或 GEO 特征，IHC 2+ 不得写成 Positive",
                "缺患者主表或缺治疗响应时，先 search_geo_catalog 再 search_geo",
                "文献摘要里出现的 GSE 必须再调用 search_geo；出现的 NCT 可调用 search_trials",
                "缺同队列分子暴露时继续搜索同时含突变和响应的独立研究，禁止建议把不同研究的患者拼成一行",
                "不得虚构 accession、study_id 或 PMID",
                "细胞系/AUC/IC50/药敏题调用 search_depmap，response_domain 只能是 preclinical_cell_line，不得当患者 pCR",
                "试验或 NCT 题调用 search_trials，已知 NCT01042379 时应带 nct_id",
                "证据/论文表格题调用 extract_paper_assets，只抽 HTML/JATS 表和图注，禁止从图像素读数",
                "如果没有尚未尝试且能缩小缺口的检索，返回空 tool_calls",
            ],
        }
        message = self._chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是科研数据智能体的下一轮规划器。根据观察自主决定下一步公开数据库调用。"
                        "质量门只用于防止空转，不能用来停止尚未尝试的合法检索。"
                    ),
                },
                {"role": "user", "content": json.dumps(instruction, ensure_ascii=False)},
            ],
            tools=self.TOOL_DEFINITIONS,
            tool_choice="auto",
            parallel_tool_calls=True,
        )
        calls = message.get("tool_calls") or []
        normalized: list[dict[str, Any]] = []
        for index, call in enumerate(calls[:max_calls]):
            function = call.get("function") or {}
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError as exc:
                raise QwenClientError("千问下一轮工具参数不是有效 JSON。") from exc
            name = function.get("name")
            if not name:
                continue
            normalized.append(
                {
                    "id": call.get("id") or f"qwen-next-{index + 1}",
                    "name": name,
                    "arguments": arguments,
                }
            )
        return normalized

    def summarize(
        self,
        question: str,
        spec: ResearchSpec,
        tool_message: dict[str, Any],
        tool_summaries: list[dict[str, Any]],
        dataset_profile: dict[str, Any],
        readiness: dict[str, Any],
    ) -> str:
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "你是肿瘤科研数据智能体。只能复述后续 JSON 中明确给出的统计事实。"
                    "禁止自行声称患者均为某亚型、具有某治疗方案或某突变类型；禁止把工具的原始记录数"
                    "称为患者数。不得把相关性描述成因果关系，不得生成患者治疗建议。"
                    "请输出 JSON 对象，且只包含 summary 一个字符串字段。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "科研问题": question,
                        "任务结构": spec.model_dump(mode="json"),
                        "要求": "先通过工具获取真实数据，再给出结论。",
                    },
                    ensure_ascii=False,
                ),
            },
            tool_message,
        ]
        for summary in tool_summaries:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": summary["call_id"],
                    "content": json.dumps(summary, ensure_ascii=False),
                }
            )
        messages.append(
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "已验证的数据集统计": dataset_profile,
                        "可科研性报告": readiness,
                        "要求": (
                            "严格依据这些 JSON 事实，用中文给出数据层面的总结；不得补充 JSON 中不存在的队列事实。"
                            "除研究编号、基因符号和必要字段代码外，疾病、亚型、药物、结局、数据类型和枚举值均使用中文。"
                            "不要使用‘建模’一词，统一称为‘科研数据’或‘科研分析’。"
                        ),
                    },
                    ensure_ascii=False,
                ),
            }
        )
        final = self._chat(
            messages=messages,
            response_format={"type": "json_object"},
        )
        try:
            content = json.loads(final.get("content") or "{}")
            summary = str(content.get("summary") or "").strip()
        except (json.JSONDecodeError, TypeError) as exc:
            raise QwenClientError("千问总结不是有效 JSON。") from exc
        if not summary:
            raise QwenClientError("千问未返回数据总结。")
        return summary

    def generate_research_questions(self, seed_question: str, count: int) -> list[str]:
        """Ask Qwen for a bounded set of research questions without fabricating data."""
        message = self._chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是医学科研问题设计助手。只生成与种子问题同癌种、可检索、可审计的肿瘤科研问题，"
                        "不得生成患者事实、结果或治疗建议。请严格输出 JSON。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "种子问题": seed_question,
                            "数量": count,
                            "输出格式": {"questions": ["中文科研问题"]},
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        try:
            payload = json.loads(message.get("content") or "{}")
            questions = [
                str(item).strip()
                for item in payload.get("questions", [])
                if str(item).strip()
            ][:count]
        except (json.JSONDecodeError, TypeError) as exc:
            raise QwenClientError("千问返回的问题列表不是有效 JSON。") from exc
        if not questions:
            raise QwenClientError("千问未返回可用科研问题。")
        return questions

    def _chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        parallel_tool_calls: bool | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.settings.api_key:
            raise QwenClientError(f"未配置{self.settings.provider_label} API Key。")
        self.settings.validate_base_url()
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": 0.1,
            "enable_thinking": False,
        }
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if parallel_tool_calls is not None:
            payload["parallel_tool_calls"] = parallel_tool_calls
        if response_format is not None:
            payload["response_format"] = response_format
        response = None
        for attempt in range(3):
            try:
                response = self.client.post(
                    f"{self.settings.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.settings.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                break
            except httpx.TimeoutException as exc:
                if attempt == 2:
                    raise QwenClientError(f"{self.settings.provider_label}请求超时。") from exc
            except httpx.RequestError as exc:
                if attempt == 2:
                    raise QwenClientError(f"{self.settings.provider_label}网络连接失败：{type(exc).__name__}。") from exc
            time.sleep(1.5 * (attempt + 1))
        assert response is not None
        if response.status_code >= 400:
            try:
                error = response.json()
                message = error.get("message") or (error.get("error") or {}).get("message")
                code = error.get("code") or (error.get("error") or {}).get("code")
            except ValueError:
                message, code = None, None
            raise QwenClientError(
                f"{self.settings.provider_label}接口返回 HTTP {response.status_code}"
                + (f"（{code}）" if code else "")
                + (f"：{message}" if message else "。")
            )
        try:
            body = response.json()
            return body["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise QwenClientError(f"{self.settings.provider_label}返回了无法解析的响应。") from exc

    def close(self) -> None:
        if self._owns_client:
            self.client.close()
