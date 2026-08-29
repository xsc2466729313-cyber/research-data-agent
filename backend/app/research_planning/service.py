from __future__ import annotations

import threading
from datetime import datetime, timezone

from backend.app.literature import LiteratureAgent, LiteratureScan, LiteratureScanRequest
from backend.app.rag import (
    EvidenceQueryRequest,
    EvidenceQueryResponse,
    PlanningRAGIndexManager,
    RAGEvaluationRequest,
    RAGEvaluationResult,
    RAGIndexReport,
    RAGIndexRequest,
    ScientificGraphSnapshot,
)
from backend.app.research_planning.formulation_agent import ResearchFormulationAgent
from backend.app.research_planning.intent_agent import ResearchIntentAgent
from backend.app.research_planning.models import (
    LiteratureScanResponse,
    QuestionCandidate,
    QuestionCandidateList,
    QuestionSelectionRequest,
    ResearchContract,
    ResearchTopic,
    TopicCreateRequest,
)
from backend.app.research_planning.research_contract import ResearchContractBuilder
from backend.app.source_broker.models import SourcePlanningResult, SourcePlanRequest
from backend.app.source_broker.service import SourceBroker


class ResearchPlanningNotFoundError(LookupError):
    pass


class ResearchPlanningService:
    """Phase 1/2 orchestration from broad topic to an evidence-backed contract and RAG index."""

    def __init__(
        self,
        *,
        intent_agent: ResearchIntentAgent | None = None,
        literature_agent: LiteratureAgent | None = None,
        formulation_agent: ResearchFormulationAgent | None = None,
        contract_builder: ResearchContractBuilder | None = None,
        rag_index: PlanningRAGIndexManager | None = None,
        source_broker: SourceBroker | None = None,
    ) -> None:
        self.intent_agent = intent_agent or ResearchIntentAgent()
        self.literature_agent = literature_agent or LiteratureAgent()
        self.formulation_agent = formulation_agent or ResearchFormulationAgent()
        self.contract_builder = contract_builder or ResearchContractBuilder()
        self.rag_index = rag_index or PlanningRAGIndexManager()
        self.source_broker = source_broker or SourceBroker()
        self._topics: dict[str, ResearchTopic] = {}
        self._scans: dict[str, LiteratureScan] = {}
        self._candidates: dict[str, list[QuestionCandidate]] = {}
        self._contracts: dict[str, ResearchContract] = {}
        self._source_plans: dict[str, SourcePlanningResult] = {}
        self._candidate_topics: dict[str, str] = {}
        self._lock = threading.Lock()

    def create_topic(self, request: TopicCreateRequest) -> ResearchTopic:
        topic = self.intent_agent.understand(request)
        with self._lock:
            self._topics[topic.topic_id] = topic
        return topic

    def scan_literature(
        self,
        topic_id: str,
        request: LiteratureScanRequest,
    ) -> LiteratureScanResponse:
        topic = self._topic(topic_id)
        query = request.query or self._literature_query(topic)
        scan = self.literature_agent.scan(
            topic_id=topic_id,
            query=query,
            max_records=request.max_records,
        )
        candidates = self.formulation_agent.formulate(topic, scan.papers)
        self.rag_index.index_topic(topic, scan, candidates)
        with self._lock:
            self._scans[topic_id] = scan
            self._candidates[topic_id] = candidates
            for candidate in candidates:
                self._candidate_topics[candidate.candidate_id] = topic_id
        return LiteratureScanResponse(scan=scan, candidate_count=len(candidates))

    def question_candidates(self, topic_id: str) -> QuestionCandidateList:
        self._topic(topic_id)
        with self._lock:
            candidates = list(self._candidates.get(topic_id, []))
            scan = self._scans.get(topic_id)
        warning = None
        if scan is None:
            warning = "尚未执行 literature-scan。"
        elif not getattr(scan, "papers", []):
            warning = "未获得论文记录；候选问题为确定性草案，必须补充 Evidence 后再执行。"
        return QuestionCandidateList(
            topic_id=topic_id,
            candidates=candidates,
            literature_warning=warning,
        )

    def select_question(
        self,
        candidate_id: str,
        request: QuestionSelectionRequest,
    ) -> ResearchContract:
        with self._lock:
            topic_id = self._candidate_topics.get(candidate_id)
        if topic_id is None:
            raise ResearchPlanningNotFoundError("候选科研问题不存在或服务已重启。")
        topic = self._topic(topic_id)
        with self._lock:
            candidates = list(self._candidates.get(topic_id, []))
            scan = self._scans.get(topic_id)
        candidate = next((item for item in candidates if item.candidate_id == candidate_id), None)
        if candidate is None:
            raise ResearchPlanningNotFoundError("候选科研问题不存在或服务已重启。")
        updates = {
            key: value
            for key, value in {
                "question": request.question_override,
                "population": request.population_override,
                "exposure": request.exposure_override,
                "outcome": request.outcome_override,
            }.items()
            if value is not None
        }
        if updates:
            updates["literature_evidence"] = []
            updates["recommendation_reason"] = "用户修改了候选问题；原论文 Evidence 不自动继承，需要重新核验。"
            candidate = candidate.model_copy(update=updates)
        papers = list(getattr(scan, "papers", []) or [])
        contract = self.contract_builder.build(topic, candidate, papers)
        contract = contract.model_copy(update={"lifecycle_status": "USER_CONFIRMED"})
        self.rag_index.index_contract(contract)
        with self._lock:
            self._contracts[contract.contract_id] = contract
        return contract

    def freeze_contract(self, contract_id: str) -> ResearchContract:
        contract = self.get_contract(contract_id)
        frozen = contract.model_copy(
            update={
                "lifecycle_status": "FROZEN",
                "frozen_at": datetime.now(timezone.utc),
                "validation_warnings": [
                    *contract.validation_warnings,
                    "用户已冻结 Research Contract；后续取数必须对照该需求，不得改写医学安全规则。",
                ],
            }
        )
        self.rag_index.index_contract(frozen)
        with self._lock:
            self._contracts[contract_id] = frozen
        return frozen

    def build_rag_index(self, topic_id: str, request: RAGIndexRequest) -> RAGIndexReport:
        topic = self._topic(topic_id)
        with self._lock:
            scan = self._scans.get(topic_id)
            candidates = list(self._candidates.get(topic_id, []))
            contract = self._contracts.get(request.contract_id) if request.contract_id else None
        if scan is None:
            raise ResearchPlanningNotFoundError("尚未执行 literature-scan，无法建立 Planning RAG。")
        if request.contract_id and contract is None:
            raise ResearchPlanningNotFoundError("指定的 Research Contract 不存在或服务已重启。")
        if contract is not None and contract.topic_id != topic_id:
            raise ValueError("Research Contract 不属于当前 Topic。")
        report = self.rag_index.index_topic(topic, scan, candidates)
        return self.rag_index.index_contract(contract) if contract is not None else report

    def query_evidence(
        self,
        topic_id: str,
        request: EvidenceQueryRequest,
    ) -> EvidenceQueryResponse:
        self._topic(topic_id)
        return self.rag_index.query(topic_id, request)

    def knowledge_graph(self, topic_id: str) -> ScientificGraphSnapshot:
        self._topic(topic_id)
        return self.rag_index.graph(topic_id)

    def evaluate_rag(
        self,
        topic_id: str,
        request: RAGEvaluationRequest,
    ) -> RAGEvaluationResult:
        self._topic(topic_id)
        return self.rag_index.evaluate(topic_id, request)

    def get_contract(self, contract_id: str) -> ResearchContract:
        with self._lock:
            contract = self._contracts.get(contract_id)
        if contract is None:
            raise ResearchPlanningNotFoundError("Research Contract 不存在或服务已重启。")
        return contract

    def plan_sources(
        self,
        contract_id: str,
        request: SourcePlanRequest,
    ) -> SourcePlanningResult:
        contract = self.get_contract(contract_id)
        with self._lock:
            scan = self._scans.get(contract.topic_id)
        papers = list(getattr(scan, "papers", []) or [])
        result = self.source_broker.plan(contract, papers, request)
        if contract.validation_status != "READY_FOR_SOURCE_PLANNING":
            warnings = [
                *result.source_plan.warnings,
                "Research Contract 尚未通过 Evidence 门控；Source Plan 只能用于发现和补证。",
            ]
            result = result.model_copy(
                update={
                    "source_plan": result.source_plan.model_copy(
                        update={"status": "PARTIAL", "warnings": warnings}
                    )
                }
            )
        with self._lock:
            self._source_plans[result.source_plan.source_plan_id] = result
        return result

    def get_source_plan(self, source_plan_id: str) -> SourcePlanningResult:
        with self._lock:
            result = self._source_plans.get(source_plan_id)
        if result is None:
            raise ResearchPlanningNotFoundError("Source Plan 不存在或服务已重启。")
        return result

    def _topic(self, topic_id: str) -> ResearchTopic:
        with self._lock:
            topic = self._topics.get(topic_id)
        if topic is None:
            raise ResearchPlanningNotFoundError("Research Topic 不存在或服务已重启。")
        return topic

    @staticmethod
    def _literature_query(topic: ResearchTopic) -> str:
        if topic.disease == "breast cancer" and "新辅助" in topic.topic:
            return "breast cancer neoadjuvant treatment response pCR"
        return topic.topic
