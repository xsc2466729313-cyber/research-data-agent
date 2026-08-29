from __future__ import annotations

from urllib.parse import urlparse

from backend.app.agent.accession_harvest import asks_pcr, seed_geo_accessions
from backend.app.agent.models import (
    AgentTaskResult,
    QualityGateLayer,
    QualityGateReport,
)


OFFICIAL_HOSTS = (
    "ncbi.nlm.nih.gov",
    "clinicaltrials.gov",
    "gdc.cancer.gov",
    "cbioportal.org",
    "civicdb.org",
    "europepmc.org",
    "ebi.ac.uk",
)


class QualityGateBuilder:
    """Four-layer research-data admission gate. Decisions use observed evidence only."""

    def build(self, result: AgentTaskResult) -> QualityGateReport:
        layers = [
            self._source_gate(result),
            self._field_gate(result),
            self._entity_gate(result),
            self._fitness_gate(result),
        ]
        decisions = [layer.decision for layer in layers]
        if "REJECT" in decisions:
            overall = "REJECT"
        elif all(decision == "PASS" for decision in decisions):
            overall = "PASS"
        else:
            overall = "REVIEW"
        publish_allowed = overall == "PASS" and bool(result.modeling_dataset.row_count)
        return QualityGateReport(
            overall=overall,
            publish_allowed=publish_allowed,
            layers=layers,
            cohort_f1=None if result.cohort_construction is None else result.cohort_construction.patient_linkage_f1,
            cohort_plan_f1=self._cohort_plan_f1(result),
            variable_coverage=(
                None
                if result.study_design is None
                else result.study_design.variable_coverage_rate
            ),
            traceability=self._traceability(result),
            research_fitness=self._fitness_score(result),
            note=(
                "质量门只根据本次任务观察到的来源、字段、身份和变量覆盖做准入判断，不生成虚假分数。"
                "本题计划队列 F1 是计划 GEO/NCT 与已检索队列的集合对照，不是 Gold Set 患者关联分，也不是正式 SDTI。"
            ),
        )

    def _source_gate(self, result: AgentTaskResult) -> QualityGateLayer:
        sources = list(result.source_items)
        if not sources:
            return QualityGateLayer(
                gate_id="source_trust",
                label="Gate 1 来源可信",
                decision="REVIEW",
                checks=["DOI/PMID", "数据库ID", "URL", "Version/checksum"],
                evidence="当前没有已登记来源，无法核验 DOI、PMID、数据库 ID 或官方 URL。",
            )
        missing_url = sum(1 for item in sources if not str(item.url or "").strip())
        missing_id = sum(1 for item in sources if not str(item.source_id or "").strip())
        missing_accession = sum(
            1 for item in sources if not str(item.accession or item.source_id or "").strip()
        )
        official = sum(1 for item in sources if self._official_url(item.url))
        versioned = sum(1 for item in sources if item.checksum or item.local_path)
        if missing_url or missing_id:
            decision = "REJECT"
            evidence = f"{missing_url} 个来源缺 URL，{missing_id} 个来源缺 source_id。"
        elif official == len(sources) and missing_accession == 0:
            decision = "PASS"
            evidence = (
                f"{len(sources)} 个来源均有 source_id 与官方 URL；"
                f"{versioned} 个带来源校验值或本地缓存版本。"
            )
        else:
            decision = "REVIEW"
            evidence = (
                f"{official}/{len(sources)} 个来源指向官方域名；"
                f"{len(sources) - missing_accession} 个有数据库 ID/accession。"
            )
        return QualityGateLayer(
            gate_id="source_trust",
            label="Gate 1 来源可信",
            decision=decision,
            checks=["DOI/PMID", "数据库ID", "URL", "Version/checksum"],
            evidence=evidence,
        )

    def _field_gate(self, result: AgentTaskResult) -> QualityGateLayer:
        readiness = result.readiness
        if not result.modeling_dataset.row_count:
            return QualityGateLayer(
                gate_id="field_quality",
                label="Gate 2 字段质量",
                decision="REVIEW",
                checks=["字段一致性", "单位一致性", "类型合法性"],
                evidence="尚无患者/样本级宽表，不能判定字段一致性或类型合法性。",
            )
        completeness = readiness.field_completeness_rate
        outcome_rate = self._fill_rate(result, ("pcr", "pcr_binary", "treatment_response"))
        outcome_aligned = bool(readiness.target_match) and (outcome_rate or 0.0) >= 0.8
        if completeness is not None and completeness >= 0.8 and readiness.target_match:
            decision = "PASS"
        elif outcome_aligned:
            decision = "PASS"
        else:
            decision = "REVIEW"
        completeness_text = "未计算" if completeness is None else f"{completeness:.1%}"
        if decision == "PASS":
            evidence = (
                f"字段完整率 {completeness_text}；"
                f"结局字段已对齐"
                + (f"（行覆盖 {outcome_rate:.1%}）" if outcome_rate is not None else "")
                + f"；清洗 {readiness.cleaned_value_count} 处。"
            )
        elif not readiness.target_match:
            evidence = (
                f"字段完整率 {completeness_text}，清洗 {readiness.cleaned_value_count} 处。"
                "本题要的结局字段还没对上，质量门因此待补。"
            )
        else:
            evidence = (
                f"字段完整率 {completeness_text}，清洗 {readiness.cleaned_value_count} 处。"
                "字段完整率尚未达到通过线，质量门因此待补。"
            )
        return QualityGateLayer(
            gate_id="field_quality",
            label="Gate 2 字段质量",
            decision=decision,
            checks=["字段一致性", "单位一致性", "类型合法性"],
            evidence=evidence,
        )

    def _entity_gate(self, result: AgentTaskResult) -> QualityGateLayer:
        alignment = result.data_alignment
        if alignment is None or not alignment.row_count:
            return QualityGateLayer(
                gate_id="entity_consistency",
                label="Gate 3 实体一致性",
                decision="REVIEW",
                checks=["患者匹配", "样本关系", "冲突信息"],
                evidence="没有主表行，不能判定患者/样本关联。低置信度匹配不得自动合并。",
            )
        status = alignment.entity_match_status
        if status == "UNMATCH":
            decision = "REVIEW"
        elif status == "MATCH":
            decision = "PASS"
        else:
            decision = "REVIEW"
        return QualityGateLayer(
            gate_id="entity_consistency",
            label="Gate 3 实体一致性",
            decision=decision,
            checks=["患者匹配", "样本关系", "冲突信息"],
            evidence=(
                f"实体匹配={status}；未对齐身份行 {alignment.unresolved_identity_row_count}；"
                f"{alignment.cross_source_join_status}。"
            ),
        )

    def _fitness_gate(self, result: AgentTaskResult) -> QualityGateLayer:
        coverage = (
            None
            if result.study_design is None
            else result.study_design.variable_coverage_rate
        )
        outcome_rate = self._fill_rate(result, ("pcr", "pcr_binary", "treatment_response"))
        her2_rate = self._fill_rate(result, ("her2_status",))
        her2_needed = self._needs_her2(result)
        her2_ok = (not her2_needed) or (her2_rate or 0.0) >= 0.5
        outcome_ok = bool(result.readiness.target_match) and (outcome_rate or 0.0) >= 0.8
        if result.readiness.analysis_ready and coverage is not None and coverage >= 0.8:
            decision = "PASS"
        elif result.readiness.analysis_ready and outcome_ok and her2_ok:
            decision = "PASS"
        elif result.modeling_dataset.row_count == 0:
            decision = "REVIEW"
        else:
            decision = "REVIEW"
        coverage_text = "未计算" if coverage is None else f"{coverage:.1%}"
        if result.readiness.target_column:
            outcome_text = f"结局字段已指向 {result.readiness.target_column}。"
        else:
            outcome_text = "本题结局字段尚未对上当前这批记录，还要补结局字段。"
        evidence = (
            f"可科研性={result.readiness.status}；"
            f"本题变量覆盖={coverage_text}。"
            f"{outcome_text}"
        )
        return QualityGateLayer(
            gate_id="research_fitness",
            label="Gate 4 科研适用性",
            decision=decision,
            checks=["研究所需变量", "结局同域", "样本量与分析单位"],
            evidence=evidence,
        )

    @staticmethod
    def _fill_rate(result: AgentTaskResult, names: tuple[str, ...]) -> float | None:
        rows = list(result.modeling_dataset.rows or [])
        if not rows:
            return None
        filled = 0
        for row in rows:
            if any(row.get(name) not in {None, "", "<缺失>"} for name in names):
                filled += 1
        return filled / len(rows)

    @staticmethod
    def _needs_her2(result: AgentTaskResult) -> bool:
        spec = result.research_spec
        blob = f"{spec.research_goal} {spec.subtype or ''}".casefold()
        return "her2" in blob or "her-2" in blob or "受体" in blob

    @staticmethod
    def _cohort_plan_f1(result: AgentTaskResult) -> float | None:
        spec = result.research_spec
        expected = {str(item).upper() for item in seed_geo_accessions(spec)}
        if asks_pcr(spec):
            expected.update({"GSE25066", "GSE76360", "GSE50948"})
        if not expected:
            return None
        retrieved: set[str] = set()
        for item in result.source_items:
            accession = str(item.accession or "").upper()
            if accession.startswith(("GSE", "NCT")):
                retrieved.add(accession)
        for row in list(result.modeling_dataset.rows or [])[:1]:
            study_id = str(row.get("study_id") or "").upper()
            if study_id.startswith(("GSE", "NCT")):
                retrieved.add(study_id)
        name = str(result.modeling_dataset.name or "").upper()
        for token in expected:
            if token in name:
                retrieved.add(token)
        if not retrieved and not result.source_items and not result.modeling_dataset.row_count:
            return None
        true_positive = len(expected & retrieved)
        false_positive = len(retrieved - expected)
        false_negative = len(expected - retrieved)
        precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) else 0.0
        recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) else 0.0
        if precision + recall == 0:
            return 0.0
        return round(2 * precision * recall / (precision + recall), 4)

    @staticmethod
    def _official_url(url: str | None) -> bool:
        host = (urlparse(str(url or "")).hostname or "").lower()
        return any(item in host for item in OFFICIAL_HOSTS)

    @staticmethod
    def _traceability(result: AgentTaskResult) -> float | None:
        sources = list(result.source_items)
        if not sources:
            return None
        complete = sum(
            1
            for item in sources
            if item.source_id and item.url and (item.accession or item.checksum)
        )
        return round(complete / len(sources), 4)

    @staticmethod
    def _fitness_score(result: AgentTaskResult) -> float | None:
        fitness = getattr(
            getattr(result.competition_report, "unified_evaluation", None),
            "task_adaptive_fitness",
            None,
        )
        score = getattr(fitness, "fitness_score", None)
        if score is None:
            return None
        return round(float(score) / 100.0, 4) if float(score) > 1 else round(float(score), 4)
