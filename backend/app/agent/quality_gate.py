from __future__ import annotations

from urllib.parse import urlparse

from backend.app.agent.accession_harvest import asks_pcr, needs_clinical_outcome, seed_geo_accessions
from backend.app.agent.models import (
    AgentTaskResult,
    QualityGateLayer,
    QualityGateReport,
)
from backend.app.agent.research_brief import ResearchBriefBuilder


OFFICIAL_HOSTS = (
    "ncbi.nlm.nih.gov",
    "clinicaltrials.gov",
    "gdc.cancer.gov",
    "cbioportal.org",
    "civicdb.org",
    "europepmc.org",
    "ebi.ac.uk",
)

FIELD_COVERAGE_MIN = 0.45
OUTCOME_MATCH_MIN = 0.75
EXPLORATORY_ROW_MIN = 30


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
            variable_coverage=self._primary_field_coverage(result),
            traceability=self._traceability(result),
            research_fitness=self._fitness_score(result),
            note=(
                "质量门仅依据本次任务观察到的来源、主要字段、身份关系和科研适用性判定，不生成虚假分数。"
                "探索性准入不等于正式发表结论或临床结论。"
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
        coverage = self._primary_field_coverage(result)
        decision = "PASS" if coverage is not None and coverage >= FIELD_COVERAGE_MIN else "REVIEW"
        coverage_text = "未计算" if coverage is None else ("未覆盖" if coverage <= 0 else f"{coverage:.1%}")
        if decision == "PASS":
            evidence = f"主要字段行覆盖 {coverage_text}，达到探索性字段准入线（{FIELD_COVERAGE_MIN:.0%}）。"
        else:
            evidence = (
                f"主要字段行覆盖 {coverage_text}，低于探索性字段准入线（{FIELD_COVERAGE_MIN:.0%}）。"
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
        coverage = self._primary_field_coverage(result)
        needs_outcome = self._needs_outcome(result)
        outcome_rate = result.readiness.target_match_rate
        if outcome_rate is None:
            outcome_rate = 1.0 if result.readiness.target_match else 0.0
        her2_rate = self._her2_evidence_rate(result)
        her2_needed = self._needs_her2(result)
        her2_ok = (not her2_needed) or (her2_rate or 0.0) >= 0.5
        outcome_ok = (not needs_outcome) or outcome_rate >= OUTCOME_MATCH_MIN
        sample_ok = result.modeling_dataset.row_count >= EXPLORATORY_ROW_MIN
        decision = "PASS" if (
            coverage is not None
            and coverage >= FIELD_COVERAGE_MIN
            and outcome_ok
            and her2_ok
            and sample_ok
        ) else "REVIEW"
        coverage_text = "未计算" if coverage is None else f"{coverage:.1%}"
        if not needs_outcome:
            outcome_text = "本题不要求临床结局。"
        elif outcome_ok:
            outcome_text = f"研究结局匹配={outcome_rate:.1%}，达到探索性准入线（{OUTCOME_MATCH_MIN:.0%}）。"
        else:
            outcome_text = f"研究结局匹配={outcome_rate:.1%}，低于探索性准入线（{OUTCOME_MATCH_MIN:.0%}）。"
        evidence = (
            f"记录数={result.modeling_dataset.row_count}（准入线 {EXPLORATORY_ROW_MIN}）；"
            f"主要字段行覆盖={coverage_text}；"
            f"{outcome_text}"
        )
        if her2_needed and not her2_ok:
            evidence += "HER2 直接状态或可追溯亚型证据不足，不能用 ERBB2 CNA 代替。"
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
    def _her2_evidence_rate(result: AgentTaskResult) -> float | None:
        rows = list(result.modeling_dataset.rows or [])
        if not rows:
            return None
        filled = 0
        for row in rows:
            direct = row.get("her2_status")
            if direct not in {None, "", "<缺失>"}:
                filled += 1
                continue
            subtype = str(row.get("subtype") or "").casefold()
            if ("her2-positive" in subtype or "her2 positive" in subtype or "her-2 positive" in subtype):
                filled += 1
        return filled / len(rows)

    @staticmethod
    def _needs_her2(result: AgentTaskResult) -> bool:
        spec = result.research_spec
        blob = f"{spec.research_goal} {spec.subtype or ''}".casefold()
        return "her2" in blob or "her-2" in blob or "受体" in blob

    @staticmethod
    def _needs_outcome(result: AgentTaskResult) -> bool:
        brief = result.research_brief
        if brief is not None:
            return bool(brief.needs_clinical_outcome)
        return needs_clinical_outcome(result.research_spec)

    @staticmethod
    def _primary_field_coverage(result: AgentTaskResult) -> float | None:
        brief = result.research_brief
        if brief is None:
            brief = ResearchBriefBuilder().build(
                result.research_spec.research_goal,
                result.research_spec,
            )
        primary = [field for field in brief.fields if field.priority == "primary"]
        rows = list(result.modeling_dataset.rows or [])
        if primary:
            if not rows:
                return 0.0
            rates: list[float] = []
            missing = {None, "", "<缺失>"}
            for field in primary:
                filled = 0
                for row in rows:
                    present = any(row.get(alias) not in missing for alias in (field.aliases or [field.field_id]))
                    if not present and field.field_id == "her2_status":
                        subtype = str(row.get("subtype") or "").casefold()
                        present = "her2" in subtype or "her-2" in subtype
                    if present:
                        filled += 1
                rates.append(filled / len(rows))
            return round(sum(rates) / len(rates), 4)
        assessment = result.value_assessment
        if assessment is not None and assessment.primary_coverage is not None:
            return assessment.primary_coverage
        if result.study_design is None:
            return None
        return result.study_design.variable_coverage_rate

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
