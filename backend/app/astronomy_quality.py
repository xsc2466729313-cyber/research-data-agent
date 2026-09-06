"""Conservative observation cleaning; no patient rules or inferred photometry."""
from collections import defaultdict
import json

from .agent.models import QualityGateLayer, QualityGateReport


def clean_observations(result):
    rows = result["rows"]
    events, unique, duplicates, review = [], [], [], []
    seen, groups = {}, defaultdict(list)
    converted = 0
    for row in rows:
        raw = row["raw_value"]["observation"]
        for field in ("mjd", "magnitude", "magnitude_error"):
            converted += isinstance(raw.get(row["raw_field"][field]), str)
        for field in ("SN", "Filt", "Band"):
            value = raw.get(field)
            if isinstance(value, str) and value != value.strip():
                events.append({"observation_id": row["observation_id"], "rule": "trim_whitespace",
                               "field": field, "before": value, "after": value.strip(),
                               "reason": "仅规范化首尾空白；原文不变"})
        # Only identical source records (apart from catalog row number) can be collapsed.
        # Different measurements at the same epoch are reviewed, never averaged.
        fingerprint = (row["source_id"], json.dumps({k: v.strip() if isinstance(v, str) else v
                       for k, v in raw.items() if k != "recno"}, sort_keys=True))
        if fingerprint in seen:
            kept = seen[fingerprint]
            duplicates.append({**row, "reason": "来源内完全重复", "duplicate_of": kept})
            events.append({"observation_id": row["observation_id"], "rule": "exact_duplicate",
                           "field": "observation_id", "before": row["observation_id"], "after": kept,
                           "reason": "除目录行号外全部原始字段相同；原始行保留在来源表"})
            continue
        seen[fingerprint] = row["observation_id"]
        unique.append(row)
        groups[(row["source_id"], row["object_id"], row["band"], row["mjd"])].append(row)
    accepted = []
    for row in unique:
        flags = []
        group = groups[(row["source_id"], row["object_id"], row["band"], row["mjd"])]
        if len(group) > 1:
            flags.append("同对象/滤镜/时刻存在多条不同记录，需确认独立曝光或冲突")
        if row["magnitude_error"] == 0:
            flags.append("星等误差为零，不能直接用于误差加权分析")
        if flags:
            reason = "；".join(flags)
            review.append({**row, "reason": reason})
            events.append({"observation_id": row["observation_id"], "rule": "quarantine",
                           "field": "quality_status", "before": "parsed", "after": "review", "reason": reason})
        else:
            row["quality_status"] = "usable_observation"
            row["quality_flags"] = "metadata_unresolved" if row["metadata_match"] == "unresolved" else ""
            accepted.append(row)
    for rejected in result["rejected_rows"]:
        events.append({"observation_id": f"{rejected['source_id']}:{rejected['source_row']}",
                       "rule": "invalid_required_value", "field": "required_fields",
                       "before": "source_record", "after": "rejected", "reason": rejected["reason"]})
    accepted.sort(key=lambda row: (row["object_id"], row["band"], row["mjd"], row["source_row"]))
    result.update(rows=accepted, review_rows=review, duplicate_rows=duplicates, cleaning_events=events,
                  pipeline_version="observation-cleaning-v1")
    report = {"input_rows": len(rows) + len(result["rejected_rows"]), "usable_rows": len(accepted),
              "duplicate_rows": len(duplicates), "invalid_rows": len(result["rejected_rows"]),
              "review_rows": len(review), "numeric_values_converted": converted,
              "whitespace_values_trimmed": sum(e["rule"] == "trim_whitespace" for e in events),
              "sorting": "object_id / band / mjd / source_row",
              "imputed_values": 0, "scientific_outlier_removals": 0}
    report["reconciled"] = report["input_rows"] == sum(report[k] for k in
        ("usable_rows", "duplicate_rows", "invalid_rows", "review_rows"))
    result["cleaning_report"] = report
    result["workflow"].append({"operation": "clean_and_quarantine", "input_rows": report["input_rows"],
                               "output_rows": len(accepted), "report": report})
    missing_metadata = sum(r["metadata_match"] == "unresolved" for r in accepted)
    traceable = all(r["source_id"] and r["source_url"] and r["raw_field"] and r["raw_value"] for r in accepted)
    gates = [
        QualityGateLayer(gate_id="source_trust", label="来源与原始证据", decision="PASS" if traceable and accepted and not result["errors"] else "REVIEW",
                         checks=["原始响应 SHA256", "source_id / URL / 原始字段与值"],
                         evidence=f"{len(result['sources'])} 份来源；{len(result['errors'])} 条获取或解析异常"),
        QualityGateLayer(gate_id="field_quality", label="字段清洗与数量对账", decision="PASS" if report["reconciled"] and accepted and not report["invalid_rows"] else "REVIEW",
                         checks=["有限数值与来源单位", "完全重复去除", "保留原始值", "输入与去向数量一致"],
                         evidence=f"输入 {report['input_rows']} = 可用 {len(accepted)} + 重复 {len(duplicates)} + 无效 {report['invalid_rows']} + 待复核 {len(review)}"),
        QualityGateLayer(gate_id="entity_alignment", label="对象关联与观测冲突", decision="REVIEW" if review or missing_metadata else "PASS",
                         checks=["目录内精确对象关联", "同对象/滤镜/时刻冲突检查", "不跨目录猜测身份"],
                         evidence=f"待复核 {len(review)} 条；对象元数据未关联 {missing_metadata} 条（不影响已知对象的光度观测保留）"),
        QualityGateLayer(gate_id="research_fitness", label="分析用途与校准边界", decision="REVIEW",
                         checks=["可按对象/滤镜绘制原始光变", "未统一测光系统或时间尺度", "未执行拟合、消光或 K 修正"],
                         evidence="清洗后表用于观测整理与探索，不代表跨目录联合物理分析已就绪；不得用亮度变化本身自动删异常点"),
    ]
    result["quality_gate"] = QualityGateReport(overall="REVIEW" if accepted else "REJECT", publish_allowed=False,
        layers=gates, note="复用医学流程的来源—字段—关联—用途四层报告；仅采用观测领域规则，未套用患者阈值。保留数据下载，不把校准待确认误报为原始数据不可用。").model_dump(mode="json")
