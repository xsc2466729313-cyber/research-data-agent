from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from backend.app.models import ResearchSpec


class QwenClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class QwenSettings:
    api_key: str | None
    base_url: str
    model: str
    workspace_id: str | None
    timeout_seconds: float = 120.0

    @classmethod
    def from_env(cls) -> "QwenSettings":
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
        allow_custom = os.getenv("QWEN_ALLOW_CUSTOM_BASE_URL") == "1"
        if parsed.scheme != "https":
            raise QwenClientError("千问接口地址必须使用 HTTPS。")
        if not allow_custom and not (
            hostname == "dashscope.aliyuncs.com"
            or hostname.endswith(".maas.aliyuncs.com")
        ):
            raise QwenClientError(
                "千问接口地址必须是阿里云百炼官方域名；如使用受信任代理，"
                "需显式设置 QWEN_ALLOW_CUSTOM_BASE_URL=1。"
            )


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
                "description": "检索 NCBI GEO 表达谱及治疗响应队列资源；需要真实 GSE accession。",
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
                {"role": "user", "content": "测试千问 API 连接。"},
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
            "最多工具数": max_sources,
            "用户指定来源": preferred_sources,
            "选择原则": [
                "需要患者级科研宽表时优先 cBioPortal",
                "治疗响应表达队列可选择 GEO",
                "TCGA 临床或组学文件选择 GDC",
                "临床试验关系选择 ClinicalTrials.gov",
                "知识证据选择 CIViC，不能替代患者队列",
                "必须调用至少一个工具，不得虚构 accession",
            ],
        }
        message = self._chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是科研数据智能体的工具规划器。根据问题调用最少且必要的真实数据库工具。",
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
            raise QwenClientError("未配置 DASHSCOPE_API_KEY。")
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
            raise QwenClientError("千问请求超时。") from exc
        except httpx.RequestError as exc:
            raise QwenClientError(f"千问网络连接失败：{type(exc).__name__}。") from exc
        if response.status_code >= 400:
            try:
                error = response.json()
                message = error.get("message") or (error.get("error") or {}).get("message")
                code = error.get("code") or (error.get("error") or {}).get("code")
            except ValueError:
                message, code = None, None
            raise QwenClientError(
                f"千问接口返回 HTTP {response.status_code}"
                + (f"（{code}）" if code else "")
                + (f"：{message}" if message else "。")
            )
        try:
            body = response.json()
            return body["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise QwenClientError("千问返回了无法解析的响应。") from exc

    def close(self) -> None:
        if self._owns_client:
            self.client.close()
