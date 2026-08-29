# 数据报告：分层指标对照（2026-08-29）

数字只从仓库 `metrics.json`、BEIR 汇总 JSON、已归档评测报告抄入。不同层不能相加成一个总分。正式 SDTI **63.36** 与 development 非正式 **66.94** 分栏；后者禁止当正式成绩。缺 pCR / HER2、质量门 REVIEW 没有写成已过。

详细能力层报告仍见：
- [综合设计、功能与评测报告](FINAL_INTEGRATED_REPORT_20260829.md)
- [Qwen3.8-Max 分层、对比与消融](../evaluation/reports/qwen38_20260829/FINAL_EVALUATION_REPORT_ZH.md)
- 看板「结果对照」同源检索表：`evaluation/vnext_retrieval_calibrated_macro_20260828.json`

---

## 1. 分层总览

三套分层不要混读。

### 1.1 质量门（任务能不能发布）

工作台四层 Gate（`backend/app/agent/quality_gate.py`）：来源可信 → 字段质量 → 实体一致性 → 科研适用性。总体只有全 PASS 才 `publish_allowed`。缺结局、缺 HER2、字段完整率不足 → **REVIEW**。

### 1.2 能力层（模块在公开基准上强不强）

检索 nDCG、Schema F1、Entity F1、清洗 Cell F1。只说明对应模块，**不是**乳腺癌正式 SDTI。

### 1.3 评测层（Gold Set 考卷）

| 层 | 考什么 | 正式卷行数 | 非正式 development |
|---|---|---:|---:|
| 检索层 | 这句话该不该检索到某数据集 | 50 | 53 |
| 字段层 | 原始值应标准化成什么 | 26 | 35 |
| 错误修复层 | 哪些错必须检出、能不能自动修 | 18 | 22 |
| 安全门 | 虚假来源、Faithfulness 红线、高风险未决 | 见下表 FAIL | FAIL |
| 正式 SDTI | 五分量几何平均 × 100 | **63.36** | **66.94（非正式）** |

---

## 2. 一张总对照表：非正式 vs 正式

| 指标 | development 千问 LIVE（非正式） | 正式 official_candidate | 目标 |
|---|---:|---:|---:|
| Gold Set ID | `breast-cancer-development-20260829` | `breast-cancer-official-candidate-20260829` | — |
| 评测 ID | `development-xsc-qwen-live-20260829` | `official-candidate-20260829T132222Z` | — |
| 审核人 | xsc | xsc | — |
| `frozen_test` | 否 | 否（`frozen=false`） | sealed 终考才是 |
| retrieval_precision | 0.600000（15/25） | 0.354839（11/31） | 0.9 |
| retrieval_recall | 0.576923（15/26） | 0.611111（11/18） | 0.9 |
| **retrieval_f1** | **0.588235** | **0.448980** | 0.9 |
| **faithfulness** | **0.771429**（27/35） | **0.653846**（17/26） | 0.95 |
| **traceability** | **1.000000**（35/35） | **1.000000**（26/26） | 1.0 |
| error_precision | 1.000000（8/8） | 1.000000（8/8） | — |
| error_recall | 0.421053（8/19） | 0.533333（8/15） | — |
| **error_f1** | **0.592593** | **0.695652** | 0.9 |
| **repair_accuracy** | **0.500000**（1/2） | **0.500000**（1/2） | 0.9 |
| **SDTI** | **66.94** | **63.36** | 90 |
| 安全门 | FAIL | FAIL | PASS |
| **publish_allowed** | **false** | **false** | true |
| 红线 | Faithfulness < 90%；5 个高风险未解决 | 同左 + 尚未 sealed frozen_test | — |

来源：
- `goldset/breast_cancer/development/evaluation_runs/development-xsc-qwen-live-20260829/metrics.json`
- `goldset/breast_cancer/official_candidate/evaluation_runs/official-candidate-20260829T132222Z/metrics.json`

SDTI 公式未改：`100 * (retrieval_f1 * faithfulness * traceability * error_f1 * repair_accuracy) ** (1/5)`。正式卷 63.359664 → **63.36**。非正式 66.944454 → **66.94**。不得相减宣传「提升了 3.58 分」：正式卷是 held-out，练习册更熟。

对照跑（非生产主链）`development-xsc-20260829` Source Broker seed：SDTI **63.69**，retrieval_f1 0.458333，仅作内部对照。

---

## 3. 检索对照：BM25 vs BGE vs 融合

与前端评测看板「结果对照」同一张表。范围：BEIR 5 集、**3,677** 条查询。**只评检索层，不是临床效果，也不是正式 Retrieval F1。**

宏平均（`evaluation/vnext_retrieval_calibrated_macro_20260828.json` → `aggregate`）：

| 方法 | 数据集 | 查询数 | nDCG@10 | Recall@100 | MRR@10 | 延迟 |
|---|---:|---:|---:|---:|---:|---:|
| 调参 BM25 | 5 | 3,677 | **0.3147** | 0.5552 | 0.3629 | 54.57 ms |
| **BGE-small-en-v1.5** | 5 | 3,677 | **0.3880** | **0.6554** | **0.4421** | 10.72 ms |
| BM25+BGE 融合 | 5 | 3,677 | 0.3791 | 0.6422 | 0.4277 | 62.73 ms |

BGE 相对 BM25：nDCG **+0.0733**，Recall@100 **+0.1002**，MRR **+0.0792**。融合没有超过纯 BGE，生产检索候选是 BGE，BM25 作回退。

按数据集（看板列：n / BM25 nDCG@10 / BGE nDCG@10 / 融合 / BGE Δ / BGE R@100）：

| 数据集 | n | BM25 nDCG@10 | BGE nDCG@10 | 融合 nDCG@10 | BGE Δ | BGE R@100 |
|---|---:|---:|---:|---:|---:|---:|
| SciFact（科学事实） | 300 | 0.6044 | **0.6803** | 0.6803 | +0.0759 | 0.9383 |
| NFCorpus（生物医学） | 323 | 0.2902 | **0.3315** | 0.3318 | +0.0413 | 0.2975 |
| SciDocs（科学论文） | 1,000 | 0.1490 | **0.1910** | 0.1563 | +0.0420 | 0.4312 |
| ArguAna（论辩检索） | 1,406 | 0.3067 | **0.3836** | 0.3741 | +0.0768 | 0.9687 |
| FiQA（财经问答） | 648 | 0.2230 | **0.3533** | 0.3533 | +0.1304 | 0.6413 |

五个分层 BGE 的 nDCG 都高于 BM25。NFCorpus 增益最小，生物医学检索仍是短板；FiQA 增益最大但不能当乳腺癌专项成绩。

---

## 4. 其他能力层（不能并进 SDTI）

| 层 | 对照 | 本项目 | 来源 |
|---|---:|---:|---|
| Schema 匹配（Valentine 10 任务） | V3 F1 0.7994 | **生产 V2 F1 0.8451** | `docs/GITHUB项目指标与链接.md` |
| 实体匹配（DeepMatcher 5 任务） | V3 校准 F1 0.5579 | **生产 V2 F1 0.7408** | 同上 |
| 查询理解 75 条 | A nDCG 0.3151 / R@100 0.5557 | E nDCG 0.3007 / **R@100 0.5726** | `evaluation/reports/qwen38_20260829/` |
| 中间智能体 3×3 | DeepSeek Recall@3 0.6667 | **Qwen3.8-Max 1.0000** | 同上；两组质量门 **9/9 REVIEW** |
| 两轮闭环（1 个真实 Qwen 任务） | 第一轮 target match 0.82 | **第二轮 1.00** | 数据行仍 141，未决缺口仍 2 |

查询理解 E 组提高召回但损害 nDCG，**不全局启用**。Qwen/DeepSeek 是小样本工程对照，不外推通用排名。闭环 progress score 从 0.915 → 0.960，不是 Repair Accuracy，也不是 SDTI。

---

## 5. 一次研究任务观察（不是正式分）

代表输入：研究 HER2 阳性乳腺癌中 PIK3CA 突变与新辅助治疗响应的关系。

这是任务级诊断，**不要写进正式 SDTI 栏**。

| 观察 | 记录数 / 覆盖 | 结局 | 质量门 | 缺什么 |
|---|---|---|---|---|
| METABRIC 宽表（结局不同域） | **848 行 × 46 列** | 生存/临床为主；治疗响应分析集 **0**；漏斗 Target Cohort=0、Analysis Dataset=0 | **REVIEW**，不可发布 | 缺 pCR / 治疗响应；有表 ≠ 本题可用 |
| GSE76360 换队列 | 基线 **50** 例，48 例有治疗响应 | 结局同域 | 仍不能跨库贴突变 | 公开矩阵 **无 PIK3CA** |
| 历史 Qwen 两轮闭环 | 数据行 **141**；来源 63→68 | target match 0.82→1.00 | 该次任务内记 PASS | **未决缺口仍 2**；行数没增加 |
| 当前质量门规则 | 字段完整率 &lt; 80% 或结局未对齐 → Gate 2 REVIEW；本题要 HER2 但 `her2_status` 覆盖不足 → Gate 4 REVIEW | — | 待补 | **缺 HER2、缺 pCR 仍然缺** |

848 / 50 / 141 来自 `docs/徐士诚_方向1A_P5-P7-P12-P16-P18_报告稿.md` 与 `evaluation/reports/qwen38_20260829/FINAL_EVALUATION_REPORT_ZH.md` 已归档观察。仓库里没有单独的「561/848」日志，不编这一格。

闭环代码已接线：缺 pCR 且当前是生存表 → 改搜 GSE25066 / GSE76360 / GSE50948。**工作台上的旧任务不会自动过门**，必须重新跑协议。代码接了补搜 ≠ 当前这张表已经补上。

---

## 6. 正式 Gold Set 元数据

| 项 | 值 |
|---|---|
| 入口 | `goldset/templates/` ← `official_candidate/` |
| 行数 | retrieval 50 / field 26 / error 18 |
| 审核人 | xsc（2026-08-29） |
| checksum | `fa87a48ad1b9e90b0d2652b929499a2e4bec860245eabe9b4c70b78ce828a13c` |
| 重跑 | `POST /api/evaluation/official-run` 或 `python goldset/breast_cancer/official_candidate/collect_official_sdti.py` |

---

## 7. 诚实结论

1. 检索能力层：BGE nDCG@10 **0.3880** > BM25 **0.3147**（3,677 查询）。这是公开检索，不是正式 Retrieval F1。
2. 正式考卷：SDTI **63.36**，目标 90 未到，`publish_allowed=false`。最弱项 Retrieval F1 0.45、Faithfulness 0.65、Repair 0.50。
3. 练习册千问 LIVE：SDTI **66.94**，非正式。
4. 研究任务：848 行 METABRIC 仍可因结局不匹配被拦住；缺 pCR / HER2、质量门 REVIEW **还没提升成 PASS**。
5. 下一步：重新跑协议，实际拉到 GSE25066 等 pCR 队列；不要假称旧结果已过门。
