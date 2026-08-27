from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from backend.app.literature.models import PaperRecord
from backend.app.research_planning.evidence import evidence_references
from backend.app.research_planning.models import (
    FeasibilityComponents,
    QuestionCandidate,
    ResearchTopic,
)


@dataclass(frozen=True)
class _QuestionDraft:
    question: str
    research_type: str
    population: str
    exposure: str
    outcome: str
    field_hints: tuple[str, ...]
    evidence_terms: tuple[str, ...]
    evidence_groups: tuple[tuple[str, ...], ...] = ()


class ResearchFormulationAgent:
    """Create evidence-linked, explicitly provisional research questions."""

    _WEIGHTS = {
        "evidence_strength": 0.25,
        "data_availability": 0.25,
        "field_coverage": 0.25,
        "novelty": 0.10,
        "traceability": 0.15,
    }

    def formulate(self, topic: ResearchTopic, papers: list[PaperRecord]) -> list[QuestionCandidate]:
        drafts = self._drafts(topic)
        candidates: list[QuestionCandidate] = []
        for draft in drafts:
            supported_papers = self._supported_papers(papers, draft.evidence_groups)
            evidence = evidence_references(
                supported_papers,
                terms=list(draft.evidence_terms),
                evidence_type="question_formulation",
                minimum_term_hits=2 if len(draft.evidence_terms) >= 3 else 1,
            )
            components = self._feasibility(supported_papers, evidence, len(draft.field_hints))
            score = round(
                sum(getattr(components, key) * weight for key, weight in self._WEIGHTS.items()),
                4,
            )
            candidates.append(
                QuestionCandidate(
                    candidate_id=f"question-{uuid4().hex[:12]}",
                    topic_id=topic.topic_id,
                    question=draft.question,
                    research_type=draft.research_type,
                    population=draft.population,
                    exposure=draft.exposure,
                    outcome=draft.outcome,
                    field_hints=list(draft.field_hints),
                    feasibility=components,
                    feasibility_score=score,
                    score_basis=[
                        "采用方案默认权重 E/D/F/N/T = 0.25/0.25/0.25/0.10/0.15。",
                        "当前分值只基于已检索论文元数据、可见摘要和公开 accession，属于规划期估计。",
                        "Novelty 未做系统综述验证，固定为保守先验，不得解释为已证实创新性。",
                    ],
                    literature_evidence=evidence,
                    recommendation_reason=(
                        "已找到可点击的论文语境证据，可继续生成字段契约并做数据源验证。"
                        if evidence
                        else "尚无可核验论文证据；可作为澄清草案，但在补充证据前不应进入正式数据获取。"
                    ),
                    rank=1,
                )
            )
        candidates.sort(key=lambda item: (-item.feasibility_score, item.question))
        return [candidate.model_copy(update={"rank": index}) for index, candidate in enumerate(candidates, start=1)]

    @staticmethod
    def _drafts(topic: ResearchTopic) -> list[_QuestionDraft]:
        folded = topic.topic.casefold()
        disease = topic.disease or topic.topic
        if disease == "breast cancer" and ("新辅助" in topic.topic or "neoadjuvant" in folded):
            return [
                _QuestionDraft(
                    question="PIK3CA 突变是否与 HER2 阳性乳腺癌患者新辅助治疗后的 pCR 有关？",
                    research_type="association",
                    population="HER2-positive breast cancer patients receiving neoadjuvant treatment",
                    exposure="PIK3CA mutation status",
                    outcome="pathological complete response",
                    field_hints=("PIK3CA_mutation", "her2_status", "pCR", "treatment"),
                    evidence_terms=("PIK3CA", "HER2", "pCR", "pathological complete response", "neoadjuvant"),
                    evidence_groups=(("PIK3CA",), ("HER2", "ERBB2"), ("pCR", "pathological complete response")),
                ),
                _QuestionDraft(
                    question="乳腺癌不同受体亚型在新辅助治疗后的 pCR 是否存在差异？",
                    research_type="association",
                    population="breast cancer patients receiving neoadjuvant treatment",
                    exposure="ER/PR/HER2 receptor subtype",
                    outcome="pathological complete response",
                    field_hints=("er_status", "pr_status", "her2_status", "pCR", "treatment"),
                    evidence_terms=("breast cancer", "subtype", "HER2", "pCR", "neoadjuvant"),
                    evidence_groups=(("subtype", "receptor subtype", "molecular subtype"), ("pCR", "pathological complete response")),
                ),
                _QuestionDraft(
                    question="治疗前基因表达特征能否预测乳腺癌新辅助治疗后的 pCR？",
                    research_type="classification_prediction",
                    population="breast cancer patients with pretreatment tumor samples",
                    exposure="pretreatment gene expression features",
                    outcome="pathological complete response",
                    field_hints=("gene_expression", "sample_timepoint", "pCR", "treatment"),
                    evidence_terms=("gene expression", "predict", "pCR", "pathological complete response", "neoadjuvant"),
                    evidence_groups=(("gene expression", "transcriptomic"), ("predict", "prediction"), ("pCR", "pathological complete response")),
                ),
            ]
        population = topic.known_population or f"研究对象：{disease}"
        outcome = topic.known_outcome or "主要科研结局（待文献定义）"
        return [
            _QuestionDraft(
                question=f"{topic.topic}中哪些可观测因素与主要结局相关？",
                research_type="association",
                population=population,
                exposure=topic.known_exposure or "候选暴露因素（待文献定义）",
                outcome=outcome,
                field_hints=("population_id", "primary_exposure", "primary_outcome"),
                evidence_terms=tuple(filter(None, (topic.topic, disease, topic.known_exposure or "", topic.known_outcome or ""))),
            ),
            _QuestionDraft(
                question=f"{topic.topic}中不同亚组的主要结局是否存在异质性？",
                research_type="subgroup_association",
                population=population,
                exposure="可验证亚组变量（待文献定义）",
                outcome=outcome,
                field_hints=("population_id", "subgroup", "primary_outcome"),
                evidence_terms=tuple(filter(None, (topic.topic, disease, "subgroup", "heterogeneity"))),
            ),
            _QuestionDraft(
                question=f"公开数据中的多变量特征能否预测{topic.topic}的主要结局？",
                research_type="classification_prediction",
                population=population,
                exposure="多变量特征集合（待文献定义）",
                outcome=outcome,
                field_hints=("population_id", "predictor_features", "primary_outcome"),
                evidence_terms=tuple(filter(None, (topic.topic, disease, "prediction", "predict"))),
            ),
        ]

    @staticmethod
    def _supported_papers(
        papers: list[PaperRecord],
        groups: tuple[tuple[str, ...], ...],
    ) -> list[PaperRecord]:
        if not groups:
            return papers
        output: list[PaperRecord] = []
        for paper in papers:
            text = " ".join([paper.title, paper.abstract or "", *paper.sections.values()]).casefold()
            if all(any(term.casefold() in text for term in group) for group in groups):
                output.append(paper)
        return output

    @staticmethod
    def _feasibility(
        papers: list[PaperRecord],
        evidence: list[object],
        field_count: int,
    ) -> FeasibilityComponents:
        evidence_strength = min(0.95, 0.25 + 0.2 * len(evidence)) if evidence else 0.1
        has_accession = any(paper.dataset_accessions for paper in papers)
        data_availability = 0.85 if has_accession else 0.55 if papers else 0.15
        field_coverage = min(0.9, 0.45 + 0.1 * len(evidence)) if field_count else 0.1
        traceability = 1.0 if evidence else 0.1
        return FeasibilityComponents(
            evidence_strength=round(evidence_strength, 3),
            data_availability=data_availability,
            field_coverage=round(field_coverage, 3),
            novelty=0.5,
            traceability=traceability,
        )
