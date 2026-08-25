from __future__ import annotations

import json
import os
import sys
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
            model=os.getenv("QWEN_MODEL", "qwen-plus").strip() or "qwen-plus",
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
                "description": "检索 GDC/TCGA 乳腺癌项目和临床、突变、表达或拷贝数文件。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "例如 TCGA-BRCA"},
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
                "description": "从 cBioPortal 获取乳腺癌患者/样本临床表、突变和离散 CNA，用于构建科研数据宽表。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "study_id": {"type": "string", "description": "例如 brca_metabric"},
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
                "description": "检索 ClinicalTrials.gov 乳腺癌临床试验、干预和结局。",
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
                        "query": {"type": "string", "description": "例如 breast cancer GSE25066"},
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
                            "description": "例如 HER2 positive breast cancer PIK3CA trastuzumab response",
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
                        "query": {"type": "string", "description": "乳腺癌、基因、药物和结局组合查询"},
                        "max_records": {"type": "integer", "minimum": 1, "maximum": 100},
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
            "任务": "把乳腺癌科研问题解析为严格 JSON",
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
                    "content": "你是乳腺癌科研数据规划器。请严格按照 JSON 输出并保持医学语义。",
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        try:
            payload = json.loads(message.get("content") or "{}")
            payload["task_id"] = task_id
            payload.setdefault("research_goal", question)
            payload.setdefault("disease", "Breast Cancer")
            payload.setdefault("required_data_types", ["clinical"])
            payload.setdefault("genes", [])
            payload.setdefault("variants", [])
            payload.setdefault("drugs", [])
            payload.setdefault("outcomes", [])
            payload.setdefault("target_fields", [])
            return ResearchSpec.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise QwenClientError("千问返回的科研任务 JSON 未通过 Schema 校验。") from exc

    def choose_tools(
        self,
        spec: ResearchSpec,
        *,
        max_sources: int,
        preferred_sources: list[str],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        instruction = {
            "任务": "为科研问题选择真实数据工具",
            "research_spec": spec.model_dump(mode="json"),
            "最多检索入口数": max_sources,
            "用户指定来源": preferred_sources,
            "选择原则": [
                "需要患者级科研宽表时优先 cBioPortal",
                "不知道具体 GSE 时先调用 search_geo_catalog 按关键词检索 GEO 目录",
                "文献里提到的 GSE/NCT 再用 search_geo 或 search_trials 拉取",
                "治疗响应表达队列可选择 GEO，且必须使用真实 accession",
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
                "缺患者主表或缺治疗响应时，先 search_geo_catalog 再 search_geo",
                "文献摘要里出现的 GSE 必须再调用 search_geo；出现的 NCT 可调用 search_trials",
                "缺同队列分子暴露时继续搜索同时含突变和响应的独立研究，禁止建议把不同研究的患者拼成一行",
                "不得虚构 accession、study_id 或 PMID",
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
                    "你是乳腺癌科研数据智能体。只能复述后续 JSON 中明确给出的统计事实。"
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
                        "你是医学科研问题设计助手。只生成可检索、可审计的乳腺癌科研问题，"
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
        try:
            response = self.client.post(
                f"{self.settings.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise QwenClientError(f"{self.settings.provider_label}请求超时。") from exc
        except httpx.RequestError as exc:
            raise QwenClientError(f"{self.settings.provider_label}网络连接失败：{type(exc).__name__}。") from exc
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
