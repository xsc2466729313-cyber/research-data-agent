# 乳腺癌科研 Agent 检索评测

- Gold Set：`evaluation\retrieval_gold.template.jsonl`
- 评测病例：3
- 生成模型：`qwen-plus`
- DeepSeek Judge：`deepseek-chat`
- 评测状态：`configured`

| metric | value |
| --- | ---: |
| recall@1 | 0.3333 |
| recall@3 | 1.0000 |
| recall@5 | 1.0000 |
| mrr@3 | 0.6667 |
| ndcg@3 | 0.7540 |
| avg_latency_ms | 16447.3027 |
| avg_faithfulness | 4.6667 |
| avg_relevance | 4.0000 |
| avg_completeness | 2.3333 |
| avg_retrieval_quality | 3.3333 |
| avg_overall | 3.3333 |
| avg_claim_support_rate | 0.4667 |
| judge_valid_rate | 1.0000 |

## 解释

Recall/MRR/nDCG 依赖人工审核的 expected_sources；DeepSeek 评分只评审检索证据和数据摘要，不替代 Gold Set。
评测结果不能解释为临床有效性或治疗建议。
