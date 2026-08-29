# 数据报告（2026-08-29）

口径：数字只来自仓库内真实 `metrics.json` / 评测报告 / 已写入文档的任务观察。不把 development 练习册说成正式 Gold Set，不把未过质量门写成已过。正式分若是 63.36 就写 63.36；内部实测 66.94 标明非正式。

---

## 1. 正式 Gold Set

| 项 | 值 |
|---|---|
| 入口 | `goldset/templates/`（由 `official_candidate/` 拷入） |
| `gold_set_id` | `breast-cancer-official-candidate-20260829` |
| 版本 | `official-candidate-v1` |
| 审核人 | **xsc**（2026-08-29） |
| 初标 | `official-candidate-draft-builder`（与审核人不同名） |
| retrieval 行数 | **50** |
| field 行数 | **26** |
| error 行数 | **18** |
| `review_status` | 全部 `approved` |
| `frozen` | **false** |
| 是否 `frozen_test` | **否**（held-out 正式考卷，尚未 checksum 密封） |
| checksum | `fa87a48ad1b9e90b0d2652b929499a2e4bec860245eabe9b4c70b78ce828a13c` |

来源核验与确定性规则复验在 manifest 中仍为 `false`。这不是漏填正式分的借口，而是「可以对本卷评分、但不能当 sealed 赛题终考」的边界。

---

## 2. 正式评测数字

来源：`goldset/breast_cancer/official_candidate/evaluation_runs/official-candidate-20260829T132222Z/metrics.json`  
评测 ID：`official-candidate-20260829T132222Z`  
状态：`EVALUATED`  
采集：生产确定性 planner 的检索 ID（`ids_from_planner`），字段/错误观察走规则层；**不是**把 development 观察拷进来。

| 指标 | 值 | 分子 / 分母 | 目标 | 是否达标 |
|---|---:|---:|---:|---|
| retrieval_precision | 0.354839 | 11 / 31 | 0.9 | 否 |
| retrieval_recall | 0.611111 | 11 / 18 | 0.9 | 否 |
| retrieval_f1 | 0.448980 | — | 0.9 | 否 |
| faithfulness | 0.653846 | 17 / 26 | 0.95 | 否 |
| traceability | 1.000000 | 26 / 26 | 1.0 | 是 |
| error_precision | 1.000000 | 8 / 8 | — | — |
| error_recall | 0.533333 | 8 / 15 | — | — |
| error_f1 | 0.695652 | — | 0.9 | 否 |
| repair_accuracy | 0.500000 | 1 / 2 | 0.9 | 否 |
| **SDTI** | **63.36** | 几何平均 × 100 | 90 | **否** |

SDTI 按冻结公式：

```text
100 * (retrieval_f1 * faithfulness * traceability * error_f1 * repair_accuracy) ** (1/5)
= 100 * (0.448980 * 0.653846 * 1.0 * 0.695652 * 0.50) ** (1/5)
= 63.359664  → 报告为 63.36
```

| 安全项 | 值 |
|---|---|
| 安全门 | **FAIL** |
| `publish_allowed` | **false** |
| 红线 | Faithfulness < 90% |
| 发布阻断 | 5 个高风险问题仍未解决；尚未 sealed `frozen_test` |
| 虚假来源率 | 0 / 12 |

同一套数字也出现在稍早的 `official-candidate-20260829T131315Z`（SDTI 同为 63.359664）。看板以最新 stamp `20260829T132222Z` 为准。

公式未改。目标 90 未达到。不得对外宣称「正式发布通过」。

---

## 3. development 非正式分（对照，禁止混用）

| | Source Broker 对照 | 千问 LIVE（生产主链观察） |
|---|---|---|
| 评测 ID | `development-xsc-20260829` | `development-xsc-qwen-live-20260829` |
| Gold Set | `breast-cancer-development-20260829` | 同左 |
| 行数 | retrieval 53 / field 35 / error 22 | 同左 |
| SDTI | 63.69 | **66.94** |
| retrieval_f1 | 0.458333 | 0.588235 |
| faithfulness | 0.771429 | 0.771429 |
| error_f1 | 0.592593 | 0.592593 |
| repair_accuracy | 0.50 | 0.50 |
| 安全门 | FAIL | FAIL |
| `publish_allowed` | false | false |

66.94 来自 `goldset/breast_cancer/development/evaluation_runs/development-xsc-qwen-live-20260829/metrics.json`。这是练习册 + 千问 LIVE 的内部实测，**不是正式成绩**。系统已经用该分册改过检索种子、DepMap 工具和任务内补搜，再当期末考则成绩不可信。

对比（不得相减当「提升了 3.58 分」对外宣传）：正式卷更难、题面 held-out，正式 SDTI **低于**练习册观察分。这符合预期。

---

## 4. 一次真实研究任务观察

口径与 `docs/徐士诚_方向1A_P5-P7-P12-P16-P18_报告稿.md` 已跑通的内部对照一致。代表输入（可替换）：

> 研究 HER2 阳性乳腺癌中 PIK3CA 突变是否影响治疗响应，并整理患者级科研数据集。

| 观察 | 记录 | 说明 |
|---|---|---|
| 真实检索但结局不同域 | METABRIC **848 行 × 46 列** | 生存/临床描述为主；治疗响应分析集为 **0** |
| 漏斗 | Raw Samples=848；Target Cohort=0；Analysis Dataset=0 | 有宽表 ≠ 本题可用 |
| 质量门 | **REVIEW**，不可自动发布 | 结局不匹配就会待补 |
| 换队列补结局 | GSE76360 基线 **50** 例，48 例有治疗响应 | 公开矩阵**无 PIK3CA**；拒绝跨库贴突变 |
| 同患者暴露+结局 | cBioPortal `breast_alpelisib_2020` | 完整变量包，不是半成品队列 |

质量门代码当前行为（`backend/app/agent/quality_gate.py`）：主表无行、字段完整率不足、**结局未对齐**、本题需要 HER2 但 `her2_status` 覆盖不足时，Gate 2 / Gate 4 为 **REVIEW**，证据写「本题要的结局字段还没对上，质量门因此待补」。

因此：**还没提升到能过门。缺少的还是缺少——缺 pCR、缺 HER2、结局不匹配、质量门待补。** 闭环改搜路径已接，但旧任务结果不会自动变成 PASS。

---

## 5. 下一步要过门需要什么

不要假称已经过门。要让当前研究任务质量门从 REVIEW 往 PASS 走，至少需要：

1. **重新跑协议**（工作台再提交同一问题或走两轮闭环），让新检索进入当前结果；旧矩阵不会原地补列。
2. **补 pCR 队列**：第二轮应实际拉到 `GSE25066` / `GSE76360` / `GSE50948` 中含病理完全缓解或治疗响应注释的患者表，而不是继续停在 METABRIC 生存列。
3. **补 HER2 临床状态**（本题若要求 HER2+）：从 GEO 样本特征或 cBioPortal `HER2_STATUS` / IHC 对齐 `her2_status`；IHC 2+ 保持 Equivocal。
4. 结局与问题同域后，字段完整率与变量覆盖仍须过门控阈值；高风险医学字段不得自动修。
5. 正式发布还要求：Faithfulness ≥ 90%、高风险问题清零、Gold Set 完成来源/规则复验并 `frozen=true`。当前正式卷 **63.36 / FAIL / publish_allowed=false**，这些都还没满足。

闭环意图代码：`backend/app/agent/outcome_repair.py`（缺 pCR 且当前是生存表 → 改搜 GSE25066 等）。意图 ≠ 旧结果已修复。
