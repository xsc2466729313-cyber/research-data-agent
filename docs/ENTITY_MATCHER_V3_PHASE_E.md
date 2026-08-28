# Entity Matcher V3 Phase E

Phase E 新增 `backend/app/integration/entity_matcher_v3.py`，并将 Entity 流程拆为：

```text
Blocking → Candidate Pairs → Feature Extraction → Matcher → PatientSampleLinker
```

关键安全约束：跨研究、患者 ID 矛盾和样本 ID 矛盾直接 REJECT；没有 `PatientSampleLinker` 授权时，即使模型置信度达到 0.99 也只能 REVIEW。公开 benchmark 的 REVIEW 仅代表候选提案，不能解释为自动合并。

## 真实公开对照

五个官方 DeepMatcher 测试集宏平均：

| 方法 | Precision | Recall | F1 |
|---|---:|---:|---:|
| Project learned entity rule v2 | 0.7259 | 0.7668 | 0.7408 |
| Project entity matcher v3 (fixed threshold) | 0.5860 | 0.4514 | 0.4883 |
| Project entity matcher v3 (train/valid calibrated) | 0.5251 | 0.6229 | 0.5579 |

V3 校准后比固定阈值提高 F1 `0.0697`、Recall `0.1715`，但仍低于 V2，保留为实验路径，不切换默认。最新产物位于 `evaluation/public_benchmarks/runs/20260828T110116Z_deepmatcher_*` 至 `evaluation/public_benchmarks/runs/20260828T110119Z_deepmatcher_*`。

## 限制

- 公开数据是通用实体匹配，不是乳腺癌患者身份 Gold Set。
- V3 的 learned matcher 和 Qwen judge 尚未接入；当前使用确定性特征融合。
- False Merge、False Split、Unresolved Rate 需要领域 Gold Set 后再报告。
- 回滚继续使用 `EntityMatcherV2`；V3 不修改 `PatientSampleLinker` 的既有安全决策。
