# 规则 × Agent 协同升级（Phase 1）

本阶段按《乳腺癌科研数据智能体_规则Agent协同升级设计稿》落地四个边界清晰的组件：

| 层 | 组件 | 负责内容 | 不负责内容 |
|---|---|---|---|
| 总控 | `ResearchOrchestrator` | 判断下一阶段、需要的工具和停止条件 | 不修改数据、不绕过质量门 |
| 规划 | `ResearchAgent` | 把文献证据、候选问题和变量需求组织成一个规划门面 | 不把无证据模板当正式结论 |
| 算法 | `BM25Retriever`、`HybridRetrieverV2`、`SchemaMatcherV2`、`EntityMatcherV2` | 检索、候选生成、字段/实体相似度计算 | 不替代医学安全判断 |
| 规则 | `QualityAgent` 与冻结 `medical_rules.yaml` | 缺失、冲突、医学禁用语义和发布门控 | 不自动修复高风险值 |

## 决策边界

字段匹配统一输出 `AUTO (>=0.90)`、`REVIEW (0.65-0.90)`、`REJECT (<0.65)`。实体匹配在高置信度前仍检查 `study_id`、`patient_id` 冲突；冲突永远拒绝自动合并。Quality Agent 复用现有 `ErrorClassifier`，只产生审核报告，不直接改变记录。

## 检索策略

`HybridRetrieverV2` 先用 BM25 和可替换的 dense backend 建候选池，再用透明 reranker 排序。当前默认 dense 实现是离线 hashing fallback，生产环境可通过接口替换 BGE；这不会把 fallback 成绩冒充 BGE 成绩。

## 后续阶段

下一阶段应接入真实 embedding/reranker，重新运行 BEIR 的 BM25、Hashing、Embedding、Hybrid、Hybrid+Reranker 对比，并用冻结验证集校准字段/实体阈值；同时增加 Qwen Alone、Qwen+RAG、Full Agent 的端到端 Research-Ready 评测。
