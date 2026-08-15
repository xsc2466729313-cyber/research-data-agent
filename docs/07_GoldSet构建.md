# 07 Gold Set 构建

采用低人工模式：

```text
强模型初标
→ 第二强模型独立复核
→ 确定性规则验证
→ 真实 accession / URL 验证
→ 分歧与高风险样本人工抽检
```

AI 输出不能直接视为 Ground Truth。

## Gold Set A：科研问题—数据集

目标：
- Retrieval Precision
- Retrieval Recall
- Retrieval F1

建议：
- 30～50 个问题
- 300～500 个 question–dataset pair

## Gold Set B：字段标准化

目标：
- Faithfulness
- Schema Mapping

建议：
- 约 300 条字段/值 pair

至少包含：
- HER2 / ERBB2
- ER / ESR1
- PR / PgR
- Drug alias
- Gene alias
- assay 差异

## Gold Set C：错误检测与修复

目标：
- Error P/R/F1
- Repair Accuracy

建议：
- 100～200 个错误案例

类别：
- duplicate
- missing
- gene alias
- drug alias
- schema mapping error
- HER2 assay error
- provenance missing
- patient/sample conflict
