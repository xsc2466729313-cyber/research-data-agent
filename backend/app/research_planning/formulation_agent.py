from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from backend.app.literature.models import PaperRecord
from backend.app.oncology import is_breast_cancer, resolve_cancer_profile
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
    perspectives: tuple[str, ...] = ()
    generation_source: str = "GENERIC_FALLBACK"


class ResearchFormulationAgent:
    """Create evidence-linked research requirements. Templates are fallback only."""

    _WEIGHTS = {
        "evidence_strength": 0.25,
        "data_availability": 0.25,
        "field_coverage": 0.25,
        "novelty": 0.10,
        "traceability": 0.15,
    }

    _GENES = (
        ("PIK3CA", ("PIK3CA",)),
        ("TP53", ("TP53", "p53")),
        ("ERBB2", ("ERBB2", "HER2")),
        ("BRCA1", ("BRCA1",)),
        ("BRCA2", ("BRCA2",)),
        ("ESR1", ("ESR1",)),
        ("AKT1", ("AKT1",)),
        ("PTEN", ("PTEN",)),
        ("EGFR", ("EGFR",)),
        ("KRAS", ("KRAS",)),
        ("BRAF", ("BRAF",)),
        ("APC", ("APC",)),
        ("SMAD4", ("SMAD4",)),
        ("SOX2", ("SOX2",)),
        ("AR", ("AR",)),
        ("SPOP", ("SPOP",)),
        ("CTNNB1", ("CTNNB1",)),
        ("TERT", ("TERT",)),
        ("CDKN2A", ("CDKN2A",)),
        ("VHL", ("VHL",)),
        ("PBRM1", ("PBRM1",)),
        ("SETD2", ("SETD2",)),
        ("BAP1", ("BAP1",)),
        ("FGFR3", ("FGFR3",)),
        ("RB1", ("RB1",)),
        ("ARID1A", ("ARID1A",)),
        ("IDH1", ("IDH1",)),
        ("NRAS", ("NRAS",)),
        ("NF1", ("NF1",)),
        ("CDH1", ("CDH1",)),
        ("CCND1", ("CCND1",)),
        ("RET", ("RET",)),
    )
    _OUTCOMES = (
        ("pathological complete response", ("pCR", "pathological complete response", "病理完全缓解")),
        ("treatment response", ("treatment response", "response", "疗效", "缓解")),
        ("overall survival", ("overall survival", "OS", "生存")),
        ("disease-free survival", ("DFS", "disease-free survival", "无病生存")),
    )

    def formulate(self, topic: ResearchTopic, papers: list[PaperRecord]) -> list[QuestionCandidate]:
        drafts = self._evidence_drafts(topic, papers)
        source = "EVIDENCE_AGENT"
        if not drafts:
            drafts = self._fallback_drafts(topic)
            source = "GENERIC_FALLBACK"
            drafts = [
                _QuestionDraft(**{**draft.__dict__, "generation_source": source})
                for draft in drafts
            ]
        candidates: list[QuestionCandidate] = []
        for draft in drafts[:5]:
            supported_papers = self._supported_papers(papers, draft.evidence_groups)
            evidence = evidence_references(
                supported_papers,
                terms=list(draft.evidence_terms),
                evidence_type="question_formulation",
                minimum_term_hits=2 if len(draft.evidence_terms) >= 3 else 1,
            )
            generation = "EVIDENCE_AGENT" if evidence else draft.generation_source
            components = self._feasibility(supported_papers, evidence, len(draft.field_hints))
            score = round(
                sum(getattr(components, key) * weight for key, weight in self._WEIGHTS.items()),
                4,
            )
            unresolved = []
            if not evidence:
                unresolved.append("尚无可核验论文 Evidence，不能进入正式数据获取。")
            if not any(paper.dataset_accessions for paper in supported_papers):
                unresolved.append("尚未在论文中看到公开 accession，数据可获得性待核验。")
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
                        "已找到可点击的论文语境证据，选择后可冻结 Research Contract。"
                        if evidence
                        else "尚无可核验论文证据；仅作为 GENERIC_FALLBACK 草案。"
                    ),
                    rank=1,
                    generation_source=generation,
                    perspectives=list(draft.perspectives),
                    unresolved_questions=unresolved,
                )
            )
        candidates.sort(key=lambda item: (-item.feasibility_score, item.question))
        if source == "EVIDENCE_AGENT" and not any(item.generation_source == "EVIDENCE_AGENT" for item in candidates):
            for index, item in enumerate(candidates):
                candidates[index] = item.model_copy(update={"generation_source": "GENERIC_FALLBACK"})
        return [candidate.model_copy(update={"rank": index}) for index, candidate in enumerate(candidates, start=1)]

    def _evidence_drafts(self, topic: ResearchTopic, papers: list[PaperRecord]) -> list[_QuestionDraft]:
        if not papers:
            return []
        corpus = self._corpus(papers)
        breast_specific = is_breast_cancer(topic.disease)
        genes = [
            name
            for name, aliases in self._GENES
            if any(
                re.search(rf"(?<![a-z0-9]){re.escape(alias.casefold())}(?![a-z0-9])", corpus)
                for alias in aliases
            )
        ]
        outcomes = [name for name, aliases in self._OUTCOMES if any(alias.casefold() in corpus for alias in aliases)]
        her2 = breast_specific and (
            "her2" in corpus or "erbb2" in corpus or "her2" in topic.topic.casefold()
        )
        neoadjuvant = "neoadjuvant" in corpus or "新辅助" in topic.topic
        expression = any(token in corpus for token in ("expression", "transcriptom", "基因表达"))
        subtype = any(token in corpus for token in ("subtype", "亚型", "receptor", "triple"))
        if not genes and not outcomes and not her2 and not neoadjuvant:
            return []
        disease = topic.disease or "breast cancer"
        population = topic.known_population or (
            "HER2-positive breast cancer patients receiving neoadjuvant treatment"
            if her2 and neoadjuvant
            else f"{disease} patients"
        )
        primary_gene = genes[0] if genes else ("ERBB2" if her2 else "molecular exposure")
        primary_outcome = outcomes[0] if outcomes else (topic.known_outcome or "treatment response")
        folded_outcome = primary_outcome.casefold()
        outcome_field = (
            "pCR"
            if "pcr" in folded_outcome or "complete" in folded_outcome
            else "survival"
            if "survival" in folded_outcome
            else "treatment_response"
        )
        molecular_fields = (
            f"{primary_gene}_mutation" if primary_gene != "molecular exposure" else "primary_exposure",
            *(("her2_status",) if breast_specific else ()),
            outcome_field,
            "treatment",
        )
        subgroup_label = "不同受体亚型" if breast_specific else "不同临床或分子亚组"
        subgroup_exposure = "ER/PR/HER2 receptor subtype" if breast_specific else "clinical or molecular subgroup"
        subgroup_fields = (
            *(('er_status', 'pr_status', 'her2_status') if breast_specific else ('subgroup',)),
            outcome_field,
            "treatment",
        )
        drafts = [
            _QuestionDraft(
                question=f"{primary_gene} 状态是否与{self._zh_population(population)}的{self._zh_outcome(primary_outcome)}有关？",
                research_type="association",
                population=population,
                exposure=f"{primary_gene} status",
                outcome=primary_outcome,
                field_hints=molecular_fields,
                evidence_terms=tuple(filter(None, (primary_gene, "HER2" if her2 else "", primary_outcome, "neoadjuvant" if neoadjuvant else ""))),
                evidence_groups=self._groups(primary_gene, primary_outcome, her2),
                perspectives=("molecular", "outcome"),
                generation_source="EVIDENCE_AGENT",
            ),
            _QuestionDraft(
                question=f"{'新辅助治疗' if neoadjuvant else '当前治疗'}后，{subgroup_label}的{self._zh_outcome(primary_outcome)}是否存在差异？",
                research_type="association",
                population=population,
                exposure=subgroup_exposure,
                outcome=primary_outcome,
                field_hints=subgroup_fields,
                evidence_terms=("subtype", "HER2" if breast_specific else "subgroup", primary_outcome, "neoadjuvant" if neoadjuvant else "treatment"),
                evidence_groups=(("subtype", "receptor", "HER2", "ERBB2", "triple") if breast_specific else ("subtype", "subgroup", "molecular"), (primary_outcome, "pCR", "response", "survival")),
                perspectives=("clinical", "treatment"),
                generation_source="EVIDENCE_AGENT",
            ),
        ]
        if expression or "predict" in corpus or "预测" in topic.topic:
            drafts.append(
                _QuestionDraft(
                    question=f"治疗前基因表达特征能否预测{self._zh_population(population)}的{self._zh_outcome(primary_outcome)}？",
                    research_type="classification_prediction",
                    population=population,
                    exposure="pretreatment gene expression features",
                    outcome=primary_outcome,
                    field_hints=("gene_expression", "sample_timepoint", outcome_field, "treatment"),
                    evidence_terms=("gene expression", "predict", primary_outcome, "neoadjuvant" if neoadjuvant else "treatment"),
                    evidence_groups=(("gene expression", "transcriptom", "expression"), ("predict", "prediction", "pCR", "response")),
                    perspectives=("molecular", "methodology"),
                    generation_source="EVIDENCE_AGENT",
                )
            )
        drafts.append(
            _QuestionDraft(
                question=f"哪些公开队列能够同时提供{primary_gene}与{self._zh_outcome(primary_outcome)}，且保持患者级可追溯？",
                research_type="association",
                population=population,
                exposure=primary_gene,
                outcome=primary_outcome,
                field_hints=("study_id", "patient_id", "source_id", f"{primary_gene}_mutation", outcome_field),
                evidence_terms=("cohort", "dataset", "GSE", primary_gene, primary_outcome),
                evidence_groups=(("GSE", "cohort", "dataset", "accession"), (primary_gene, primary_outcome, "pCR", "response")),
                perspectives=("data",),
                generation_source="EVIDENCE_AGENT",
            )
        )
        supported = []
        for draft in drafts:
            if self._supported_papers(papers, draft.evidence_groups) or draft.perspectives == ("data",):
                supported.append(draft)
        return supported[:5]

    def _fallback_drafts(self, topic: ResearchTopic) -> list[_QuestionDraft]:
        if self._legacy_applicable(topic):
            return self._legacy_template_drafts()
        disease = topic.disease or topic.topic
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
                perspectives=("clinical", "outcome"),
            ),
            _QuestionDraft(
                question=f"{topic.topic}中不同亚组的主要结局是否存在异质性？",
                research_type="subgroup_association",
                population=population,
                exposure="可验证亚组变量（待文献定义）",
                outcome=outcome,
                field_hints=("population_id", "subgroup", "primary_outcome"),
                evidence_terms=tuple(filter(None, (topic.topic, disease, "subgroup", "heterogeneity"))),
                perspectives=("clinical", "methodology"),
            ),
            _QuestionDraft(
                question=f"公开数据中的多变量特征能否预测{topic.topic}的主要结局？",
                research_type="classification_prediction",
                population=population,
                exposure="多变量特征集合（待文献定义）",
                outcome=outcome,
                field_hints=("population_id", "predictor_features", "primary_outcome"),
                evidence_terms=tuple(filter(None, (topic.topic, disease, "prediction", "predict"))),
                perspectives=("data", "methodology"),
            ),
        ]

    @staticmethod
    def _legacy_applicable(topic: ResearchTopic) -> bool:
        folded = topic.topic.casefold()
        disease = topic.disease or topic.topic
        return disease == "breast cancer" and ("新辅助" in topic.topic or "neoadjuvant" in folded)

    @staticmethod
    def _legacy_template_drafts() -> list[_QuestionDraft]:
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
                perspectives=("molecular", "outcome"),
                generation_source="GENERIC_FALLBACK",
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
                perspectives=("clinical", "treatment"),
                generation_source="GENERIC_FALLBACK",
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
                perspectives=("molecular", "methodology"),
                generation_source="GENERIC_FALLBACK",
            ),
        ]

    @staticmethod
    def _groups(gene: str, outcome: str, her2: bool) -> tuple[tuple[str, ...], ...]:
        gene_group = (gene, "HER2", "ERBB2") if her2 else (gene,)
        outcome_group = (outcome, "pCR", "pathological complete response", "response", "survival")
        return (gene_group, outcome_group)

    @staticmethod
    def _zh_population(population: str) -> str:
        profile = resolve_cancer_profile(population)
        if profile is not None and profile.key == "breast_cancer" and "HER2" in population:
            return "HER2 阳性乳腺癌患者"
        if profile is not None:
            return f"{profile.label_zh}患者"
        return population

    @staticmethod
    def _zh_outcome(outcome: str) -> str:
        folded = outcome.casefold()
        if "pcr" in folded or "complete" in folded:
            return "病理完全缓解（pCR）"
        if "survival" in folded:
            return "生存结局"
        return "治疗响应"

    @staticmethod
    def _corpus(papers: list[PaperRecord]) -> str:
        parts = []
        for paper in papers:
            parts.extend([paper.title, paper.abstract or "", *paper.sections.values(), " ".join(paper.dataset_accessions)])
        return " ".join(parts).casefold()

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
