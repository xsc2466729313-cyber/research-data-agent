# VNext Phase A 完成 / Phase B 协议底座：治理与统一检索

本阶段按《乳腺癌科研数据智能体 VNext 完整改造方案》的首轮执行顺序落地，不修改冻结的 `canonical_schema.yaml`、`medical_rules.yaml` 或 SDTI 公式。

## Phase A：统一决策与 Safety Layer

新增 `backend/app/governance/`：

- `EvidenceRecord`：强制记录 `source_id`、`raw_field`、`raw_value`、`transformation`、`model_or_rule` 和版本；
- `DecisionRecord`：统一记录 proposal、置信度、证据、决策来源、规则命中和审计哈希；
- `ReviewRecord`：为 `REVIEW` 结果生成可持久化的待审记录；
- `SafetyLayer`：独立检查来源证据、HER2/ERBB2 语义边界、跨研究身份关联和 response domain。

决策顺序固定为：

```text
Proposal -> Evidence validation -> Medical/Identity rules -> AUTO/REVIEW/REJECT
```

Agent、Qwen 和算法都只能提交 proposal，不能绕过 Safety Layer。缺 Evidence、HER2 IHC 2+ 自动判阳、跨研究无 crosswalk 的患者 Join、身份矛盾和临床/细胞系 response 混用会被拒绝。

## Phase B 协议底座：Retrieval V2

新增 `RetrievalServiceV2` 和 `POST /api/v2/retrieval/search`，统一输出：

- `doc_id`、`source_id`；
- BM25、dense、fusion、rerank 分数；
- 最终 rank；
- latency、后端名称、Qwen 实际调用次数与调用率；
- 输入/输出 SHA-256、代码/模型/规则/Schema/数据清单版本。

当前默认主检索仍是 BM25；Hashing 仅是显式 fallback。真实 `BAAI/bge-small-en-v1.5` 已完成五组 BEIR test；新增融合权重校准仅使用 train/dev qrels，五组宏平均 nDCG@10 为 `0.3791`，高于 tuned BM25 `0.3147` 但低于纯 BGE `0.3880`，因此仍不切换默认主策略。CrossEncoder 模型下载不完整，尚未产生真实 reranker 分数。结果见 `evaluation/vnext_retrieval_calibrated_macro_20260828.md`。

后续 Phase C Research Agent V2 已完成结构化抽取、Evidence Pack、变量设计和研究设计编排；Phase D Schema Matcher V3 已作为独立模块和 `/api/v2/schema/match` 接入。V3 在当前已完成的 Valentine 任务上 F1 `0.7500`，低于 V2 `1.0000`，因此仍保留 V2 为默认。详见 `docs/RESEARCH_AGENT_V2_PHASE_C.md` 与 `docs/SCHEMA_MATCHER_V3_PHASE_D.md`。

Phase E Entity Matcher V3 已新增 blocking、候选特征和 PatientSampleLinker 安全授权，并提供 `/api/v2/entity/match`。五个 DeepMatcher 任务宏平均 F1 `0.4883`，低于现有 V2 `0.7408`，因此仍为实验路径。

## API

```text
POST /api/v2/governance/decide
POST /api/v2/retrieval/search
POST /api/v2/research/plan
```

旧 API 保持兼容。

## 限制与回滚

- BEIR 结果仅代表公开检索层，不代表临床效果、全 Agent 质量或 SDTI；乳腺癌 Gold Set 仍未生成新的正式成绩。
- `configs/vnext.yaml` 中的 target invocation rate 是设计目标，不是已取得的结果。
- 回滚时可移除两个 `/api/v2/` 路由以及 `governance/`、Retrieval V2 service；原检索器和旧 API 未被删除或改写。
